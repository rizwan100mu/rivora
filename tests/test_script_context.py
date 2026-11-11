import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock


class ScriptContextTests(unittest.TestCase):
    def setup_context(self, user):
        self.frappe = types.SimpleNamespace(
            whitelist=lambda **kw: lambda fn: fn,
            session=types.SimpleNamespace(user=user),
            defaults=types.SimpleNamespace(
                get_user_default=Mock(return_value='own-default'),
                get_defaults=Mock(return_value={'custom_key':'own-value'}),
                get_user_permissions=Mock(return_value={'Company':[]}),
            ),
            db=types.SimpleNamespace(get_single_value=Mock(return_value='setting')),
            get_roles=Mock(return_value=['Sales User']),
            AuthenticationError=PermissionError,
            throw=lambda text, kind: (_ for _ in ()).throw(kind(text)),
        )
        tree = ast.parse((Path(__file__).parents[1]/'rivora/script_context.py').read_text())
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        namespace = {'frappe':self.frappe}
        exec(compile(tree,'script_context','exec'),namespace)
        return namespace['get_context']

    def test_only_own_context_and_allowlisted_settings(self):
        result = self.setup_context('own@example.com')()
        self.assertEqual(result['user'],'own@example.com')
        self.assertEqual(result['roles'],['Sales User'])
        self.assertIn('custom_key',result['defaults'])
        self.frappe.defaults.get_defaults.assert_called_once_with('own@example.com')
        self.frappe.get_roles.assert_called_once_with('own@example.com')
        self.assertEqual(set(result['system_defaults']), {'number_format','float_precision','currency_precision','rounding_method'})

    def test_guest_has_no_context(self):
        with self.assertRaises(PermissionError): self.setup_context('Guest')()
        self.frappe.get_roles.assert_not_called()
        self.frappe.defaults.get_user_default.assert_not_called()


if __name__ == '__main__': unittest.main()
