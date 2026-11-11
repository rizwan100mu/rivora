"""Narrow adapters to the Rivora backend bundled in the Rivora package.

Original Rivora schema, controllers, hooks, schedulers, settings and licenses remain
bundled under the Rivora namespace. They do not require a second installed app.
"""
from importlib import import_module
import frappe
from frappe import _


def require_backend():
    if "employee_self_service" in frappe.get_installed_apps():
        frappe.throw(_("This consolidated Rivora build must not run beside a separately installed legacy employee-service app. Use a reviewed migration on a staging clone."))
    if "rivora" not in frappe.get_installed_apps():
        frappe.throw(_("Install rivora on this site first."))


def call_employee(module, function, **kwargs):
    require_backend()
    # Private helper; callers use fixed method names, never user-supplied dispatch.
    method = getattr(import_module("rivora.mobile.v1." + module), function)
    previous = frappe.local.response
    frappe.local.response = frappe._dict()
    try:
        result = method(**kwargs)
        response = frappe.local.response
        status = int(response.get("http_status_code") or 200)
        if status >= 400:
            frappe.throw(str(response.get("message") or _("Rivora request failed")))
        return response.get("data") if "data" in response else result
    finally:
        frappe.local.response = previous
