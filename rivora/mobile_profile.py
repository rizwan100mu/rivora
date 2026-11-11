"""Read-only mobile presentation profile for the authenticated user."""
import frappe
from .api import identity


@frappe.whitelist(methods=["GET"])
def get_profile():
    # No caller-supplied user/employee or business-permission changes.
    identity()
    from .presentation import profile_policy
    user_type = frappe.db.get_value("User", frappe.session.user, "user_type")
    return {
        "user": frappe.session.user,
        "user_type": user_type,
        **profile_policy(user_type),
    }
