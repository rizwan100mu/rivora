"""Desk registration. These helpers do not grant document permissions."""
import json
from pathlib import Path
import frappe


def has_app_permission():
    if frappe.session.user == "Guest":
        return False
    return any(frappe.has_permission(doctype, "read") for doctype in
        ("ToDo", "Rivora Mobile Settings", "Rivora Mobile Post"))


def ensure_workspace():
    # Standard workspace sync normally imports this JSON. Repair a missing entry
    # on existing installs without overwriting an existing customized workspace.
    if frappe.db.exists("Workspace", "Rivora"):
        return
    path = Path(__file__).parent / "rivora" / "workspace" / "rivora" / "rivora.json"
    frappe.get_doc(json.loads(path.read_text(encoding="utf-8"))).insert(ignore_permissions=True)
