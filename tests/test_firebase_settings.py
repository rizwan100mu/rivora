import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class FirebaseSettingsTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f._ = lambda text: text
        self.f.only_for = Mock()
        self.f.throw = lambda text: (_ for _ in ()).throw(ValueError(text))
        self.f.conf = {}
        self.f.get_single = Mock()
        self.password = types.ModuleType('frappe.utils.password')
        self.password.set_encrypted_password = Mock()
        self.password.get_decrypted_password = Mock(return_value=None)
        self.google = types.ModuleType('google.oauth2.service_account')
        self.google.Credentials = types.SimpleNamespace(from_service_account_info=Mock())
        self.patch = patch.dict(sys.modules, {'frappe': self.f, 'frappe.utils.password': self.password, 'google.oauth2.service_account': self.google})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        spec = importlib.util.spec_from_file_location('firebase_settings_check', Path(__file__).parents[1] / 'rivora/firebase_settings.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.data = {'type': 'service_account', 'project_id': 'rizora-5a6e6', 'client_email': 'firebase@example.com', 'private_key': 'test-secret', 'token_uri': 'https://oauth2.googleapis.com/token'}

    def test_upload_encrypts_and_returns_only_project(self):
        result = self.module.upload_credentials(json.dumps(self.data))
        self.f.only_for.assert_called_once_with('System Manager')
        self.f.get_single.return_value.check_permission.assert_called_once_with('write')
        self.assertEqual(result, {'configured': True, 'project_id': 'rizora-5a6e6'})
        self.assertEqual(json.loads(self.password.set_encrypted_password.call_args.args[2]), self.data)
        self.assertNotIn('test-secret', str(result))

    def test_unauthorized_upload_never_reads_or_stores_credentials(self):
        self.f.only_for.side_effect = PermissionError()
        with self.assertRaises(PermissionError): self.module.upload_credentials(json.dumps(self.data))
        self.f.get_single.assert_not_called()
        self.password.set_encrypted_password.assert_not_called()

    def test_invalid_or_android_files_never_replace_existing_key(self):
        for value in ['not json', '{}', json.dumps({'project_info': {}}), 'x' * 32769, json.dumps({**self.data, 'token_uri': 'https://example.com/token'})]:
            with self.subTest(value=value[:20]):
                with self.assertRaisesRegex(ValueError, 'valid Firebase Admin'): self.module.upload_credentials(value)
        self.password.set_encrypted_password.assert_not_called()

    def test_status_never_returns_key(self):
        self.password.get_decrypted_password.return_value = json.dumps(self.data)
        self.assertEqual(self.module.configuration_status(), {'configured': True, 'source': 'settings', 'project_id': 'rizora-5a6e6'})

    def test_bad_pem_is_rejected_without_echoing_key(self):
        self.google.Credentials.from_service_account_info.side_effect = ValueError('test-secret')
        with self.assertRaises(ValueError) as raised: self.module.upload_credentials(json.dumps(self.data))
        self.assertNotIn('test-secret', str(raised.exception))
        self.password.set_encrypted_password.assert_not_called()
