import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.saved={k:v for k,v in sys.modules.items() if k=='frappe' or k.startswith('frappe.') or k=='rivora.api'}
        f=types.ModuleType('frappe');f.whitelist=lambda **kw:lambda fn:fn;f._=lambda text:text
        f.PermissionError=PermissionError
        f.throw=lambda text,kind=ValueError:(_ for _ in ()).throw(kind(text))
        f.parse_json=lambda value:json.loads(value) if isinstance(value,str) else value
        f.db=types.SimpleNamespace(get_value=Mock(return_value=1))
        self.perms={'read':True,'share':True,'write':True,'submit':True}
        def check(kind):
            if not self.perms.get(kind):raise PermissionError(kind)
        self.doc=types.SimpleNamespace(check_permission=Mock(side_effect=check),has_permission=lambda kind:self.perms.get(kind,False),meta=types.SimpleNamespace(issingle=False),get=lambda key:'["assignee@example.com"]' if key=='_assign' else None)
        f.get_doc=Mock(return_value=self.doc);f.get_all=Mock(return_value=[])
        f.get_system_settings=Mock(return_value=0)
        sys.modules['frappe']=f
        utils=types.ModuleType('frappe.utils');utils.cint=lambda value:int(value or 0);sys.modules['frappe.utils']=utils
        api=types.ModuleType('rivora.api');api.allowed=Mock();sys.modules['rivora.api']=api
        self.allowed=api.allowed
        assignments=types.ModuleType('frappe.desk.form.assign_to');assignments.add=Mock();assignments.remove=Mock()
        sys.modules['frappe.desk.form.assign_to']=assignments
        sharing=types.ModuleType('frappe.share');sharing.add=Mock();sharing.remove=Mock();sys.modules['frappe.share']=sharing
        self.assignments=assignments;self.sharing=sharing;self.f=f
        spec=importlib.util.spec_from_file_location('rivora.document_access',Path(__file__).parents[1]/'rivora/document_access.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def tearDown(self):
        for key in list(sys.modules):
            if key=='frappe' or key.startswith('frappe.') or key=='rivora.api':sys.modules.pop(key)
        sys.modules.update(self.saved)

    def test_assignment_uses_standard_api_and_deduplicates_users(self):
        self.module.assign('Quotation','Q-1',['user@example.com','user@example.com'],description='Please review',priority='High',due_date='2026-11-02')
        args=self.assignments.add.call_args.args[0]
        self.assertEqual(args,{'doctype':'Quotation','name':'Q-1','assign_to':['user@example.com'],'description':'Please review','priority':'High','date':'2026-11-02'})
        self.assertNotIn('ignore_permissions',args)
        self.doc.check_permission.assert_called_with('read')

    def test_unreadable_document_cannot_be_assigned(self):
        self.perms['read']=False
        with self.assertRaises(PermissionError):self.module.assign('Quotation','Q-1',['user@example.com'])
        self.assignments.add.assert_not_called()

    def test_unsupported_document_rejected_before_read(self):
        self.allowed.side_effect=PermissionError()
        with self.assertRaises(PermissionError):self.module.status('Forbidden','X')
        self.f.get_doc.assert_not_called()

    def test_disabled_user_cannot_be_assigned(self):
        self.f.db.get_value.return_value=0
        with self.assertRaises(ValueError):self.module.assign('Quotation','Q-1',['disabled@example.com'])
        self.assignments.add.assert_not_called()

    def test_sharing_passes_permission_flags_to_public_api(self):
        self.module.share('Sales Order','SO-1','user@example.com',write=1,submit=0,share=0,notify=1)
        self.sharing.add.assert_called_once_with('Sales Order','SO-1',user='user@example.com',read=1,write=1,submit=0,share=0,everyone=0,notify=1)
        self.doc.check_permission.assert_called_with('share')

    def test_no_share_permission_blocks_write(self):
        self.perms['share']=False
        with self.assertRaises(PermissionError):self.module.share('Sales Order','SO-1','user@example.com')
        self.sharing.add.assert_not_called()

    def test_disabled_site_sharing_blocks_write(self):
        self.f.get_system_settings.return_value=1
        with self.assertRaises(PermissionError):self.module.share('Sales Order','SO-1','user@example.com')
        self.sharing.add.assert_not_called()

    def test_shared_access_list_is_hidden_without_share_permission(self):
        self.perms['share']=False
        result=self.module.status('Quotation','Q-1')
        self.assertFalse(result['can_share']);self.assertEqual(result['shares'],[])
        self.f.get_all.assert_not_called()

    def test_status_share_query_is_document_scoped(self):
        result=self.module.status('Quotation','Q-1')
        self.assertEqual(result['assignees'],['assignee@example.com'])
        self.assertEqual(self.f.get_all.call_args.kwargs['filters'],{'share_doctype':'Quotation','share_name':'Q-1'})

    def test_unassign_uses_standard_remove(self):
        self.module.unassign('Quotation','Q-1','user@example.com')
        self.assignments.remove.assert_called_once_with('Quotation','Q-1',assign_to='user@example.com')

    def test_unshare_requires_permission_before_internal_remove(self):
        self.perms['share']=False
        with self.assertRaises(PermissionError):self.module.unshare('Quotation','Q-1','user@example.com')
        self.sharing.remove.assert_not_called()

    def test_standard_permission_rejection_propagates(self):
        self.sharing.add.side_effect=PermissionError('Cannot grant write')
        with self.assertRaises(PermissionError):self.module.share('Quotation','Q-1','user@example.com',write=1)

if __name__=='__main__':unittest.main()
