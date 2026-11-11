"""Mobile-only ToDo assignment alerts, independent of ERPNext notification preferences."""
import hashlib
import frappe
from frappe import _


def queue_assignment(doc, method=None):
    if frappe.flags.get('in_install') or frappe.flags.get('in_migrate'):
        return
    if not doc.get('allocated_to') or doc.get('status') != 'Open':
        return
    previous = doc.get_doc_before_save()
    if previous and previous.get('allocated_to') == doc.get('allocated_to'):
        return
    try:
        frappe.enqueue('rivora.todo_notifications.deliver_assignment', queue='short',
            enqueue_after_commit=True, name=doc.name, user=doc.allocated_to,
            assigned_at=str(doc.modified))
    except Exception:
        frappe.log_error(title='Rivora assignment alert could not be queued',
            message='Check the short queue and background workers.')


def deliver_assignment(name, user, assigned_at):
    if not frappe.db.exists('ToDo', name):
        return
    doc = frappe.get_doc('ToDo', name)
    if doc.get('allocated_to') != user or doc.get('status') != 'Open':
        return
    if user == 'Guest' or not frappe.db.get_value('User', user, 'enabled'):
        return
    if not frappe.has_permission('ToDo', 'read', doc=doc, user=user):
        return
    # Keep this alert in a dedicated mobile-only table. Frappe's standard log
    # appears in Desk, while Rivora Notification Log invokes a legacy relay.
    key = 'rivora-todo-' + hashlib.sha256(f'{name}\n{user}\n{assigned_at}'.encode()).hexdigest()
    if frappe.db.exists('Rivora Mobile Notification', key):
        return
    alert = frappe.get_doc({
        'doctype': 'Rivora Mobile Notification', 'notification_id': key,
        'recipient': user, 'type': 'Assignment', 'document_type': 'ToDo',
        'document_name': name, 'reference_type': doc.get('reference_type'),
        'reference_name': doc.get('reference_name'),
        'subject': _('New ToDo assignment'),
        'message': doc.get('description') or _('A ToDo has been assigned to you.'),
    })
    try:
        alert.insert(ignore_permissions=True, set_name=key)
    except frappe.DuplicateEntryError:
        pass
    else:
        try:
            # Bind delivery to this ToDo's allocated user, independently of
            # ERPNext's notification preferences and Desk notification logs.
            frappe.enqueue('rivora.api.send_push', queue='short',
                enqueue_after_commit=True, user=user, notification_name=key,
                notification_source='Rivora Mobile Notification')
        except Exception:
            frappe.log_error(title='Rivora ToDo phone alert could not be queued',
                message='Check the short queue and background workers. The ToDo remains saved.')
