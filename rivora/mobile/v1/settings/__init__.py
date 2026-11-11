import frappe
from frappe import _

from rivora.mobile.v1.api_utils import (
    employee_validate,
    exception_handler,
    gen_response,
    get_employee_by_user,
)


@frappe.whitelist()
@employee_validate(methods=["GET"])
def get_hr_settings():
    try:
        settings = frappe.get_doc("HR Settings", "HR Settings")
        return gen_response(200, "HR settings get successfully", settings)
    except Exception as e:
        return exception_handler(e)
