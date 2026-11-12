"""Mobile notifications belong to document owners or current assignees only."""
import frappe

def personal_document(doctype, name, user):
    if not doctype or not name or not user or user == 'Guest':
        return False
    try:
        doc = frappe.get_doc(doctype, name)
    except frappe.DoesNotExistError:
        return False
    if not frappe.has_permission(doctype, 'read', doc=doc, user=user):
        return False
    # An allocated ToDo belongs to the assignee, even if a manager created it.
    if doctype == 'ToDo':
        return doc.get('allocated_to') == user
    if doc.get('owner') == user:
        return True
    return bool(frappe.db.exists('ToDo', {'reference_type': doctype, 'reference_name': name,
        'allocated_to': user, 'status': 'Open'}))

def personal_alert(log, user):
    doctype = log.get('document_type') or log.get('reference_document')
    name = log.get('document_name') or log.get('reference_name')
    # No unreferenced business message can bypass ownership checks.
    return personal_document(doctype, name, user)
