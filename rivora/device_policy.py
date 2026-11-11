"""Apply the original Rivora device policy before creating a mobile session."""
import frappe
from frappe import _


def before_mobile_login(login_manager):
    command = frappe.form_dict.get("cmd") or ""
    path = getattr(getattr(frappe.local, "request", None), "path", "")
    methods = ("rivora.session.login", "rivora.session.verify_2fa_otp")
    if command not in methods and not any(path.endswith("/" + name) for name in methods):
        return
    from .employee_services import require_backend
    require_backend()
    settings = frappe.get_single("Rivora Settings")
    if not settings.get("enable_device_restrictions"):
        return
    device_id = getattr(frappe.flags, "rivora_device_id", None)
    if not device_id:
        frappe.throw(_("Device identity is required by Rivora settings. Sign in again."), frappe.AuthenticationError)
    employee = frappe.db.get_value("Employee", {"user_id": login_manager.user, "status": "Active"}, "name")
    if not employee:
        frappe.throw(_("An active linked employee is required"), frappe.PermissionError)
    from rivora.mobile.v1.employee import register_device
    register_device(employee, device_id)
