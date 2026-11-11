"""Permission-checked metadata audit and translated display strings."""
import frappe
from frappe import _
from .api import identity, TYPES


@frappe.whitelist(methods=["GET"])
def inspect_form(doctype, language="en"):
    identity()
    if language not in ("en", "ar", "hi", "ur"):
        frappe.throw(_("Unsupported mobile language"))
    if not (frappe.has_permission(doctype, "read") or frappe.has_permission(doctype, "create")):
        frappe.throw(_("Not permitted to inspect this form"), frappe.PermissionError)
    labels = {}
    fields = []
    seen = set()
    def rivora_visit(name, depth=0):
        if name in seen or depth > 4:
            return
        seen.add(name)
        for field in frappe.get_meta(name).fields:
            label = field.label or field.fieldname
            labels[label] = _(label, lang=language)
            if field.fieldtype == "Select":
                for option in (field.options or "").splitlines():
                    if option.strip():
                        labels[option.strip()] = _(option.strip(), lang=language)
            fields.append({
                "doctype": name, "fieldname": field.fieldname,
                "fieldtype": field.fieldtype, "label": labels[label],
                "required": bool(field.reqd), "hidden": bool(field.hidden),
                "native_supported": field.fieldtype in TYPES or field.fieldtype in ("Tab Break", "Section Break", "Column Break"),
                "needs_rich_editor": field.fieldtype == "Text Editor",
            })
            if field.fieldtype in ("Table", "Table MultiSelect") and field.options:
                rivora_visit(field.options, depth + 1)
    rivora_visit(doctype)
    scripts = bool(frappe.db.exists("Client Script", {"dt": doctype, "enabled": 1}))
    return {"doctype": doctype, "language": language, "labels": labels,
            "fields": fields, "client_script_enabled": scripts,
            "note": "Native metadata does not execute Client Scripts. ERPNext form mode executes the site's own form engine."}
