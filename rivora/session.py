"""Rivora authentication and profile endpoints using Frappe's own login flow.

No upstream Rivora backend is imported. Password policy, lockout, OTP, IP restrictions,
login hours and session expiry remain enforced by Frappe LoginManager.
"""
import frappe
from frappe import _
from frappe.utils import cint
from .api import identity


def _finish_login():
    if frappe.session.user == "Guest":
        frappe.throw(_("Complete sign in first"), frappe.AuthenticationError)
    employee = identity()
    from frappe.sessions import get_csrf_token
    return {
        "user": frappe.session.user,
        "user_type": frappe.db.get_value("User", frappe.session.user, "user_type"),
        "employee_id": employee,
        "session_id": frappe.session.sid,
        "csrf_token": get_csrf_token(),
    }


def _login_response():
    result = frappe.local.login_manager.login()
    if result is False:
        response = frappe.local.response
        if response.get("tmp_id") and response.get("verification"):
            return {"data": {"two_factor_required": True, "tmp_id": response["tmp_id"]}}
        frappe.throw(_("Sign in was not completed. Check password reset requirements in your browser."), frappe.AuthenticationError)
    return _finish_login()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def login(usr, pwd, unique_id=None):
    # Run even when an old session is attached; never use the old session as proof
    # that the newly supplied account has authenticated.
    frappe.form_dict.update({"usr": usr, "pwd": pwd})
    frappe.form_dict.pop("tmp_id", None)
    frappe.form_dict.pop("otp", None)
    return _login_response()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def verify_2fa_otp(tmp_id, otp):
    if not tmp_id or not otp:
        frappe.throw(_("Verification details are required"), frappe.AuthenticationError)
    # LoginManager retrieves the credentials cached by its own first step.
    from frappe.twofactor import get_cached_user_pass
    frappe.form_dict.update({"tmp_id": tmp_id, "otp": otp})
    frappe.form_dict.pop("usr", None)
    frappe.form_dict.pop("pwd", None)
    user, password = get_cached_user_pass()
    if not user or not password:
        frappe.throw(_("Verification expired. Sign in again."), frappe.AuthenticationError)
    return _login_response()


@frappe.whitelist(methods=["POST"])
def logout():
    frappe.local.login_manager.logout()
    return {"signed_out": True}


@frappe.whitelist(methods=["GET"])
def get_dashboard():
    employee = identity()
    # The authenticated employee mapping is resolved server-side. Only a small
    # self-profile is read here; no cross-employee search is accepted.
    profile = frappe.db.get_value("Employee", employee,
        ["employee_name", "company", "branch"], as_dict=True) or {}
    return {"employee": employee, **profile}


@frappe.whitelist(methods=["GET"])
def notification_list(start=0, page_length=30):
    identity()
    from .notification_history import list_notifications
    return list_notifications(start=start, page_length=page_length)


@frappe.whitelist(methods=["GET"])
def get_feed(start=0, page_length=30):
    identity()
    rows = frappe.get_list("Rivora Mobile Post", filters={"publish": 1},
        fields=["name", "title", "post_type", "post_datetime", "user"],
        order_by="post_datetime desc, name desc", start=max(0,cint(start)),
        page_length=min(101,max(1,cint(page_length))))
    return rows


@frappe.whitelist(methods=["POST"])
def rivora_employee_device_info(platform=None, unique_id=None, app_version=None):
    identity()
    import hashlib
    import re
    if not re.fullmatch(r"[a-f0-9]{48}", unique_id or ""):
        frappe.throw(_("Invalid device ID"))
    if platform != "Android" or len(app_version or "") > 32:
        frappe.throw(_("Invalid device details"))
    key = hashlib.sha256(f"{frappe.session.user}:{unique_id}".encode()).hexdigest()
    doc = frappe.get_doc("Rivora Mobile Client Device", key) if frappe.db.exists("Rivora Mobile Client Device", key) else frappe.get_doc({
        "doctype": "Rivora Mobile Client Device", "device_key": key,
        "user": frappe.session.user, "device_id": unique_id,
    })
    # Internal bookkeeping is always scoped to the current authenticated user.
    if doc.user != frappe.session.user:
        frappe.throw(_("Device is not owned by your account"), frappe.PermissionError)
    doc.platform = platform
    doc.app_version = app_version
    doc.save(ignore_permissions=True)
    return {"registered": True}
