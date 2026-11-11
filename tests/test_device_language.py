import ast
import hashlib
from pathlib import Path
import re
import types
import unittest
from unittest.mock import Mock


class DeviceLanguageTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).parents[1]/"rivora/api.py").read_text(encoding="utf-8"))
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"register_device","set_device_language"}]
        self.doc=types.SimpleNamespace(user="me@example.com",save=Mock())
        self.f=types.SimpleNamespace(whitelist=lambda **kw:lambda fn:fn,session=types.SimpleNamespace(user="me@example.com"),db=types.SimpleNamespace(exists=Mock(return_value=True)),get_doc=Mock(return_value=self.doc),PermissionError=PermissionError)
        self.f.throw=lambda text,kind=ValueError:(_ for _ in ()).throw(kind(text))
        scope={"frappe":self.f,"_":lambda text:text,"identity":Mock(return_value="EMP-1"),"hashlib":hashlib,"re":re,"now_datetime":lambda:"now"}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),"device_language","exec"),scope)
        self.register=scope["register_device"];self.set_language=scope["set_device_language"]

    def test_registration_saves_app_language_on_current_user_device(self):
        self.register("a"*48,"token",language="ar")
        self.assertEqual(self.doc.language,"ar")
        self.doc.save.assert_called_once_with(ignore_permissions=True)

    def test_language_update_checks_current_user_scope(self):
        self.set_language("a"*48,"ar")
        filters=self.f.db.exists.call_args.args[1]
        self.assertEqual(filters["user"],"me@example.com")
        self.assertEqual(self.doc.language,"ar")

    def test_another_users_device_cannot_be_modified(self):
        self.doc.user="other@example.com"
        with self.assertRaises(PermissionError):self.set_language("a"*48,"ar")
        self.doc.save.assert_not_called()

    def test_invalid_language_cannot_be_saved(self):
        with self.assertRaises(ValueError):self.set_language("a"*48,"invalid")
        self.doc.save.assert_not_called()

if __name__=="__main__":unittest.main()
