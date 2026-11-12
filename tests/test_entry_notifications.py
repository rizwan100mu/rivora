import importlib.util
from pathlib import Path
import unittest


class RetiredEngineTests(unittest.TestCase):
    def test_pre_upgrade_jobs_are_harmless_without_frappe_or_settings(self):
        path = Path(__file__).parents[1] / "rivora/entry_notifications.py"
        spec = importlib.util.spec_from_file_location("retired_engine", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIsNone(module.validate_settings(None))
        self.assertIsNone(module.queue_entry_alert(None))
        self.assertIsNone(module.deliver_entry_alert("Task", "TASK-1", "date"))
