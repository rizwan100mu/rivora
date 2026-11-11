"""Preserve existing User Types when replacing the old configurable Home rules."""
import frappe


def execute():
    from rivora.presentation import initialize_home_user_types
    # Removed Single DocType fields remain in tabSingles after model sync.
    # Read only the legacy mode; runtime policy never consults it.
    rows = frappe.db.sql(
        "SELECT value FROM `tabSingles` WHERE doctype=%s AND field=%s",
        ("Rivora Mobile Settings", "dashboard_configuration"),
    )
    initialize_home_user_types(legacy_mode=rows[0][0] if rows else None)
