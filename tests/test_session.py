import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: v for k, v in sys.modules.items() if k == 'frappe' or k.startswith('frappe.') or k in {'rivora.api','rivora.notification_history'}}
        f = types.ModuleType('frappe')
        f.whitelist = lambda **kw: lambda fn: fn
        f.AuthenticationError = PermissionError
        f.PermissionError = PermissionError
        f._ = lambda s: s
        f.throw = lambda message, kind=ValueError: (_ for _ in ()).throw(kind(message))
        f.form_dict = {}
        f.session = types.SimpleNamespace(user='Guest',sid='Guest')
        f.db = types.SimpleNamespace(get_value=Mock(return_value='Training'))
        self.manager = types.SimpleNamespace(login=Mock(),logout=Mock())
        f.local = types.SimpleNamespace(login_manager=self.manager,response={})
        f.get_list = Mock(return_value=[])
        sys.modules['frappe'] = f
        utils = types.ModuleType('frappe.utils'); utils.cint = lambda v: int(v or 0)
        sys.modules['frappe.utils'] = utils
        sessions = types.ModuleType('frappe.sessions'); sessions.get_csrf_token = lambda: 'csrf'
        sys.modules['frappe.sessions'] = sessions
        self.cached = Mock(return_value=('me@example.com','cached-password'))
        twofactor = types.ModuleType('frappe.twofactor'); twofactor.get_cached_user_pass = self.cached
        sys.modules['frappe.twofactor'] = twofactor
        api = types.ModuleType('rivora.api')
        def identity():
            if f.session.user == 'Guest': raise PermissionError('Sign in required')
            return 'EMP-1'
        api.identity = identity
        sys.modules['rivora.api'] = api
        self.history = types.ModuleType('rivora.notification_history')
        self.history.list_notifications = Mock(return_value=[])
        sys.modules['rivora.notification_history'] = self.history
        spec = importlib.util.spec_from_file_location('rivora.session',Path(__file__).parents[1]/'rivora/session.py')
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.f = f

    def tearDown(self):
        for key in list(sys.modules):
            if key == 'frappe' or key.startswith('frappe.') or key in {'rivora.api','rivora.notification_history'}: sys.modules.pop(key)
        sys.modules.update(self.saved)

    def complete(self):
        self.f.session.user='me@example.com'; self.f.session.sid='session-id'

    def test_authentication_rejection_never_returns_session(self):
        self.manager.login.side_effect=PermissionError('locked out')
        with self.assertRaises(PermissionError): self.module.login('me@example.com','bad')
        self.manager.login.assert_called_once()

    def test_otp_pending_never_returns_credentials(self):
        self.manager.login.return_value=False
        self.f.local.response={'tmp_id':'challenge','verification':{'method':'OTP'}}
        result=self.module.login('me@example.com','password')
        self.assertTrue(result['data']['two_factor_required'])
        self.assertNotIn('session_id',result)

    def test_success_uses_framework_session_without_api_keys(self):
        self.manager.login.side_effect=self.complete
        result=self.module.login('me@example.com','password')
        self.assertEqual(result['session_id'],'session-id')
        self.assertEqual(result['csrf_token'],'csrf')
        self.assertEqual(result['user_type'],'Training')
        self.assertNotIn('key_details',result)

    def test_password_reset_cannot_return_old_authenticated_session(self):
        self.complete(); self.manager.login.return_value=False
        self.f.local.response={'message':'Password Reset'}
        with self.assertRaises(PermissionError): self.module.login('someone@example.com','password')

    def test_expired_otp_cannot_use_existing_session(self):
        self.complete(); self.cached.return_value=(None,None)
        with self.assertRaises(PermissionError): self.module.verify_2fa_otp('expired','123456')
        self.manager.login.assert_not_called()

    def test_otp_must_pass_framework_login(self):
        self.manager.login.side_effect=self.complete
        result=self.module.verify_2fa_otp('challenge','123456')
        self.assertEqual(result['user'],'me@example.com')
        self.manager.login.assert_called_once()
        self.assertNotIn('usr',self.f.form_dict)

    def test_guest_cannot_read_dashboard_or_notifications(self):
        for method in [self.module.get_dashboard,self.module.notification_list,self.module.get_feed]:
            with self.assertRaises(PermissionError): method()
        self.f.get_list.assert_not_called()

    def test_mobile_adapter_uses_shared_personal_history_guard(self):
        self.complete();self.module.notification_list(start=-10,page_length=999)
        self.history.list_notifications.assert_called_once_with(start=-10,page_length=999)
        self.f.get_list.assert_not_called()

    def test_logout_delegates_to_framework(self):
        self.module.logout();self.manager.logout.assert_called_once()


if __name__ == '__main__': unittest.main()
