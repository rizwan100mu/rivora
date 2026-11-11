"""Read permitted companies and use Frappe's existing session defaults contract."""
import frappe
from frappe import _
from .api import identity


def _companies():
    # get_list enforces the current user's role and User Permission restrictions.
    return [row.name for row in frappe.get_list("Company", fields=["name"],
        order_by="name asc", limit_page_length=0)]


def _company_enabled():
    settings = frappe.get_single("Session Default Settings")
    return any(row.ref_doctype == "Company" for row in settings.session_defaults)


@frappe.whitelist(methods=["GET"])
def get_context():
    employee = identity()
    companies = _companies()
    default = frappe.defaults.get_user_default("Company")
    if default not in companies:
        default = companies[0] if len(companies) == 1 else None
    profile = frappe.db.get_value("Employee", employee, "employee_name")
    return {"employee_name": profile, "company": default, "companies": companies,
            "session_company_enabled": _company_enabled()}


@frappe.whitelist(methods=["POST"])
def set_company(company):
    identity()
    if not isinstance(company, str) or company not in _companies():
        frappe.throw(_("You do not have access to this company"), frappe.PermissionError)
    if not _company_enabled():
        frappe.throw(_("Add Company in Session Default Settings first"))
    from frappe.core.doctype.session_default_settings.session_default_settings import set_session_default_values
    result = set_session_default_values({"company": company})
    if result != "success":
        frappe.throw(_("Could not update the session company"))
    return get_context()
