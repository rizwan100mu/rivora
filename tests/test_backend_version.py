import ast
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).parents[1]

class VersionTests(unittest.TestCase):
    def test_version_helper_reports_rivora_and_separate_source_provenance(self):
        source = ROOT / 'rivora/mobile/v1/employee.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'get_backend_employee_version')
        function.decorator_list = []
        tree = ast.Module(body=[function], type_ignores=[])
        app = types.ModuleType('rivora'); app.__version__ = '2.0.1'
        upstream = types.ModuleType('rivora._bundled_employee')
        exec((ROOT/'rivora/_bundled_employee.py').read_text(), upstream.__dict__)
        saved = dict(sys.modules)
        sys.modules.update({'rivora': app, 'rivora._bundled_employee': upstream})
        def fail(error): raise error
        namespace = {'gen_response': lambda status, message, data: data, 'exception_handler': fail}
        try:
            exec(compile(ast.fix_missing_locations(tree), str(source), 'exec'), namespace)
            result = namespace['get_backend_employee_version']()
            self.assertEqual(result['app'], 'rivora')
            self.assertEqual(result['version'], app.__version__)
            self.assertEqual(result['bundled_source_version'], '2.2.5')
        finally:
            sys.modules.clear(); sys.modules.update(saved)
