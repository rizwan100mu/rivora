import ast, importlib.util, json, sys, types, unittest
from pathlib import Path
from unittest.mock import Mock
ROOT = Path(__file__).parents[1]
class MergeTests(unittest.TestCase):
    def test_all_branded_schemas_are_unique_and_have_renamed_controllers(self):
        names = set()
        for path in (ROOT/'rivora').rglob('*.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('doctype') != 'DocType': continue
            name = data['name']
            self.assertNotIn(name, names)
            names.add(name)
            self.assertTrue(name.startswith('Rivora '))
            self.assertNotEqual(name, 'Employee Self Service Settings')
            self.assertEqual(data['module'], 'Rivora')
            # Frappe resolves controllers from the scrubbed DocType name.
            scrubbed = name.lower().replace(' ', '_').replace('-', '_')
            self.assertEqual(path.parent.name, scrubbed)
            self.assertEqual(path.stem, scrubbed)
            self.assertTrue(path.with_suffix('.py').is_file())
            controller = path.with_suffix('.py')
            if controller.exists():
                classes = {n.name for n in ast.parse(controller.read_text(encoding='utf-8')).body if isinstance(n, ast.ClassDef)}
                self.assertIn(name.replace(' ', '').replace('-', ''), classes)
        self.assertIn('Rivora Post', names)
        self.assertIn('Rivora Mobile Post', names)
        self.assertIn('Rivora Settings', names)
        self.assertIn('Rivora Mobile Settings', names)
        self.assertIn('Rivora Employee Mobile Event', names)
    def load_guard(self, installed, old_schema=False):
        f=types.SimpleNamespace(get_installed_apps=lambda: installed, get_all=lambda *a, **kw: ['Rivora Post'] if old_schema else [], throw=lambda text: (_ for _ in ()).throw(ValueError(text)))
        saved=sys.modules.get('frappe');sys.modules['frappe']=f
        self.addCleanup(lambda:sys.modules.__setitem__('frappe',saved) if saved else sys.modules.pop('frappe',None))
        spec=importlib.util.spec_from_file_location('rivora_lifecycle_check',ROOT/'rivora/lifecycle.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    def test_existing_employee_install_is_refused(self):
        with self.assertRaisesRegex(ValueError,'reviewed staging'): self.load_guard(['frappe','employee_self_service']).assert_installable()
    def test_existing_rivora_install_is_refused(self):
        with self.assertRaisesRegex(ValueError,'reviewed staging'): self.load_guard(['frappe','rizora_workforce']).assert_installable()
    def test_orphaned_old_schema_is_refused(self):
        with self.assertRaisesRegex(ValueError,'Existing legacy employee schema'): self.load_guard(['frappe'], True).assert_installable()
    def test_fresh_site_is_eligible(self): self.load_guard(['frappe','erpnext','hrms']).assert_installable()
    def test_both_hook_families_are_retained(self):
        source=(ROOT/'rivora/hooks.py').read_text()
        self.assertIn('deepcopy(employee.doc_events)',source)
        self.assertIn('deepcopy(employee.scheduler_events)',source)
        self.assertIn('rivora.transaction_validation.before_validate',source)
        self.assertNotIn('rivora.entry_notifications.queue_entry_alert',source)
