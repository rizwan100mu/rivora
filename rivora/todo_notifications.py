"""Retired notification engine; use ERPNext Notification with channel System.

Entry points remain harmless for jobs queued before the upgrade.
"""


def queue_assignment(doc, method=None):
    return None


def deliver_assignment(name, user, assigned_at):
    return None
