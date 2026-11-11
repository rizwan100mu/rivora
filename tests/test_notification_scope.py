import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.saved=dict(sys.modules)
        f=types.ModuleType('frappe');f.DoesNotExistError=KeyError
        self.doc={'owner':'creator','allocated_to':'worker'}
        f.get_doc=Mock(side_effect=lambda *a:self.doc)
        f.has_permission=Mock(return_value=True)
        f.db=types.SimpleNamespace(exists=Mock(return_value=False))
        sys.modules['frappe']=f;self.f=f
        spec=importlib.util.spec_from_file_location('scope_test',Path(__file__).parents[1]/'rivora/notification_scope.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
    def tearDown(self):
        for key in list(sys.modules):
            if key not in self.saved:sys.modules.pop(key,None)
        sys.modules.update(self.saved)
    def test_assigned_todo_only_assignee_even_with_read_access(self):
        for user,allowed in [('worker',True),('creator',False),('manager',False),('other',False)]:
            self.assertEqual(self.module.personal_document('ToDo','TODO-1',user),allowed)
    def test_unallocated_todo_owner_only(self):
        self.doc['allocated_to']=None
        self.assertTrue(self.module.personal_document('ToDo','TODO-1','creator'))
        self.assertFalse(self.module.personal_document('ToDo','TODO-1','other'))
    def test_document_owner_or_open_assignee(self):
        self.doc={'owner':'creator'}
        self.assertTrue(self.module.personal_document('Quotation','Q-1','creator'))
        self.assertFalse(self.module.personal_document('Quotation','Q-1','reader'))
        self.f.db.exists.return_value=True
        self.assertTrue(self.module.personal_document('Quotation','Q-1','worker'))
        self.assertEqual(self.f.db.exists.call_args.args[1],{'reference_type':'Quotation','reference_name':'Q-1','allocated_to':'worker','status':'Open'})
    def test_revoked_permission_blocks_owner_and_assignee(self):
        self.f.has_permission.return_value=False
        self.assertFalse(self.module.personal_document('ToDo','TODO-1','worker'))
        self.assertFalse(self.module.personal_document('Quotation','Q-1','creator'))
    def test_missing_guest_and_unreferenced_fail_closed(self):
        for dt,name,user in [(None,None,'worker'),('ToDo','TODO-1','Guest')]:
            self.assertFalse(self.module.personal_document(dt,name,user))
        self.f.get_doc.side_effect=KeyError()
        self.assertFalse(self.module.personal_document('ToDo','missing','worker'))
    def test_employee_reference_has_same_scope(self):
        self.assertTrue(self.module.personal_alert({'reference_document':'ToDo','reference_name':'TODO-1'},'worker'))
        self.assertFalse(self.module.personal_alert({'reference_document':'ToDo','reference_name':'TODO-1'},'other'))

if __name__=='__main__':unittest.main()
