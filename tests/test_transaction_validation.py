import importlib.util
from pathlib import Path
import sys,types,unittest
from unittest.mock import Mock

class PartyValidationTests(unittest.TestCase):
    def setUp(self):
        self.saved=dict(sys.modules);f=types.ModuleType('frappe');f._=lambda s:s;f.MandatoryError=ValueError
        f.throw=lambda msg,kind:(_ for _ in ()).throw(kind(msg));f.get_request_header=Mock(return_value='1')
        sys.modules['frappe']=f;self.f=f
        spec=importlib.util.spec_from_file_location('party_guard',Path(__file__).parents[1]/'rivora/transaction_validation.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
    def tearDown(self):
        for key in list(sys.modules):
            if key not in self.saved:sys.modules.pop(key,None)
        sys.modules.update(self.saved)
    def doc(self,type,**values):return types.SimpleNamespace(doctype=type,get=lambda k:values.get(k))
    def test_every_trade_type_requires_its_party_on_mobile(self):
        for type,key in self.module.PARTY_FIELDS.items():
            with self.subTest(type=type):
                with self.assertRaises(ValueError):self.module.before_validate(self.doc(type,quotation_to='Customer'))
                self.module.before_validate(self.doc(type,quotation_to='Customer',**{key:'PARTY-1'}))
    def test_quotation_requires_type_and_accepts_customer_lead_prospect_and_deal(self):
        with self.assertRaises(ValueError):self.module.require_party(self.doc('Quotation',party_name='A'))
        for target in ['Customer','Lead','Prospect','CRM Deal']:
            self.module.require_party(self.doc('Quotation',quotation_to=target,party_name='A'))
    def test_desk_quotation_policy_is_not_globally_changed(self):
        self.f.get_request_header.return_value=None
        self.module.before_validate(self.doc('Quotation'))
        with self.assertRaises(ValueError):self.module.require_party(self.doc('Quotation'))
    def test_non_party_doctypes_keep_normal_erp_rules(self):
        for type in ['Material Request','ToDo','Journal Entry','BOM','Stock Entry']:
            self.module.before_validate(self.doc(type))

class PagePackageTests(unittest.TestCase):
    def test_registered_routes_have_exact_matching_assets(self):
        import json
        base=Path(__file__).parents[1]/'rivora/rivora/page'
        for route in ['employee-location-tr','employee-location-tracker']:
            slug=route.replace('-','_');folder=base/slug
            data=json.loads((folder/(slug+'.json')).read_text())
            self.assertEqual(data['name'],route);self.assertEqual(data['page_name'],route)
            self.assertIn('frappe.pages["'+route+'"]',(folder/(slug+'.js')).read_text())
            self.assertTrue(list(folder.iterdir()))
    def test_javascript_in_distribution_manifest(self):
        root=Path(__file__).parents[1]
        self.assertIn('*.js',(root/'MANIFEST.in').read_text());self.assertIn('"*.js"',(root/'pyproject.toml').read_text())

class PageRepairTests(unittest.TestCase):
    def test_existing_role_rows_survive_forced_reload(self):
        saved=dict(sys.modules)
        try:
            f=types.ModuleType('frappe');doc=Mock();doc.get.return_value=[types.SimpleNamespace(as_dict=lambda:{'role':'HR Manager'})]
            f.db=Mock();f.db.exists.return_value=True;f.get_doc=Mock(return_value=doc);f.reload_doc=Mock();f.clear_cache=Mock()
            sys.modules['frappe']=f
            path=Path(__file__).parents[1]/'rivora/patches/fix_rivora_employee_location_page.py'
            spec=importlib.util.spec_from_file_location('page_repair',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.execute()
            self.assertEqual(f.reload_doc.call_count,2)
            self.assertEqual(doc.set.call_count,2)
            doc.set.assert_called_with('roles',[{'role':'HR Manager'}])
            self.assertTrue(doc.flags.do_not_update_json)
            doc.save.assert_called_with(ignore_permissions=True)
            self.assertIn('fix_rivora_employee_location_page',(path.parent.parent/'patches.txt').read_text().split('[post_model_sync]')[0])
        finally:
            for key in list(sys.modules):
                if key not in saved:sys.modules.pop(key,None)
            sys.modules.update(saved)

if __name__=='__main__':unittest.main()
