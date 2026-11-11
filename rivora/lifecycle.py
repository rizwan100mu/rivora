"""Fresh consolidated install only; existing ownership requires staged migration."""
import frappe
def assert_installable():
    conflicts = set(frappe.get_installed_apps()) & {"employee_self_service", "rizora_workforce", "ess_mobile_extras"}
    if conflicts:
        frappe.throw("Rivora requires a reviewed staging ownership/data migration for existing apps: " + ", ".join(sorted(conflicts)) + ". Do not uninstall old apps or delete their records to bypass this check.")
    old = frappe.get_all("DocType", filters={"name": ["like", "ESS %"]}, pluck="name", limit_page_length=1)
    if old:
        frappe.throw("Existing legacy employee schema found. Apply a reviewed staging migration before installing Rivora.")
def after_install():
    from .setup import after_install as employee_setup
    from .install import after_install as mobile_setup
    from .desktop import ensure_workspace
    employee_setup()
    mobile_setup()
    ensure_workspace()
def after_migrate():
    from .setup import after_install as employee_setup
    from .live_location import ensure_indexes
    from .desktop import ensure_workspace
    employee_setup()
    ensure_indexes()
    ensure_workspace()
