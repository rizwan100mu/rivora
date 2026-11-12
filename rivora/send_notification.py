"""Retired notification engine; use ERPNext Notification with channel System.

Entry points remain harmless for jobs queued before the upgrade.
"""


def notification(doc, event):
    return None


def notification_processing(doc, event):
    return None


def send_notification(doc, notification, recipients):
    return None
