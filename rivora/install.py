"""Create only the optional site-local request DocType if it is absent.
Existing Leave Request metadata, permissions and records are left untouched.
"""
import frappe


def after_install():
    from .live_location import ensure_indexes
    ensure_indexes()
    from .presentation import initialize_home_user_types
    initialize_home_user_types()
    # Fresh installations already have the new schema and initial rows.
    # Mark the upgrade-only migration complete so a later empty list stays empty.
    patch = "rivora.patches.simplify_home_user_types"
    if not frappe.db.exists("Patch Log", {"patch": patch}):
        frappe.get_doc({"doctype": "Patch Log", "patch": patch}).insert(ignore_permissions=True)
    if frappe.db.exists("DocType", "Leave Request"):
        return
    frappe.get_doc({
        "doctype": "DocType", "name": "Leave Request", "module": "Rivora",
        "custom": 1, "autoname": "naming_series:", "track_changes": 1,
        "field_order": ["naming_series", "employee", "leave_month", "company", "reason"],
        "fields": [
            {"fieldname":"naming_series", "label":"Series", "fieldtype":"Select", "options":"RW-LR-.YYYY.-", "default":"RW-LR-.YYYY.-", "reqd":1},
            {"fieldname":"employee", "label":"Employee", "fieldtype":"Link", "options":"Employee", "reqd":1},
            {"fieldname":"leave_month", "label":"Month", "fieldtype":"Select", "options":"January\nFebruary\nMarch\nApril\nMay\nJune\nJuly\nAugust\nSeptember\nOctober\nNovember\nDecember"},
            {"fieldname":"company", "label":"Company", "fieldtype":"Link", "options":"Company"},
            {"fieldname":"reason", "label":"Reason", "fieldtype":"Text Editor"},
        ],
        "permissions": [
            {"role":"System Manager", "read":1, "write":1, "create":1, "delete":1},
            {"role":"Employee", "read":1, "write":1, "create":1, "if_owner":1},
        ],
    }).insert(ignore_permissions=True)
