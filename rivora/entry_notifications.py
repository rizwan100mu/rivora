"""Configuration-driven new-entry alerts; business documents are never modified."""
import hashlib
from html import escape
import frappe
from frappe import _

EXCLUDED = frozenset({'Notification Log', 'Error Log', 'Rivora Mobile Settings', 'Rivora Mobile Tracking Session', 'Rivora Mobile Location Point'})


def _selected(settings, field, key):
    return {row.get(key) for row in settings.get(field) or [] if row.get(key)}


def validate_settings(settings):
    if not settings.get('enable_entry_notifications'):
        return
    doctypes = _selected(settings, 'entry_notification_doctypes', 'document_type')
    users = _selected(settings, 'entry_rivora_notification_users', 'user')
    if not doctypes or not users:
        frappe.throw(_('Select at least one DocType and one notification user'))
    for doctype in doctypes:
        if not frappe.db.exists('DocType', doctype):
            frappe.throw(_('Selected DocType does not exist'))
        meta = frappe.get_meta(doctype)
        if doctype in EXCLUDED or meta.istable or meta.issingle:
            frappe.throw(_('Select a regular business DocType, not a log, child table or settings document'))
    for user in users:
        if user == 'Guest' or not frappe.db.get_value('User', user, 'enabled'):
            frappe.throw(_('Notification recipients must be enabled users'))


def queue_entry_alert(doc, method=None):
    """after_insert hook: only queue; emit nothing until the transaction commits."""
    if doc.doctype == 'ToDo':
        return  # Dedicated default assignment path avoids duplicate entry alerts.
    if doc.doctype in EXCLUDED or doc.meta.istable or doc.meta.issingle:
        return
    if frappe.flags.get('in_install') or frappe.flags.get('in_migrate'):
        return
    try:
        settings = frappe.get_cached_doc('Rivora Mobile Settings')
        if not settings.get('enable_entry_notifications'):
            return
        if doc.doctype not in _selected(settings, 'entry_notification_doctypes', 'document_type'):
            return
        if not _selected(settings, 'entry_rivora_notification_users', 'user'):
            return
        frappe.enqueue('rivora.entry_notifications.deliver_entry_alert',
            queue='short', enqueue_after_commit=True, doctype=doc.doctype,
            name=doc.name, creation=str(doc.creation))
    except Exception:
        # Notification configuration must never roll back an otherwise valid entry.
        frappe.log_error(title='Rivora entry notification could not be queued',
            message='Check the notification configuration and background workers.')


def deliver_entry_alert(doctype, name, creation):
    """Read current settings/permissions and create one Notification Log per recipient."""
    from frappe.desk.doctype.notification_settings.notification_settings import is_notifications_enabled
    if doctype in EXCLUDED:
        return
    settings = frappe.get_cached_doc('Rivora Mobile Settings')
    if not settings.get('enable_entry_notifications'):
        return
    if doctype not in _selected(settings, 'entry_notification_doctypes', 'document_type'):
        return
    if not frappe.db.exists(doctype, name):
        return
    doc = frappe.get_doc(doctype, name)
    if doc.meta.istable or doc.meta.issingle or str(doc.creation) != creation:
        return
    for user in sorted(_selected(settings, 'entry_rivora_notification_users', 'user')):
        if user == 'Guest' or not frappe.db.get_value('User', user, 'enabled'):
            continue
        from .notification_scope import personal_document
        if not personal_document(doctype, name, user):
            continue
        if not is_notifications_enabled(user):
            continue
        if not frappe.has_permission(doctype, 'read', doc=doc, user=user):
            continue
        key = 'rivora-entry-' + hashlib.sha256(
            f'{doctype}\n{name}\n{creation}\n{user}'.encode()).hexdigest()
        if frappe.db.exists('Notification Log', key):
            continue
        alert = frappe.get_doc({
            'doctype': 'Notification Log', 'type': 'Alert', 'for_user': user,
            'from_user': doc.owner, 'document_type': doctype, 'document_name': name,
            'subject': _('New {0}: {1}').format(escape(doctype), escape(name)),
        })
        try:
            # Internal notification insertion matches Frappe's own notification path.
            # The business record is read-only here; recipients were checked above.
            alert.insert(ignore_permissions=True, set_name=key)
        except frappe.DuplicateEntryError:
            # A retry/concurrent worker must not duplicate a committed alert.
            pass
