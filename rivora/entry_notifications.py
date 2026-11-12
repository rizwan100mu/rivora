"""Retired notification engine; use ERPNext Notification with channel System.

Entry points remain harmless for jobs queued before the upgrade.
"""


def validate_settings(settings):
    return None


def queue_entry_alert(doc, method=None):
    return None


def deliver_entry_alert(doctype, name, creation):
    return None
