"""Repair the legacy short Page route without deleting records or role policies."""
import frappe

def execute():
    for slug,route in [('rivora_employee_location_tr','employee-location-tr'),('rivora_employee_location_tracker','employee-location-tracker')]:
        # Preserve the existing Page role rows when forcing asset metadata sync.
        roles=None
        if frappe.db.exists('Page',route):
            roles=[row.as_dict() for row in frappe.get_doc('Page',route).get('roles') or []]
        frappe.reload_doc('rivora','page',slug,force=True)
        if roles is not None:
            doc=frappe.get_doc('Page',route)
            doc.set('roles',[{'role':row['role']} for row in roles])
            doc.flags.do_not_update_json=True
            doc.save(ignore_permissions=True)
        frappe.clear_cache(doctype='Page')
