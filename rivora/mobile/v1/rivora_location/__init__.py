import frappe
from frappe.utils import today

from rivora.mobile.v1.api_utils import (
    check_workflow_exists,
    employee_validate,
    exception_handler,
    gen_response,
    get_attachments,
    get_employee_by_user,
    get_employee_settings,
    get_global_defaults,
)


@frappe.whitelist()
@employee_validate(methods=["GET"])
def get_location():
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["name", "branch"])
        employee_settings = get_employee_settings()
        geofencing_based_on = employee_settings.get("geofencing_based_on")
        # if not employee_settings.get("location_validate"):
        # if not emp_data.get("branch") and geofencing_based_on == "Branch":
        # 	return gen_response(500, "Branch not assigned to employee!")

        # if geofencing_based_on == "Rivora Location":
        # 	filters = [
        # 		["from_date", "<=", today()],
        # 		["to_date", ">=", today()],
        # 		["employee", "=", emp_data.get("name")],
        # 	]
        # 	location_assignments = frappe.get_all(
        # 		"Rivora Location Assignment", filters=filters, fields=["name"]
        # 	)
        # if len(location_assignments) < 1:
        # 	return gen_response(500, "Rivora Location not assigned to employee!")

        locations = []
        if geofencing_based_on == "Branch":
            if emp_data.get("branch"):
                branch_doc = frappe.get_doc("Branch", emp_data.get("branch"))
                locations.append(
                    {
                        "latitude": branch_doc.get("latitude"),
                        "longitude": branch_doc.get("longitude"),
                        "radius": branch_doc.get("radius"),
                    }
                )
        if geofencing_based_on == "Rivora Location":
            filters = [
                ["from_date", "<=", today()],
                ["to_date", ">=", today()],
                ["employee", "=", emp_data.get("name")],
            ]
            location_assignment = frappe.get_all(
                "Rivora Location Assignment", filters=filters, fields=["name", "location"]
            )
            for row in location_assignment:
                location_doc = frappe.get_doc("Rivora Location", row.location)
                locations.append(
                    {
                        "latitude": location_doc.get("latitude"),
                        "longitude": location_doc.get("longitude"),
                        "radius": location_doc.get("radius"),
                    }
                )
        return gen_response(200, "Rivora Location get successfully", locations)
    except Exception as e:
        return exception_handler(e)
