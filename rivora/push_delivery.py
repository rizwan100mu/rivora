"""Own-project Firebase phone delivery with safe, token-free diagnostics."""
import hashlib
import json
from html import unescape
import re
import frappe
from frappe import _

CHANNEL_ID = "rivora_alerts_v1"


def _plain(value, limit):
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    text = " ".join(unescape(text).split())
    return text[:limit]


AR_DOCTYPES = {
    "ToDo": "المهام", "Quotation": "عرض سعر", "Sales Order": "أمر بيع",
    "Sales Invoice": "فاتورة مبيعات", "Purchase Order": "أمر شراء",
    "Purchase Invoice": "فاتورة مشتريات", "Task": "مهمة", "Issue": "مشكلة",
    "Leave Application": "طلب إجازة", "Leave Request": "طلب إجازة",
    "Expense Claim": "مطالبة مصروفات", "Employee": "موظف", "Customer": "عميل",
    "Supplier": "مورد", "Payment Entry": "قيد دفع", "Journal Entry": "قيد يومية",
    "Material Request": "طلب مواد", "Stock Entry": "قيد مخزون",
    "Delivery Note": "إشعار تسليم", "Purchase Receipt": "إيصال شراء",
}


def normalize_language(language):
    code = str(language or "en").lower().replace("_", "-").split("-")[0]
    return code if code in {"en", "ar", "hi", "ur"} else "en"


def translated(text, language):
    value = _(text, lang=language)
    if language == "ar" and value == text:
        return AR_DOCTYPES.get(text, text)
    return value


def render_alert(log, language="en"):
    language = normalize_language(language)
    doctype = _plain(log.get("document_type") or log.get("reference_document"), 140)
    name = _plain(log.get("document_name") or log.get("reference_name"), 140)
    label = translated(doctype, language) if doctype else ""
    subject = _plain(log.get("title") or log.get("subject"), 500)
    title = " \u00b7 ".join(part for part in (label, name) if part)[:120]
    body = subject or _plain(log.get("description") or log.get("email_content") or log.get("message"), 500)
    if log.get("type") == "Assignment" and doctype == "ToDo":
        reference_type = _plain(log.get("reference_type"), 140)
        reference_name = _plain(log.get("reference_name"), 140)
        if reference_type and reference_name:
            reference_label = translated(reference_type, language)
            title = f"{reference_label} \u00b7 {reference_name}"[:120]
        else:
            title = translated("ToDo", language)
        body = _plain(log.get("message") or log.get("description") or subject, 500)
    if language != "en":
        if log.get("type") == "Assignment" and doctype == "ToDo":
            pass  # Keep the task description and linked-record label intact.
        elif log.get("type") == "Assignment" and doctype and name:
            # Assignment logs also include removals: use an accurate neutral label.
            template = "تحديث إسناد {0}: {1}" if language == "ar" else translated("Assignment update for {0}: {1}", language)
            body = template.format(label, name)
        elif log.get("type") == "Share" and doctype and name:
            template = "تمت مشاركة {0}: {1} معك" if language == "ar" else translated("Document shared with you: {0} {1}", language)
            body = template.format(label, name)
        elif str(log.get("name") or "").startswith("rivora-entry-") and doctype and name:
            template = "سجل جديد — {0}: {1}" if language == "ar" else translated("New {0}: {1}", language)
            body = template.format(label, name)
        elif body:
            body = translated(body, language)
    fallback = "إشعار جديد" if language == "ar" else translated("New notification", language)
    return (title or subject[:120] or "Rivora", _plain(body or fallback, 500))


def _alert_content(user, notification_name, language="en", notification_source="Notification Log"):

    try:
        if notification_source not in {"Notification Log", "Rivora Mobile Notification"}:
            return None
        log = frappe.get_doc(notification_source, notification_name)
    except frappe.DoesNotExistError:
        return None
    recipient = log.get("for_user") if notification_source == "Notification Log" else log.get("recipient")
    if recipient != user:
        return None
    from .notification_scope import personal_alert
    if not personal_alert(log, user):
        return None
    return render_alert(log, language)


