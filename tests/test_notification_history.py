import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: v for k, v in sys.modules.items() if k == "frappe" or k.startswith("frappe.")}
        f = types.ModuleType("frappe")
        f.whitelist = lambda **kw: lambda fn: fn
        f._ = lambda text: text
        f.AuthenticationError = PermissionError
        f.DoesNotExistError = KeyError
        f.has_permission = Mock(return_value=True)
        f.get_doc = Mock(return_value={"owner":"me@example.com"})
        f.throw = lambda text, kind=ValueError: (_ for _ in ()).throw(kind(text))
        f.session = types.SimpleNamespace(user="me@example.com")
        self.exists = {"Notification Log", "Rivora Notification Log"}
        f.db = types.SimpleNamespace(exists=lambda dt, name: isinstance(name,str) and name in self.exists)
        self.fields = {"Notification Log": {"for_user", "subject", "read", "document_type", "document_name", "description", "title"},
            "Rivora Notification Log": {"recipient", "subject", "message", "read", "reference_document", "reference_name"}}
        f.get_meta = lambda dt: types.SimpleNamespace(has_field=lambda key: key in self.fields[dt])
        self.rows = {"Notification Log": [], "Rivora Notification Log": []}
        def read(dt, **kw):
            owner = "for_user" if dt == "Notification Log" else "recipient"
            data = [row for row in self.rows[dt] if row[owner] == kw["filters"][owner]]
            data.sort(key=lambda row: (row["creation"], row["name"]), reverse=True)
            return [{k: v for k, v in row.items() if k in kw["fields"]} for row in data[kw["start"]:kw["start"]+kw["page_length"]]]
        f.get_all = Mock(side_effect=read)
        sys.modules["frappe"] = f
        utils = types.ModuleType("frappe.utils");utils.cint = lambda v: int(v or 0)
        sys.modules["frappe.utils"] = utils
        path = Path(__file__).parents[1]/"rivora/notification_history.py"
        scope_spec=importlib.util.spec_from_file_location('rivora.notification_scope',Path(__file__).parents[1]/'rivora/notification_scope.py')
        scope=importlib.util.module_from_spec(scope_spec);scope_spec.loader.exec_module(scope)
        sys.modules['rivora.notification_scope']=scope
        spec = importlib.util.spec_from_file_location("rivora.history_under_test", path)
        self.module = importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.f = f

    def tearDown(self):
        for key in list(sys.modules):
            if key == "frappe" or key.startswith("frappe."): sys.modules.pop(key)
        sys.modules.update(self.saved)

    def seed(self):
        self.rows["Notification Log"] = [
            dict(name="ERP-1", creation="2026-10-31 09:00:00", subject="ERP alert", document_type="ToDo", document_name="TODO-1", for_user="me@example.com"),
            dict(name="ERP-other", creation="2026-10-31 12:00:00", subject="Private", for_user="other@example.com")]
        self.rows["Rivora Notification Log"] = [
            dict(name="Rivora-1", creation="2026-10-31 10:00:00", message="Rivora alert", reference_document="ToDo", reference_name="TODO-1", recipient="me@example.com", token="secret"),
            dict(name="Rivora-other", creation="2026-10-31 13:00:00", recipient="other@example.com")]

    def test_combines_sources_newest_first_without_employee_link_or_tokens(self):
        self.seed(); rows = self.module.list_notifications()
        self.assertEqual([r["name"] for r in rows], ["Rivora-1", "ERP-1"])
        self.assertNotIn("token", rows[0])
        self.assertEqual(rows[0]["notification_source"], "Rivora Notification Log")
        for call in self.f.get_all.call_args_list:
            self.assertEqual(list(call.kwargs["filters"].values()), ["me@example.com"])

    def test_guest_rejected_before_any_query(self):
        self.f.session.user = "Guest"
        with self.assertRaises(PermissionError): self.module.list_notifications()
        self.f.get_all.assert_not_called()

    def test_no_employee_installation_still_reads_erp(self):
        self.seed();self.exists.remove("Rivora Notification Log")
        self.assertEqual([r["name"] for r in self.module.list_notifications()], ["ERP-1"])

    def test_global_pagination_does_not_skip_one_source(self):
        self.seed()
        self.assertEqual(self.module.list_notifications(start=1, page_length=1)[0]["name"], "ERP-1")
        for call in self.f.get_all.call_args_list:
            self.assertEqual(call.kwargs["page_length"], 200)
            self.assertEqual(call.kwargs["start"], 0)

    def test_limits_and_optional_schema_fields(self):
        self.module.list_notifications(start=-5, page_length=999)
        for call in self.f.get_all.call_args_list:
            self.assertEqual(call.kwargs["page_length"], 200)
            self.assertNotIn("email_content", call.kwargs["fields"])

    def test_missing_recipient_field_fails_closed(self):
        self.fields["Notification Log"].remove("for_user")
        with self.assertRaises(ValueError): self.module.list_notifications()
        self.f.get_all.assert_not_called()

    def test_oversized_offset_rejected_before_query(self):
        with self.assertRaises(ValueError): self.module.list_notifications(start=10001)
        self.f.get_all.assert_not_called()

    def test_read_and_unread_alerts_are_retained(self):
        self.seed();self.rows["Notification Log"][0]["read"] = 1
        self.rows["Rivora Notification Log"][0]["read"] = 0
        self.assertEqual([r["read"] for r in self.module.list_notifications()], [0, 1])

    def test_unrelated_referenced_alerts_are_hidden_even_if_for_user_matches(self):
        self.seed()
        self.f.get_doc.return_value={'owner':'other','allocated_to':'other'}
        self.assertEqual(self.module.list_notifications(),[])

    def test_scope_is_confirmed_for_new_mobile_client(self):
        self.seed()
        result=self.module.personal_notifications()
        self.assertEqual(result['scope'],'owner_or_assignee')
        self.assertEqual(len(result['notifications']),2)

    def test_filtering_scans_past_unrelated_page(self):
        self.rows['Notification Log']=[dict(name=f'OTHER-{i}',creation=f'{1000-i:04}',document_type='ToDo',document_name=f'OTHER-{i}',for_user='me@example.com') for i in range(201)]
        self.rows['Notification Log'].append(dict(name='OWN',creation='0001',document_type='ToDo',document_name='OWN',for_user='me@example.com'))
        self.f.get_doc.side_effect=lambda dt,name:{'owner':'me@example.com' if name=='OWN' else 'other'}
        result=self.module.list_notifications(page_length=1)
        self.assertEqual([r['name'] for r in result],['OWN'])
        self.assertIn(200,[c.kwargs['start'] for c in self.f.get_all.call_args_list])

if __name__ == "__main__": unittest.main()
