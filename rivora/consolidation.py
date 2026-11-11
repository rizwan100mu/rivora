"""Single-app installation guard and original Rivora setup lifecycle."""
import frappe
from frappe import _


def assert_single_app_install():
    if "employee_self_service" in frappe.get_installed_apps():
        frappe.throw(_("A separate Employee Self Service app is already installed. This consolidated build requires a reviewed ownership migration on a staging clone. Do not uninstall it or delete its data to bypass this check."))
    # A failed earlier install can leave a separately owned module behind. A module
    # owned by the uninstalled Rivora app must be reviewed before schema sync.
    owner = frappe.db.get_value("Module Def", "Employee Self Service", "app_name")
    if owner == "employee_self_service":
        frappe.throw(_("Existing Rivora module ownership was found. Review it on a staging clone before consolidating; no automatic ownership transfer is performed."))


def after_install():
    from .setup import after_install as original_employee_setup
    from .install import after_install as rivora_setup
    original_employee_setup()
    rivora_setup()


def after_migrate():
    from .setup import after_install as original_employee_setup
    from .desktop import ensure_workspace
    original_employee_setup()
    ensure_workspace()