def send_user_push(user, device_name=None, notification_name=None, is_test=False,
                   notification_source="Notification Log"):
    if not notification_name and not is_test:
        return {"status": "out_of_scope", "sent": 0}
    title, body = "Rivora", "You have a new update."
    if notification_name:
        content = _alert_content(user, notification_name, notification_source=notification_source)
        if content is None:
            return {"status": "notification_unavailable", "sent": 0}
        title, body = content
    elif is_test:
        title, body = "Rivora push test", "Your phone can receive notifications."

    from .firebase_settings import service_account
    try:
        credential_file = service_account() or frappe.conf.get("rivora_firebase_credentials")
    except Exception:
        return {"status": "configuration_error", "sent": 0}
    if not credential_file:
        return {"status": "no_credentials", "sent": 0}
    from firebase_admin import credentials, messaging
    import firebase_admin
    app_name = "rivora_" + hashlib.sha256(frappe.local.site.encode()).hexdigest()[:16]
    if isinstance(credential_file, dict):
        app_name += '_' + hashlib.sha256(json.dumps(credential_file, sort_keys=True).encode()).hexdigest()[:16]
    try:
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            app = firebase_admin.initialize_app(credentials.Certificate(credential_file), name=app_name)
    except Exception:
        frappe.log_error(title="Rivora Firebase configuration failed", message="Check the configured service account file and Firebase project. No credentials are logged.")
        return {"status": "configuration_error", "sent": 0}
    filters = {"user": user}
    if device_name:
        filters["name"] = device_name
    devices = frappe.get_all("Rivora Mobile Device", filters=filters, pluck="name")
    if not devices:
        return {"status": "no_devices", "sent": 0}
    sent = 0
    for name in devices:
        device = frappe.get_doc("Rivora Mobile Device", name)
        token = device.get_password("token", raise_exception=False)
        if not token:
            continue
        language = normalize_language(getattr(device, "get", lambda key: None)("language"))
        if notification_name:
            content = _alert_content(user, notification_name, language, notification_source)
            if content is None:
                continue
            title, body = content
        elif is_test:
            title = "اختبار إشعارات ريزورا" if language == "ar" else translated("Rivora push test", language)
            body = "يمكن لهاتفك استقبال الإشعارات." if language == "ar" else translated("Your phone can receive notifications.", language)
        else:
            body = "لديك تحديث جديد." if language == "ar" else translated("You have a new update.", language)
        try:
            messaging.send(messaging.Message(token=token,
                notification=messaging.Notification(title=title, body=body),
                data={"route": "notifications"},
                android=messaging.AndroidConfig(priority="high", notification=messaging.AndroidNotification(
                    channel_id=CHANNEL_ID, sound="default", priority="high", icon="rivora_notification"))), app=app)
            sent += 1
        except messaging.UnregisteredError:
            frappe.db.delete("Rivora Mobile Device", {"name": name})
        except Exception:
            frappe.log_error(title="Rivora push delivery failed", message="Check Firebase project permissions and network access. No tokens are logged.")
    return {"status": "sent" if sent else "delivery_failed", "sent": sent}


@frappe.whitelist(methods=["POST"])
def test_phone_push(device_id):
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Sign in required"), frappe.AuthenticationError)
    if not re.fullmatch(r"[a-f0-9]{48}", device_id or ""):
        frappe.throw(_("Invalid device ID"))
    key = hashlib.sha256(f"{user}:{device_id}".encode()).hexdigest()
    if not frappe.db.exists("Rivora Mobile Device", {"name": key, "user": user}):
        return {"status": "no_devices", "sent": 0}
    # Only the requesting account's current registered phone is targeted.
    return send_user_push(user, device_name=key, is_test=True)
