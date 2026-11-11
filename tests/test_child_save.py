import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


class Field(dict):
    def __getattr__(self, key):
        return self.get(key)


class Document(dict):
    def __init__(self, **values):
        super().__init__(values)
        self.check_permission = Mock()
        self.save = Mock()
        self.insert = Mock()
    def __getattr__(self, key):
        if key in self:
            return self[key]
        raise AttributeError(key)
    def as_dict(self):
        return dict(self)


class ChildSaveTests(unittest.TestCase):
    module_file = 'api.py'
    def setUp(self):
        self.saved_modules = dict(sys.modules)
        f = types.ModuleType('frappe')
        f.whitelist = lambda **kw: lambda fn: fn
        f._ = lambda value: value
        f.PermissionError = PermissionError
        f.TimestampMismatchError = RuntimeError
        f.MandatoryError = ValueError
        f.throw = lambda msg, kind=ValueError: (_ for _ in ()).throw(kind(msg))
        f.parse_json = lambda value: value
        f.session = types.SimpleNamespace(user='employee@example.com')
        f.db = types.SimpleNamespace(get_value=Mock(return_value='EMP-1'))
        self.parent_meta = types.SimpleNamespace(fields=[
            Field(fieldname='title', fieldtype='Data'),
            Field(fieldname='items', fieldtype='Table', options='Quotation Item'),
        ])
        self.child_meta = types.SimpleNamespace(fields=[
            Field(fieldname='item_code', fieldtype='Link', options='Item'),
            Field(fieldname='qty', fieldtype='Float'),
            Field(fieldname='rate', fieldtype='Currency'),
            Field(fieldname='source_detail', fieldtype='Data', hidden=1),
            Field(fieldname='derived_value', fieldtype='Currency', read_only=1),
        ])
        f.get_meta = Mock(side_effect=lambda name: self.child_meta if name == 'Quotation Item' else self.parent_meta)
        self.row = Document(name='ROW-1', doctype='Quotation Item', parent='Q-1', parenttype='Quotation', parentfield='items', idx=1, item_code='ITEM', qty=1, rate=10, source_detail='SOURCE-ROW', derived_value=100)
        self.doc = Document(name='Q-1', doctype='Quotation', modified='stamp', docstatus=0, items=[self.row], meta=self.parent_meta, quotation_to='Customer', party_name='CUST-1')
        f.get_doc = Mock(return_value=self.doc)
        f.new_doc = Mock(return_value=self.doc)
        sys.modules['frappe'] = f
        utils = types.ModuleType('frappe.utils')
        for name in ['cint', 'getdate', 'now_datetime', 'nowdate', 'add_days', 'add_months']:
            setattr(utils, name, Mock())
        utils.cint = lambda value: int(value or 0)
        sys.modules['frappe.utils'] = utils
        workflow = types.ModuleType('frappe.model.workflow')
        for name in ['apply_workflow', 'get_transitions', 'get_workflow_name', 'has_approval_access']:
            setattr(workflow, name, Mock())
        sys.modules['frappe.model.workflow'] = workflow
        guard_spec=importlib.util.spec_from_file_location('rivora.transaction_validation',Path(__file__).parents[1]/'rivora/transaction_validation.py')
        guard=importlib.util.module_from_spec(guard_spec);guard_spec.loader.exec_module(guard)
        sys.modules['rivora.transaction_validation']=guard
        spec = importlib.util.spec_from_file_location('rivora.child_save_api', Path(__file__).parents[1] / 'rivora' / self.module_file)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)
        self.api.attachment_urls = Mock(return_value=[])
        self.f = f

    def tearDown(self):
        for key in list(sys.modules):
            if key not in self.saved_modules:
                sys.modules.pop(key, None)
        sys.modules.update(self.saved_modules)

    def save(self, rows):
        return self.api.save_document('Quotation', {'modified': 'stamp', 'items': rows}, name='Q-1')

    def test_existing_row_edit_preserves_identity_source_and_server_fields(self):
        result = self.save([{'name': 'ROW-1', 'qty': 4, 'source_detail': 'FORGED', 'derived_value': 0, 'parent': 'OTHER'}])
        rows = self.doc['items']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'ROW-1')
        self.assertEqual(rows[0]['qty'], 4)
        self.assertEqual(rows[0]['rate'], 10)
        self.assertEqual(rows[0]['source_detail'], 'SOURCE-ROW')
        self.assertEqual(rows[0]['derived_value'], 100)
        self.assertEqual(rows[0]['parent'], 'Q-1')
        self.assertEqual(result['name'], 'Q-1')
        self.doc.save.assert_called_once_with()
        self.doc.insert.assert_not_called()
        self.doc.check_permission.assert_called_once_with('write')

    def test_new_row_is_cleaned_and_explicit_omission_removes_old_row(self):
        self.save([{'item_code': 'NEW', 'qty': 2, 'source_detail': 'FORGED', 'flags': {'ignore_mandatory': True}}])
        self.assertEqual(self.doc['items'], [{'item_code': 'NEW', 'qty': 2}])

    def test_empty_table_deliberately_removes_all_rows(self):
        self.save([])
        self.assertEqual(self.doc['items'], [])

    def test_foreign_row_rejected_before_save_or_parent_mutation(self):
        original = list(self.doc['items'])
        with self.assertRaises(PermissionError):
            self.save([{'name': 'FOREIGN', 'qty': 2}])
        self.assertEqual(self.doc['items'], original)
        self.doc.save.assert_not_called()

    def test_duplicate_row_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.save([{'name': 'ROW-1'}, {'name': 'ROW-1'}])
        self.doc.save.assert_not_called()

    def test_non_string_child_name_rejected(self):
        with self.assertRaises(PermissionError):
            self.save([{'name': ['ROW-1']}])
        self.doc.save.assert_not_called()

    def test_permission_failure_precedes_cleaning_and_write(self):
        self.doc.check_permission.side_effect = PermissionError('denied')
        with self.assertRaises(PermissionError):
            self.save([{'name': 'ROW-1', 'qty': 9}])
        self.assertEqual(self.doc['items'][0]['qty'], 1)
        self.doc.save.assert_not_called()

    def test_server_validation_error_propagates_without_bypass_or_insert(self):
        self.doc.save.side_effect = ValueError('controller rejected')
        with self.assertRaisesRegex(ValueError, 'controller rejected'):
            self.save([{'name': 'ROW-1', 'qty': 2}])
        self.doc.save.assert_called_once_with()
        self.doc.insert.assert_not_called()

    def test_new_parent_uses_normal_insert_and_rejects_named_foreign_rows(self):
        self.api.save_document('Quotation', {'items': [{'item_code': 'NEW', 'qty': 1}]})
        self.doc.insert.assert_called_once_with()
        self.doc.save.assert_not_called()
        self.doc.check_permission.assert_called_once_with('create')
        with self.assertRaises(PermissionError):
            self.api.save_document('Quotation', {'items': [{'name': 'ROW-1', 'qty': 2}]})

    def test_customer_script_local_row_uses_insert_without_client_identity(self):
        self.api.save_document('Customer', {'items': [{
            'name': 'new-native-7', '__islocal': 1, 'qty': 2,
            'parent': 'new-customer', 'parenttype': 'Customer',
            'parentfield': 'wrong', 'doctype': 'Wrong', 'idx': 99,
            'flags': {'ignore_mandatory': True},
        }]})
        self.assertEqual(self.doc['items'], [{'qty': 2}])
        self.doc.insert.assert_called_once_with()

    def test_saved_document_accepts_local_rows_alongside_existing_rows(self):
        self.save([{'name': 'ROW-1', 'qty': 3},
                   {'name': 'new-native-8', '__islocal': 1, 'item_code': 'NEW', 'qty': 2}])
        self.assertEqual(self.doc['items'][0]['name'], 'ROW-1')
        self.assertEqual(self.doc['items'][0]['source_detail'], 'SOURCE-ROW')
        self.assertEqual(self.doc['items'][1], {'item_code': 'NEW', 'qty': 2})

    def test_local_flag_never_authorizes_foreign_database_identity(self):
        for row in [{'name': 'FOREIGN', '__islocal': 1},
                    {'name': 'new-native-9'},
                    {'name': 'new-native-9', '__islocal': '1'},
                    {'name': 'new-native-9-foreign', '__islocal': 1}]:
            with self.subTest(row=row), self.assertRaises(PermissionError):
                self.save([row])
        self.doc.save.assert_not_called()

    def test_duplicate_local_rows_rejected_before_write(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.save([{'name': 'new-native-1', '__islocal': 1}] * 2)
        self.doc.save.assert_not_called()

    def test_local_flag_cannot_replace_existing_row_identity_or_server_fields(self):
        self.save([{'name': 'ROW-1', '__islocal': 1, 'qty': 9, 'source_detail': 'FORGED'}])
        self.assertEqual(self.doc['items'][0]['name'], 'ROW-1')
        self.assertEqual(self.doc['items'][0]['source_detail'], 'SOURCE-ROW')
        self.assertNotIn('__islocal', self.doc['items'][0])

    def test_reorder_keeps_row_identities_and_updates_positions(self):
        row2 = Document(name='ROW-2', item_code='SECOND', qty=1, idx=2, source_detail='SOURCE-2')
        self.doc['items'].append(row2)
        self.save([{'name': 'ROW-2', 'qty': 3}, {'name': 'ROW-1', 'qty': 4}])
        self.assertEqual([(r['name'], r['idx']) for r in self.doc['items']], [('ROW-2', 1), ('ROW-1', 2)])
        self.assertEqual(self.doc['items'][0]['source_detail'], 'SOURCE-2')

    def test_omitted_table_does_not_replace_existing_children(self):
        self.api.save_document('Quotation', {'title': 'Changed'}, name='Q-1')
        self.assertIs(self.doc['items'][0], self.row)

    def test_non_save_cleaner_keeps_copy_preview_behavior_without_child_identity(self):
        cleaned = self.api.clean_values('Quotation', {'items': [{'name': 'COPY-ROW', 'qty': 3}]})
        self.assertEqual(cleaned, {'items': [{'qty': 3}]})

    def test_existing_self_scope_policy_remains_enforced(self):
        self.doc['employee'] = 'OTHER-EMPLOYEE'
        with self.assertRaises(PermissionError):
            self.api.save_document('Leave Application', {'title': 'Changed'}, name='Q-1')
        self.doc.save.assert_not_called()


class LegacyChildSaveTests(ChildSaveTests):
    module_file = 'legacy_api.py'


if __name__ == '__main__':
    unittest.main()
