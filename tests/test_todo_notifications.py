import importlib.util
from pathlib import Path
import unittest


class RetiredEngineTests(unittest.TestCase):
    def test_pre_upgrade_jobs_are_harmless_without_frappe_or_settings(self):
        path = Path(__file__).parents[1] / "rivora/todo_notifications.py"
        spec = importlib.util.spec_from_file_location("retired_engine", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIsNone(module.queue_assignment(None))
        self.assertIsNone(module.deliver_assignment("TODO-1", "user", "date"))
