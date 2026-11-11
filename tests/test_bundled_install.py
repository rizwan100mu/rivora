from pathlib import Path
import ast
import importlib.util
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("rivora_local_install", ROOT / "install_local.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class BundledTests(unittest.TestCase):
    def test_no_separate_employee_backend_python_imports(self):
        for path in (ROOT / "rivora").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.ImportFrom): self.assertFalse((node.module or "").startswith("employee_self_service"), str(path))
                if isinstance(node, ast.Import):
                    self.assertFalse(any(a.name.startswith("employee_self_service") for a in node.names), str(path))
        hooks = (ROOT / "rivora/hooks.py").read_text()
        self.assertIn('required_apps = ["erpnext", "hrms"]', hooks)
    def test_legacy_apps_are_refused_before_any_installer_write(self):
        with tempfile.TemporaryDirectory() as folder:
            bench = Path(folder); source = bench / "apps/rivora"; source.mkdir(parents=True)
            site = bench / "sites/demo"; site.mkdir(parents=True); (site / "site_config.json").write_text("{}")
            with self.assertRaisesRegex(RuntimeError, "staging migration"):
                installer.validate(bench, "demo", source, {"erpnext", "hrms", "employee_self_service"})
            self.assertFalse((bench / "sites/apps.txt").exists())
    def test_fresh_site_accepts_local_bundled_app(self):
        with tempfile.TemporaryDirectory() as folder:
            bench=Path(folder); source=bench/'apps/rivora'; source.mkdir(parents=True)
            site=bench/'sites/demo';site.mkdir(parents=True);(site/'site_config.json').write_text('{}')
            self.assertEqual(installer.validate(bench,'demo',source,{'erpnext','hrms'})[1],source.resolve())
