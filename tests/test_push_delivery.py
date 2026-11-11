import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


class PushDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k:v for k,v in sys.modules.items() if k in {"frappe", "firebase_admin", "firebase_admin.messaging", "firebase_admin.credentials"}}
        f = types.ModuleType("frappe")
        f.whitelist = lambda **kw: lambda fn: fn
        f._ = lambda text, **kwargs:text
        f.AuthenticationError = PermissionError
        f.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
        f.throw = lambda text, kind=ValueError: (_ for _ in ()).throw(kind(text))
        f.session = types.SimpleNamespace(user="me@example.com")
        f.conf = {"rivora_firebase_credentials":"/private/account.json"}
        f.local = types.SimpleNamespace(site="erp.local")
        f.db = types.SimpleNamespace(exists=Mock(return_value=True),delete=Mock())
        f.get_all = Mock(return_value=["device-key"])
        f.get_doc = Mock(return_value=types.SimpleNamespace(get_password=Mock(return_value="private-token")))
        f.has_permission = Mock(return_value=True)
        f.log_error = Mock()
        self.f = f;sys.modules["frappe"] = f
        admin = types.ModuleType("firebase_admin")
        admin.get_app = Mock(return_value=object())
        admin.initialize_app = Mock(return_value=object())
        credentials = types.ModuleType("firebase_admin.credentials")
        credentials.Certificate = Mock(return_value=object())
        messaging = types.ModuleType("firebase_admin.messaging")
        for name in ["Message","Notification","AndroidConfig","AndroidNotification"]:
            setattr(messaging,name,lambda **kw: types.SimpleNamespace(**kw))
        messaging.UnregisteredError = type("UnregisteredError",(Exception,),{})
        messaging.send = Mock(return_value="message-id")
        admin.credentials = credentials;admin.messaging=messaging
        sys.modules.update(firebase_admin=admin)
        sys.modules["firebase_admin.credentials"] = credentials
        sys.modules["firebase_admin.messaging"] = messaging
        self.admin = admin;self.messaging = messaging
        self.previous_firebase_settings = sys.modules.get('rivora.firebase_settings')
        self.firebase_settings = types.ModuleType('rivora.firebase_settings')
        self.firebase_settings.service_account = Mock(return_value=None)
        sys.modules['rivora.firebase_settings'] = self.firebase_settings
        scope_spec=importlib.util.spec_from_file_location('rivora.notification_scope',Path(__file__).parents[1]/'rivora/notification_scope.py')
        scope=importlib.util.module_from_spec(scope_spec);scope_spec.loader.exec_module(scope)
        sys.modules['rivora.notification_scope']=scope
        spec=importlib.util.spec_from_file_location("rivora.delivery_test",Path(__file__).parents[1]/"rivora/push_delivery.py")
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def tearDown(self):
        if self.previous_firebase_settings is None:
            sys.modules.pop('rivora.firebase_settings', None)
        else:
            sys.modules['rivora.firebase_settings'] = self.previous_firebase_settings
        for key in ["frappe","firebase_admin","firebase_admin.messaging","firebase_admin.credentials"]: sys.modules.pop(key,None)
        sys.modules.update(self.saved)

    def test_high_priority_sound_and_channel_are_sent(self):
        result=self.module.send_user_push("me@example.com", is_test=True)
        message=self.messaging.send.call_args.args[0]
        self.assertEqual(result,{"status":"sent","sent":1})
        self.assertEqual(message.android.priority,"high")
        self.assertEqual(message.android.notification.channel_id,"rivora_alerts_v1")
        self.assertEqual(message.android.notification.sound,"default")
        self.assertEqual(self.f.get_all.call_args.kwargs["filters"],{"user":"me@example.com"})

    def test_missing_credentials_reported_without_delivery(self):
        self.f.conf.clear()
        self.assertEqual(self.module.send_user_push("me@example.com", is_test=True)["status"],"no_credentials")
        self.messaging.send.assert_not_called()

    def test_uploaded_credentials_take_priority_and_rotation_changes_app(self):
        self.admin.get_app.side_effect = ValueError()
        self.firebase_settings.service_account.return_value = {'project_id': 'phone-project', 'private_key': 'first'}
        self.assertEqual(self.module.send_user_push('me@example.com', is_test=True)['sent'], 1)
        first_name = self.admin.initialize_app.call_args.kwargs['name']
        self.assertEqual(self.admin.credentials.Certificate.call_args.args[0]['private_key'], 'first')
        self.firebase_settings.service_account.return_value = {'project_id': 'phone-project', 'private_key': 'second'}
        self.module.send_user_push('me@example.com', is_test=True)
        self.assertNotEqual(first_name, self.admin.initialize_app.call_args.kwargs['name'])
        self.assertNotIn('second', self.admin.initialize_app.call_args.kwargs['name'])

    def test_bad_configuration_is_safe_and_actionable(self):
        self.admin.get_app.side_effect=ValueError()
        self.admin.credentials.Certificate.side_effect=ValueError("secret detail")
        self.assertEqual(self.module.send_user_push("me@example.com", is_test=True)["status"],"configuration_error")
        self.assertNotIn("secret detail",str(self.f.log_error.call_args))

    def test_test_endpoint_targets_only_current_user_and_device(self):
        self.module.test_phone_push("a"*48)
        scope=self.f.get_all.call_args.kwargs["filters"]
        self.assertEqual(scope["user"],"me@example.com")
        self.assertEqual(set(scope),{"user","name"})
        self.assertEqual(self.f.db.exists.call_args.args[1],scope)

    def test_guest_cannot_send(self):
        self.f.session.user="Guest"
        with self.assertRaises(PermissionError):self.module.test_phone_push("a"*48)
        self.messaging.send.assert_not_called()

    def test_unregistered_phone_cannot_trigger_delivery(self):
        self.f.db.exists.return_value=False
        self.assertEqual(self.module.test_phone_push("a"*48)["status"],"no_devices")
        self.messaging.send.assert_not_called()

    def test_expired_token_removed_and_no_success_claimed(self):
        self.messaging.send.side_effect=self.messaging.UnregisteredError()
        self.assertEqual(self.module.send_user_push("me@example.com", is_test=True)["status"],"delivery_failed")
        self.f.db.delete.assert_called_once_with("Rivora Mobile Device",{"name":"device-key"})

    def test_send_failure_never_logs_token(self):
        self.messaging.send.side_effect=ValueError("private-token")
        self.assertEqual(self.module.send_user_push("me@example.com", is_test=True)["status"],"delivery_failed")
        self.assertNotIn("private-token",str(self.f.log_error.call_args))

    def seed_alert(self, **fields):
        log = {"for_user": "me@example.com", "document_type": "ToDo", "document_name": "TODO-0001", "subject": "<b>New assignment</b> &amp; review"}
        log.update(fields)
        device = types.SimpleNamespace(get_password=Mock(return_value="private-token"))
        self.f.get_doc.side_effect = lambda dt, name: log if dt == "Notification Log" else device if dt == "Rivora Mobile Device" else {"owner":"me@example.com","allocated_to":"me@example.com"}

    def test_real_alert_uses_doctype_record_and_plain_subject(self):
        self.seed_alert()
        self.module.send_user_push("me@example.com", notification_name="LOG-1")
        message = self.messaging.send.call_args.args[0]
        self.assertEqual(message.notification.title, "ToDo \u00b7 TODO-0001")
        self.assertEqual(message.notification.body, "New assignment & review")

    def test_todo_popup_highlights_reference_type_and_id(self):
        title, body = self.module.render_alert({
            "type": "Assignment", "document_type": "ToDo", "document_name": "TODO-0001",
            "reference_type": "Sales Order", "reference_name": "SO-TA-2026-0042",
            "subject": "New ToDo assignment", "message": "Confirm shipment readiness with the warehouse team.",
        })
        self.assertEqual(title, "Sales Order \u00b7 SO-TA-2026-0042")
        self.assertIn("Confirm shipment readiness", body)
        self.assertNotIn("TODO-0001", body)

    def test_quotation_is_not_labelled_as_todo(self):
        self.seed_alert(document_type="Quotation", document_name="QTN-0001", subject="Quotation submitted")
        self.module.send_user_push("me@example.com", notification_name="LOG-2")
        self.assertEqual(self.messaging.send.call_args.args[0].notification.title, "Quotation \u00b7 QTN-0001")

    def test_recipient_mismatch_prevents_delivery(self):
        self.seed_alert(for_user="other@example.com")
        self.assertEqual(self.module.send_user_push("me@example.com", notification_name="LOG-1")["status"], "notification_unavailable")
        self.messaging.send.assert_not_called()
        self.f.get_all.assert_not_called()

    def test_deleted_alert_is_not_sent(self):
        self.f.get_doc.side_effect = self.f.DoesNotExistError()
        self.assertEqual(self.module.send_user_push("me@example.com", notification_name="missing")["status"], "notification_unavailable")
        self.messaging.send.assert_not_called()

    def test_system_alert_without_document_is_suppressed(self):
        self.seed_alert(document_type=None, document_name=None, subject="Password changed")
        self.module.send_user_push("me@example.com", notification_name="LOG-1")
        self.messaging.send.assert_not_called()

    def test_test_push_is_labelled_as_a_test(self):
        self.module.test_phone_push("a"*48)
        message = self.messaging.send.call_args.args[0]
        self.assertEqual(message.notification.title, "Rivora push test")
        self.assertNotIn("ToDo",message.notification.body)

    def test_payload_text_is_bounded_and_has_no_html(self):
        self.seed_alert(document_type="Q"*140, document_name="N"*140, subject="<b>"+"S"*2000+"</b>")
        self.module.send_user_push("me@example.com", notification_name="LOG-1")
        message = self.messaging.send.call_args.args[0]
        self.assertLessEqual(len(message.notification.title),120)
        self.assertLessEqual(len(message.notification.body),500)
        self.assertNotIn("<",message.notification.body)

    def test_arabic_assignment_label_and_message(self):
        log={"for_user":"me@example.com","type":"Assignment","document_type":"Quotation","document_name":"QTN-1","subject":"Manager assigned a task"}
        title,body=self.module.render_alert(log,"ar")
        self.assertEqual(title,"عرض سعر \u00b7 QTN-1")
        self.assertIn("إسناد",body)
        self.assertNotIn("Manager assigned",body)

    def test_arabic_new_entry_and_share_messages(self):
        for fields,word in [({"name":"rivora-entry-1","type":"Alert"},"جديد"),({"type":"Share"},"مشاركة")]:
            log={"document_type":"Sales Order","document_name":"SO-1","subject":"English text",**fields}
            title,body=self.module.render_alert(log,"ar")
            self.assertEqual(title,"أمر بيع \u00b7 SO-1")
            self.assertIn(word,body)

    def test_two_phones_receive_their_own_language(self):
        log={"for_user":"me@example.com","type":"Assignment","document_type":"Quotation","document_name":"QTN-1","subject":"Assigned to you"}
        self.f.get_all.return_value=["phone-en","phone-ar"]
        def get_doc(dt,name):
            if dt=="Notification Log":return log
            if dt != "Rivora Mobile Device":return {"owner":"me@example.com"}
            return types.SimpleNamespace(get=lambda key:"ar" if name=="phone-ar" else "en",get_password=lambda *a,**kw:name+"-token")
        self.f.get_doc.side_effect=get_doc
        result=self.module.send_user_push("me@example.com",notification_name="LOG-1")
        self.assertEqual(result['sent'],2)
        en,ar=[call.args[0] for call in self.messaging.send.call_args_list]
        self.assertEqual(en.notification.title,"Quotation \u00b7 QTN-1")
        self.assertEqual(ar.notification.title,"عرض سعر \u00b7 QTN-1")
        self.assertEqual(en.notification.body,"Assigned to you")
        self.assertNotEqual(ar.notification.body,en.notification.body)

    def test_custom_message_text_is_retained_without_machine_translation(self):
        title,body=self.module.render_alert({"document_type":"ToDo","document_name":"T-1","subject":"Customer supplied description"},"ar")
        self.assertIn("المهام",title)
        self.assertEqual(body,"Customer supplied description")

    def test_anonymous_legacy_push_cannot_bypass_document_scope(self):
        self.assertEqual(self.module.send_user_push('me@example.com')['status'],'out_of_scope')
        self.messaging.send.assert_not_called()

    def test_referenced_todo_for_another_assignee_is_not_pushed(self):
        log={'for_user':'me@example.com','document_type':'ToDo','document_name':'TODO-1','subject':'Private assignment'}
        self.f.get_doc.side_effect=lambda dt,name:log if dt=='Notification Log' else {'owner':'me@example.com','allocated_to':'other'}
        self.assertEqual(self.module.send_user_push('me@example.com',notification_name='LOG-1')['status'],'notification_unavailable')
        self.messaging.send.assert_not_called()

if __name__ == "__main__":unittest.main()
