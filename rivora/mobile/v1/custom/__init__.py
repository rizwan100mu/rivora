import frappe

from rivora.mobile.v1.api_utils import (
    employee_validate,
    exception_handler,
    gen_response,
)


@frappe.whitelist()
@employee_validate(methods=["GET"])
def get_rivora_custom_fields(doctype_name):
    try:
        if not frappe.db.exists("Rivora Custom Field", doctype_name):
            return gen_response(200, "No custom fields found for this form", [])
        custom_field_doc = frappe.get_doc("Rivora Custom Field", doctype_name)
        return gen_response(
            200, "Custom fields retrieved successfully", custom_field_doc
        )
    except Exception as e:
        return exception_handler(e)
