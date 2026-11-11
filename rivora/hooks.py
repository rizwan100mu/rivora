"""Combined Rivora hooks: original employee workflows plus current mobile features."""
from copy import deepcopy
from . import _employee_hooks as employee
app_name = "rivora"
app_title = "Rivora"
app_publisher = "Rizwan"
app_description = "Rivora workforce and ERP mobile"
app_email = ""
app_license = "See LICENSES and THIRD_PARTY_NOTICES.md"
required_apps = ["erpnext", "hrms"]
doc_events = deepcopy(employee.doc_events)
for doctype, event, handler in [
    ("*", "before_validate", "rivora.transaction_validation.before_validate"),
    ("*", "after_insert", "rivora.entry_notifications.queue_entry_alert"),
    ("Notification Log", "after_insert", "rivora.api.push_update"),
    ("ToDo", "after_insert", "rivora.todo_notifications.queue_assignment"),
    ("ToDo", "on_update", "rivora.todo_notifications.queue_assignment"),
]:
    events = doc_events.setdefault(doctype, {})
    existing = events.get(event, [])
    if isinstance(existing, str): existing = [existing]
    events[event] = list(dict.fromkeys([*existing, handler]))
scheduler_events = deepcopy(employee.scheduler_events)
scheduler_events.setdefault("daily", []).extend(["rivora.api.clean_devices", "rivora.live_location.cleanup"])
doctype_js = deepcopy(employee.doctype_js)
jinja = deepcopy(employee.jinja)
fixtures = deepcopy(employee.fixtures)
before_tests = employee.before_tests
before_install = "rivora.lifecycle.assert_installable"
before_migrate = "rivora.lifecycle.assert_installable"
after_install = "rivora.lifecycle.after_install"
after_migrate = "rivora.lifecycle.after_migrate"
app_include_css = "/assets/rivora/css/rivora.css"
app_include_js = "/assets/rivora/js/rivora_mobile_language.js"
app_logo_url = "/assets/rivora/images/rivora-mark.svg"
add_to_apps_screen = [{"name":"rivora", "logo":app_logo_url, "title":"Rivora", "route":"/app/rivora", "has_permission":"rivora.desktop.has_app_permission"}]
