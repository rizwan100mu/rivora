import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


class LabelTests(unittest.TestCase):
    def test_metadata_labels_translate_without_touching_names_options_or_data(self):
        saved = sys.modules.get('frappe')
        frappe = types.ModuleType('frappe')
        frappe.whitelist = lambda **kw: lambda fn: fn
        frappe._ = lambda value, lang=None: {'Customer Name': 'اسم العميل', 'Company': 'الشركة'}.get(value, value)
        class Field(dict):
            __getattr__ = dict.get
        fields = [Field(fieldname='customer_name', label='Customer Name', fieldtype='Data'),
                  Field(fieldname='accounts', label='Accounts', fieldtype='Table', options='Party Account')]
        frappe.get_meta = Mock(side_effect=lambda name: types.SimpleNamespace(fields=fields if name == 'Customer' else [Field(label='Company', fieldname='company', fieldtype='Link', options='Company')]))
        sys.modules['frappe'] = frappe
        try:
            spec = importlib.util.spec_from_file_location('labels_under_test', Path(__file__).parents[1] / 'rivora/ui_labels.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            result = module.form_labels('Customer', 'ar')
            self.assertEqual(result, {'Customer Name': 'اسم العميل', 'Company': 'الشركة'})
            self.assertEqual(fields[0]['fieldname'], 'customer_name')
            self.assertEqual(fields[0]['label'], 'Customer Name')
            self.assertEqual(fields[1]['options'], 'Party Account')
            frappe.get_meta.reset_mock()
            self.assertEqual(module.form_labels('Customer', 'en'), {})
            self.assertEqual(module.form_labels('Customer', 'invalid'), {})
            frappe.get_meta.assert_not_called()
        finally:
            if saved is None: sys.modules.pop('frappe', None)
            else: sys.modules['frappe'] = saved
