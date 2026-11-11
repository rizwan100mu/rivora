"""Confirm check-ins created by the installed Rivora routines, without replacing them.

The outer attendance endpoint owns capture-time, geofence, site-policy and
idempotency checks. This bridge never commits a transaction. The after_insert
hook is inert unless a request-local bridge call is active.
"""
from importlib import import_module

import frappe
from frappe import _

_CAPTURE_KEY = "_rivora_employee_checkin_capture"
_SAVEPOINT = "rivora_employee_checkin_bridge"


def _reject(message, status=417):
    kind = frappe.AuthenticationError if status == 401 else frappe.PermissionError if status == 403 else frappe.ValidationError
    error = kind(message)
    error.http_status_code = status
    raise error


def capture_created_checkin(doc, method=None):
    """Employee Checkin.after_insert hook; never expose this as a public method."""
    context = getattr(frappe.local, _CAPTURE_KEY, None)
    if context is None:
        return
    if frappe.session.user != context["user"] or doc.employee != context["employee"] or doc.log_type != context["log_type"]:
        context["mismatch"] = True
        _reject(_("The created employee check-in does not match this request"), 403)
    if not doc.name:
        _reject(_("ERPNext did not assign an employee check-in number"))
    if doc.name not in context["created"]:
        context["created"].append(doc.name)


def _uploaded_photo(url):
    if not isinstance(url, str) or not url.startswith("/private/files/"):
        _reject(_("Use a private attendance image uploaded to this site"), 403)
    rows = frappe.get_list("File", filters={"file_url": url, "owner": frappe.session.user, "is_private": 1},
        fields=["name"], limit_page_length=2)
    if len(rows) != 1:
        _reject(_("The attendance image is unavailable or ambiguous"), 403)
    photo = frappe.get_doc("File", rows[0]["name"])
    photo.check_permission("read")
    if photo.owner != frappe.session.user or not photo.is_private or photo.file_url != url:
        _reject(_("The attendance image is not owned by your account"), 403)
    if photo.get("attached_to_name") or photo.get("attached_to_doctype"):
        _reject(_("Upload a new attendance image instead of reassigning an existing attachment"), 403)
    if not frappe.get_meta("Employee Checkin").has_field("attendance_image"):
        _reject(_("The Rivora attendance-image field is missing. Update the Rivora app before using images."))
    return photo


def create_employee_checkin(employee, log_type, local_time, latitude=None, longitude=None,
        odometer_reading=None, attendance_image=None, out_of_location_reason=None):
    """Return one confirmed Employee Checkin name, or raise and roll back this bridge.

    `employee` must already be resolved by the caller's authenticated identity.
    `local_time` must already be validated and converted to the site's timezone.
    An optional image is the private URL returned by the normal upload endpoint.
    The original Rivora functions create/check documents and update shift last-sync.
    """
    user = frappe.session.user
    if user == "Guest":
        _reject(_("Sign in required"), 401)
    if not employee or frappe.db.get_value("Employee", employee, "user_id") != user:
        _reject(_("Only your own employee check-ins can be created"), 403)
    if log_type not in ("IN", "OUT"):
        _reject(_("Invalid employee check-in type"))
    if (latitude is None) != (longitude is None):
        _reject(_("Provide both attendance coordinates or neither"))
    if getattr(frappe.local, _CAPTURE_KEY, None) is not None:
        _reject(_("A check-in creation is already in progress"))
    employee = import_module("rivora.mobile.v1.employee")
    if out_of_location_reason is not None:
        if log_type != "OUT" or not isinstance(out_of_location_reason, str) or not out_of_location_reason.strip():
            _reject(_("An out-of-location checkout requires OUT and a reason"))
        if employee.get_employee_settings().get("out_of_location_checkout") not in (1, True, "1"):
            _reject(_("Out-of-location checkout is disabled in Rivora Settings"), 403)
    photo = _uploaded_photo(attendance_image) if attendance_image else None
    location = f"{latitude},{longitude}" if latitude is not None else None
    outer_response = frappe.local.response
    response = frappe._dict()
    context = {"user": user, "employee": employee, "log_type": log_type, "created": [], "mismatch": False}
    frappe.db.savepoint(_SAVEPOINT)
    setattr(frappe.local, _CAPTURE_KEY, context)
    frappe.local.response = response
    try:
        if out_of_location_reason is not None:
            employee.create_out_location_checkout(out_time=str(local_time), reason=out_of_location_reason.strip(), location=location)
        else:
            employee.create_employee_log(log_type=log_type, log_time=str(local_time), location=location,
                odometer_reading=odometer_reading)
        status = response.get("http_status_code")
        try:
            status = int(status)
        except (TypeError, ValueError):
            _reject(_("The Rivora check-in routine did not confirm a result"))
        if status < 200 or status >= 300:
            _reject(response.get("message") or _("The Rivora check-in routine failed"), status if 400 <= status <= 599 else 417)
        if context["mismatch"] or len(context["created"]) != 1:
            _reject(_("ERPNext did not confirm exactly one matching employee check-in"))
        name = context["created"][0]
        persisted = frappe.db.get_value("Employee Checkin", name, ["employee", "log_type"], as_dict=True)
        if not persisted or persisted.get("employee") != employee or persisted.get("log_type") != log_type:
            _reject(_("The employee check-in was not persisted for this account"), 403)
        if photo is not None:
            checkin = frappe.get_doc("Employee Checkin", name)
            if checkin.employee != employee or checkin.log_type != log_type:
                _reject(_("The attendance image target does not match this check-in"), 403)
            photo.attached_to_doctype = "Employee Checkin"
            photo.attached_to_name = name
            photo.attached_to_field = "attendance_image"
            # Original Rivora self-service also saves its own upload and just-created
            # Employee Checkin with ignore_permissions; all ownership checks above
            # are explicit, and document validation and hooks still run.
            photo.save(ignore_permissions=True)
            checkin.attendance_image = attendance_image
            checkin.save(ignore_permissions=True)
        return name
    except Exception:
        frappe.db.rollback(save_point=_SAVEPOINT)
        raise
    finally:
        frappe.local.response = outer_response
        delattr(frappe.local, _CAPTURE_KEY)
