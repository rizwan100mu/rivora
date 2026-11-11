import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

class CompanyTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)
        f = types.ModuleType('frappe')
        f.whitelist = lambda **kw: lambda fn: fn
        f._ = lambda s: s
        f.PermissionError = PermissionError
        f.throw = lambda message, kind=ValueError: (_ for _ in ()).throw(kind(message))
        f.get_list = Mock(return_value=[types.SimpleNamespace(name='A'), types.SimpleNamespace(name='B')])
        f.get_single = Mock(return_value=types.SimpleNamespace(session_defaults=[types.SimpleNamespace(ref_doctype='Company')]))
        f.defaults = types.SimpleNamespace(get_user_default=Mock(return_value='B'))
        f.db = types.SimpleNamespace(get_value=Mock(return_value='Employee'))
        sys.modules['frappe'] = f
        api = types.ModuleType('rivora.api'); api.identity = Mock(return_value='EMP-1')
        sys.modules['rivora.api'] = api
        setter = types.ModuleType('frappe.core.doctype.session_default_settings.session_default_settings')
        self.setter = Mock(return_value='success'); setter.set_session_default_values = self.setter
        sys.modules[setter.__name__] = setter
        spec = importlib.util.spec_from_file_location('rivora.company_context', Path(__file__).parents[1]/'rivora/company_context.py')
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.f = f; self.identity = api.identity
    def tearDown(self):
        for key in list(sys.modules):
            if key not in self.saved: sys.modules.pop(key, None)
        sys.modules.update(self.saved)
    def test_defaults_come_from_framework_and_not_employee_company(self):
        result=self.module.get_context()
        self.assertEqual(result['company'],'B')
        self.assertEqual(result['companies'],['A','B'])
        self.f.defaults.get_user_default.assert_called_once_with('Company')
        self.assertEqual(self.f.get_list.call_args.kwargs['limit_page_length'],0)
    def test_invalid_default_does_not_choose_first_of_multiple_companies(self):
        self.f.defaults.get_user_default.return_value='Other'
        self.assertIsNone(self.module.get_context()['company'])
    def test_only_permitted_company_is_default_when_unset(self):
        self.f.defaults.get_user_default.return_value=None
        self.f.get_list.return_value=[types.SimpleNamespace(name='A')]
        self.assertEqual(self.module.get_context()['company'],'A')
    def test_switch_uses_standard_frappe_session_default_setter(self):
        self.module.set_company('B')
        self.setter.assert_called_once_with({'company':'B'})
    def test_unpermitted_company_never_changes_defaults(self):
        with self.assertRaises(PermissionError): self.module.set_company('Other')
        self.setter.assert_not_called()
    def test_guest_never_reads_companies(self):
        self.identity.side_effect=PermissionError('Sign in')
        for method in [self.module.get_context, lambda:self.module.set_company('B')]:
            with self.assertRaises(PermissionError): method()
        self.f.get_list.assert_not_called()
    def test_company_switch_respects_session_default_configuration(self):
        self.f.get_single.return_value.session_defaults=[]
        with self.assertRaises(ValueError): self.module.set_company('B')
        self.setter.assert_not_called()
    def test_failed_framework_setter_is_reported(self):
        self.setter.return_value=None
        with self.assertRaises(ValueError): self.module.set_company('B')

if __name__=='__main__': unittest.main()
