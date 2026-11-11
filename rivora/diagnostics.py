"""Read-only parity diagnostics for an administrator running bench execute.

This module does not invoke Rivora business endpoints, change settings, inspect
business document contents, return credentials, or include Client Script bodies.
"""
import importlib
import re

import frappe


ESS_SCHEMA = (
    "Rivora Settings", "Rivora Attendance Log Settings",
    "Rivora Notification Settings", "Rivora Notification", "Rivora Notification Template",
    "Rivora Notification Log", "Rivora Workflow Settings", "Rivora Workflow Documents",
    "Rivora Employee Device Registration", "Rivora Employee Device Info", "Rivora Location",
    "Rivora Location Assignment", "Rivora Post", "Rivora Documents", "Rivora Visit",
    "Rivora Petty Expense", "Rivora Employee Target Entry", "Rivora Notice Board",
)

ESS_PROBES = (
    "rivora.mobile.v1.employee.create_employee_log",
    "rivora.mobile.v1.employee.get_dashboard",
    "rivora.mobile.v1.employee.get_employee_settings",
    "rivora.mobile.v1.todo.get_todo_list",
    "rivora.mobile.v1.payment.make_payment",
    "rivora.mobile.v1.order.create_order",
    "rivora.mobile.v1.quotation.create_quotation",
    "rivora.mobile.v1.transactions.get_transactions",
    "rivora.mobile.v1.translation.get_translation",
)


def _error_kind(error):
    # Exception messages and tracebacks can contain request/site configuration.
    # Return only a bounded exception class name, never str(error) or traceback.
    return re.sub(r"[^A-Za-z0-9_]", "", type(error).__name__)[:80]


def _app_info(name):
    try:
        module = importlib.import_module(name)
        version = str(getattr(module, "__version__", "not_declared"))
        if not re.fullmatch(r"[A-Za-z0-9._+\-]{1,80}", version):
            version = "not_reported"
        return {"app": name, "importable": True, "version": version}
    except Exception as error:
        return {"app": name, "importable": False, "error_type": _error_kind(error)}


def _doctype_info(name):
    if not frappe.db.exists("DocType", name):
        return {"doctype": name, "exists": False, "fields": []}
    try:
        meta = frappe.get_meta(name)
        fields = []
        for field in meta.fields:
            # HTML/Code options can contain executable source. Do not include
            # them. Select values and schema reference names are metadata only.
            options = None
            if field.fieldtype == "Select":
                options = (field.options or "").splitlines()
            elif field.fieldtype in ("Link", "Table", "Table MultiSelect", "Dynamic Link"):
                options = field.options or ""
            fields.append({
                "fieldname": field.fieldname,
                "fieldtype": field.fieldtype,
                "label": field.label or field.fieldname,
                "options": options,
                "required": bool(field.reqd),
                "read_only": bool(field.read_only),
                "hidden": bool(field.hidden),
            })
        return {"doctype": name, "exists": True, "fields": fields}
    except Exception as error:
        return {"doctype": name, "exists": True, "error_type": _error_kind(error), "fields": []}


def audit_employee_parity():
    """Run using: bench --site SITE execute rivora.diagnostics.audit_employee_parity.

    This intentionally is not an HTTP-whitelisted endpoint. Bench normally uses
    Administrator; the returned Checkin permissions therefore are NOT proof of
    permissions for the phone's Employee/Training account.
    """
    if frappe.session.user != "Administrator":
        frappe.only_for("System Manager")

    installed = list(frappe.get_installed_apps())
    result = {
        "audit_mode": "read_only_metadata_and_import_readiness",
        "backend_mode": "bundled_in_rivora",
        "bundled_employee_source_version": "2.2.5",
        "separate_employee_install_present": "employee_self_service" in installed,
        "evaluated_user": frappe.session.user,
        "permission_scope_note": "Checkin permissions belong only to evaluated_user, not automatically to the signed-in phone employee.",
        "installed_apps": [_app_info(name) for name in installed],
        "employee_backend_bundled": True,
        "rivora_installed_on_site": "rivora" in installed,
        "doctypes": [_doctype_info(name) for name in ("ToDo", "Leave Request", "Employee Checkin")],
        "employee_checkin_permissions": {
            "read": bool(frappe.has_permission("Employee Checkin", "read")),
            "create": bool(frappe.has_permission("Employee Checkin", "create")),
        },
        "employee_schema": [{"doctype": name, "exists": bool(frappe.db.exists("DocType", name))} for name in ESS_SCHEMA],
        "client_scripts": [],
        "backend_readiness": [],
        "limitations": [
            "No business endpoints were called and no checkin was created.",
            "Metadata does not reveal options assigned dynamically while Client Scripts execute.",
            "Import readiness does not prove endpoint behavior or version compatibility.",
            "No script bodies, business document contents, credentials or site configuration are returned.",
        ],
    }
    if frappe.db.exists("DocType", "Client Script"):
        try:
            rows = frappe.get_all("Client Script", filters={
                "enabled": 1, "dt": ["in", ["ToDo", "Leave Request", "Employee Checkin"]],
            }, fields=["name", "dt"], order_by="dt asc, name asc", limit_page_length=200)
            result["client_scripts"] = [{"name": row.name, "doctype": row.dt} for row in rows]
            result["client_scripts_may_be_truncated"] = len(rows) == 200
        except Exception as error:
            result["client_script_audit_error"] = _error_kind(error)
    for path in ESS_PROBES:
        try:
            endpoint = frappe.get_attr(path)
            result["backend_readiness"].append({"method": path, "importable": True, "callable": callable(endpoint)})
        except Exception as error:
            result["backend_readiness"].append({"method": path, "importable": False, "error_type": _error_kind(error)})
    result["missing_employee_schema"] = [row["doctype"] for row in result["employee_schema"] if not row["exists"]]
    return result
