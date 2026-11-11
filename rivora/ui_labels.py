"""Translate metadata labels only; never change field names or saved values."""
import frappe
from frappe import _


@frappe.whitelist(methods=['GET'])
def get_form_labels(doctype, language):
    if frappe.session.user == 'Guest' or not any(
        frappe.has_permission(doctype, permission) for permission in ('read', 'create', 'write')
    ):
        frappe.throw(_('No permission to view this form'), frappe.PermissionError)
    return form_labels(doctype, language)


def form_labels(doctype, language):
    if language not in ('ar', 'en', 'hi', 'ur') or language == 'en':
        return {}
    result = {}
    visited = set()

    def collect(name, depth=0):
        if name in visited:
            return
        visited.add(name)
        meta = frappe.get_meta(name)
        result[name] = _(name, lang=language)
        for field in meta.fields:
            label = field.get('label')
            if isinstance(label, str) and label:
                result[label] = _(label, lang=language)
            if depth == 0 and field.fieldtype in ('Table', 'Table MultiSelect') and field.options:
                collect(field.options, depth + 1)
    collect(doctype)
    return {key: value for key, value in result.items() if isinstance(value, str) and value != key}
