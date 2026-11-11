import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

class Settings(dict):
    def set(self, key, value): self[key] = value
    def save(self, **kwargs): self.saved = True

class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.previous = sys.modules.get("frappe")
        self.f = types.ModuleType("frappe")
        self.f.db = types.SimpleNamespace(exists=Mock(return_value=True))
        self.f.has_permission = Mock(return_value=True)
        sys.modules["frappe"] = self.f
        spec = importlib.util.spec_from_file_location("simple_home_policy", Path(__file__).parents[1]/"rivora/presentation.py")
        self.module = importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
    def tearDown(self):
        if self.previous is None:sys.modules.pop("frappe",None)
        else:sys.modules["frappe"] = self.previous
    def test_matching_types_get_only_todo(self):
        for name in ["Training","Employee Self Service","Contractor"]:
            self.assertEqual(self.module.home_doctypes(name,{"home_rules":[{"user_type":name}]}),["ToDo"])
    def test_nonmatching_and_empty_configuration_show_full_dashboard(self):
        self.assertIsNone(self.module.home_doctypes("System User",{"home_rules":[{"user_type":"Training"}]}))
        self.assertIsNone(self.module.home_doctypes("Training",{"home_rules":[]}))
        self.assertIsNone(self.module.home_doctypes("",{"home_rules":[{}]}))
    def test_membership_ignores_case_whitespace_and_duplicate_rows(self):
        self.assertEqual(self.module.home_doctypes(" training ",{"home_rules":[{"user_type":"Training"},{"user_type":"Training"}]}),["ToDo"])
    def test_legacy_single_doctype_is_respected(self):
        settings={"dashboard_configuration":"Repository defaults","home_rules":[{"user_type":"Contractor","home_mode":"Full dashboard","document_type":"Task"}]}
        self.assertEqual(self.module.home_doctypes("Contractor",settings),["Task"])
        self.assertIsNone(self.module.home_doctypes("Training",settings))
    def test_existing_read_permissions_and_missing_doctypes_still_apply(self):
        self.f.has_permission.side_effect=lambda name,ptype:name=="ToDo"
        settings={"home_rules":[{"user_type":"Training"}]}
        self.assertEqual(self.module.home_doctypes("Training",settings),["ToDo"])
        self.f.db.exists.return_value=False
        self.assertEqual(self.module.home_doctypes("Training",settings),[])
    def test_migration_preserves_unique_custom_user_types(self):
        settings=Settings(home_rules=[{"user_type":"Contractor","document_type":"Task"},{"user_type":"Contractor","document_type":"ToDo"}])
        self.f.get_single=Mock(return_value=settings)
        self.module.initialize_home_user_types(legacy_mode="Custom rules")
        self.assertEqual(settings["home_rules"],[{"user_type":"Contractor", "allowed_doctypes":"Task\nToDo"}])
        self.assertTrue(settings.saved)
    def test_migration_preserves_empty_custom_list(self):
        settings=Settings(home_rules=[]);self.f.get_single=Mock(return_value=settings)
        self.module.initialize_home_user_types(legacy_mode="Custom rules")
        self.assertEqual(settings["home_rules"],[])
    def test_initial_defaults_seed_only_existing_user_types(self):
        settings=Settings(home_rules=[]);self.f.get_single=Mock(return_value=settings)
        self.f.db.exists.side_effect=lambda kind,name:name=="Training"
        self.module.initialize_home_user_types()
        self.assertEqual(settings["home_rules"],[{"user_type":"Training", "allowed_doctypes":"ToDo"}])
    def test_runtime_profile_uses_settings_without_reseeding(self):
        settings=Settings(home_rules=[]);self.f.get_single=Mock(return_value=settings)
        self.assertIsNone(self.module.profile_policy("Training")["home_doctypes"])
        self.assertFalse(hasattr(settings,"saved"))

    def test_multiple_selected_doctypes_deduplicate_and_obey_read_permission(self):
        settings = {'home_rules': [{'user_type': 'Training', 'allowed_doctypes': 'ToDo\nSales Invoice\nToDo\nDelivery Note'}]}
        self.f.has_permission.side_effect = lambda name, kind: name != 'Sales Invoice'
        self.assertEqual(self.module.home_doctypes('Training', settings), ['ToDo', 'Delivery Note'])

    def test_explicit_empty_selection_is_restricted_not_full_dashboard(self):
        settings = {'home_rules': [{'user_type': 'Training', 'allowed_doctypes': ''}]}
        self.assertEqual(self.module.home_doctypes('Training', settings), [])
        self.assertIsNone(self.module.home_doctypes('System User', settings))

    def test_initialization_preserves_multiselections_and_empty_choices(self):
        settings = Settings(home_rules=[{'user_type': 'Training', 'allowed_doctypes': 'ToDo\nSales Invoice'}, {'user_type': 'Contractor', 'allowed_doctypes': ''}])
        self.f.get_single = Mock(return_value=settings)
        self.module.initialize_home_user_types(legacy_mode='Custom rules')
        self.assertEqual(settings['home_rules'], [{'user_type': 'Training', 'allowed_doctypes': 'ToDo\nSales Invoice'}, {'user_type': 'Contractor', 'allowed_doctypes': ''}])

if __name__ == "__main__":unittest.main()
