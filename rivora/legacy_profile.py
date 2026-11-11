"""Read-only mobile presentation profile for the authenticated user."""
import frappe
from .api import identity


@frappe.whitelist(methods=["GET"])
def get_profile():
    # No caller-supplied user/employee or business-permission changes.
    identity()
    return {
        "user": frappe.session.user,
        "user_type": frappe.db.get_value("User", frappe.session.user, "user_type"),
    }
