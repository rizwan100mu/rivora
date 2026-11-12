"""Original Rivora APIs. Generate locally; execute only on the ERPNext server.

No access decision relies on a client-provided employee or user. Explicit permission
checks precede every domain write. Only internal idempotency/device bookkeeping
uses ignore_permissions, scoped to the authenticated account.
"""
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name, has_approval_access
from frappe.utils import cint, getdate, now_datetime, nowdate, add_days, add_months

ALLOWED = {
    'Sales Invoice', 'Purchase Invoice', 'Account', 'Cost Center', 'GL Entry', 'Stock Entry', 'Material Request', 'Delivery Note', 'Purchase Receipt', 'Stock Reconciliation', 'Item', 'Warehouse', 'Bin', 'Stock Ledger Entry', 'Work Order', 'Job Card', 'BOM', 'Production Plan', 'Operation', 'Workstation', 'Purchase Order', 'Supplier',
    "ToDo", "Leave Request", "Leave Application", "Expense Claim", "Attendance Request", "Shift Request",
    "Event", "Lead", "Task", "Journal Entry", "Rivora Mobile Post", "Rivora Mobile Document",
    "Payment Entry", "Sales Order", "Quotation", "Rivora Mobile Visit", "Issue", "Timesheet", "Customer",
    "Salary Slip", "Holiday List", "Employee Checkin",
}
SELF_FIELDS = {
    "Leave Application": "employee", "Expense Claim": "employee", "Salary Slip": "employee", "Employee Checkin": "employee",
    "Attendance Request": "employee", "Shift Request": "employee",
    "Leave Request": "employee", "Rivora Mobile Document": "employee_no", "Rivora Mobile Visit": "employee", "Timesheet": "employee",
}
READ_ONLY = {'Account', 'Cost Center', 'GL Entry', 'Warehouse', 'Bin', 'Stock Ledger Entry', 'Operation', 'Workstation', "Salary Slip", "Holiday List", "Employee Checkin"}
HIDDEN_INPUTS = {"employee", "employee_no", "owner", "user", "docstatus", "name",
                 "poll_votes", "post_datetime", "workflow_state"}
TYPES = {"Data", "Link", "Dynamic Link", "Select", "Int", "Float", "Currency",
         "Percent", "Check", "Date", "Datetime", "Time", "Small Text", "Text",
         "Long Text", "Text Editor", "Attach", "Attach Image", "Table"}


def identity():
    if frappe.session.user == "Guest":
        frappe.throw(_("Sign in required"), frappe.AuthenticationError)
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
    if not employee:
        frappe.throw(_("An active linked employee is required"), frappe.PermissionError)
    return employee


def allowed(doctype):
    identity()
    if doctype not in ALLOWED:
        frappe.throw(_("Document type is not supported"), frappe.PermissionError)


def writable_fields(meta, depth=0):
    # Metadata alone grants no write access: save_document also runs Frappe's
    # per-document, field-level and child-document permission checks.
    result = []
    section = None
    for f in meta.fields:
        if f.fieldtype in ("Section Break", "Tab Break"):
            section = _(f.label) if f.label and not f.hidden else None
            continue
        if f.fieldtype not in TYPES or f.hidden or f.read_only or f.fieldname in HIDDEN_INPUTS:
            continue
        if cint(f.get("permlevel", 0)) != 0:
            continue
        item = {k: f.get(k) for k in ("fieldname", "fieldtype", "label", "options", "reqd", "default")}
        item["label"] = _(item["label"] or f.fieldname)
        item["section"] = section
        if item["default"] in ("Today", "Now", "__user") or (isinstance(item["default"], str) and item["default"].startswith((":", "eval:", "__"))):
            item["default"] = None  # Frappe applies dynamic defaults on new_doc.
        if f.fieldtype == "Table":
            if depth >= 1:
                continue
            item["fields"] = writable_fields(frappe.get_meta(f.options), depth + 1)
        result.append(item)
    return result


@frappe.whitelist(methods=["GET"])
def form_schema(doctype, language=None):
    allowed(doctype)
    if doctype in READ_ONLY or not (
        frappe.has_permission(doctype, "create") or frappe.has_permission(doctype, "write")
    ):
        frappe.throw(_("No permission to edit this document type"), frappe.PermissionError)
    fields = writable_fields(frappe.get_meta(doctype))
    draft = frappe.new_doc(doctype)
    apply_mobile_defaults(draft, fields)
    defaults = {field["fieldname"]: draft.get(field["fieldname"]) for field in fields
                if field["fieldtype"] != "Table" and draft.get(field["fieldname"]) not in (None, "")}
    from .ui_labels import form_labels
    return {"doctype": doctype, "fields": fields, "defaults": defaults,
            "label_translations": form_labels(doctype, language)}


def apply_mobile_defaults(doc, fields):
    """Mirror new-document defaults without assigning a document number."""
    names = {field["fieldname"] for field in fields}
    for field in fields:
        key = field["fieldname"]
        if doc.get(key) in (None, ""):
            if field["fieldtype"] == "Date" and (field.get("default") == "Today" or key in ("transaction_date", "posting_date")):
                doc.set(key, nowdate())
            elif key == "naming_series":
                options = [option.strip() for option in str(field.get("options") or "").split("\n") if option.strip()]
                if options:
                    doc.set(key, options[0])
    if "company" in names and not doc.get("company"):
        doc.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    if doc.doctype == "Quotation" and not doc.get("valid_till"):
        days = cint(frappe.db.get_single_value("CRM Settings", "default_valid_till"))
        start = doc.get("transaction_date") or nowdate()
        doc.valid_till = add_days(start, days) if days > 0 else add_months(start, 1)
    if "currency" in names and doc.get("company"):
        company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
        if not doc.get("currency"):
            doc.currency = company_currency
        from erpnext.setup.utils import get_exchange_rate
        doc.conversion_rate = 1 if doc.currency == company_currency else get_exchange_rate(doc.currency, company_currency, doc.get("transaction_date") or doc.get("posting_date"))
        price_list = doc.get("selling_price_list") or doc.get("buying_price_list")
        if price_list:
            doc.price_list_currency = frappe.get_cached_value("Price List", price_list, "currency")
        if not doc.get("price_list_currency"):
            doc.price_list_currency = doc.currency
        doc.plc_conversion_rate = 1 if doc.price_list_currency == company_currency else get_exchange_rate(doc.price_list_currency, company_currency, doc.get("transaction_date") or doc.get("posting_date"))


def clean_values(doctype, values, depth=0, existing_doc=None, validate_child_names=False):
    if not isinstance(values, dict):
        frappe.throw(_("Expected form values"))
    schema = {f["fieldname"]: f for f in writable_fields(frappe.get_meta(doctype), depth)}
    cleaned = {}
    for key, value in values.items():
        if key not in schema:
            continue
        f = schema[key]
        if f["fieldtype"] == "Table":
            if not isinstance(value, list) or len(value) > 100:
                frappe.throw(_("Invalid child rows"))
            # Existing child identity and controller-owned fields must survive
            # writable edits. Only rows loaded through this permitted parent may
            # be referenced; never trust a phone-supplied child name globally.
            existing_rows = {
                row.get("name"): row
                for row in ((existing_doc.get(key) or []) if existing_doc is not None else [])
                if row.get("name")
            }
            seen = set()
            cleaned_rows = []
            for index, row in enumerate(value):
                if not isinstance(row, dict):
                    frappe.throw(_("Expected child row values"))
                row_name = row.get("name")
                if row_name and validate_child_names:
                    if not isinstance(row_name, str):
                        frappe.throw(_("Child row does not belong to this document"), frappe.PermissionError)
                    if row_name in seen:
                        frappe.throw(_("Duplicate child row"))
                    seen.add(row_name)
                    if row_name not in existing_rows:
                        # Native scripts need an in-memory name for locals/cdn.
                        # It is never a database identity: discard it and let
                        # Frappe append/name a fresh row through normal insert.
                        # A local flag alone must not authorize foreign IDs.
                        if row.get("__islocal") in (1, True) and re.fullmatch(r"new-native-[0-9]+", row_name):
                            cleaned_rows.append(clean_values(f["options"], row, depth + 1, validate_child_names=True))
                            continue
                        frappe.throw(_("Child row does not belong to this document"), frappe.PermissionError)
                    original = existing_rows[row_name]
                    merged = dict(original.as_dict() if hasattr(original, "as_dict") else original)
                    merged.update(clean_values(f["options"], row, depth + 1, existing_doc=original, validate_child_names=True))
                    merged["idx"] = index + 1
                    cleaned_rows.append(merged)
                else:
                    cleaned_rows.append(clean_values(f["options"], row, depth + 1, validate_child_names=validate_child_names))
            # Replacing the table deliberately removes omitted existing rows.
            cleaned[key] = cleaned_rows
        else:
            if isinstance(value, (dict, list)):
                frappe.throw(_("Invalid field value"))
            if isinstance(value, str) and len(value) > 100000:
                frappe.throw(_("Field value is too long"))
            if f["fieldtype"] in ("Attach", "Attach Image") and value:
                files = frappe.get_list("File", filters={"file_url": value}, fields=["name"], limit_page_length=1)
                if not files:
                    frappe.throw(_("Attachment is not accessible"), frappe.PermissionError)
                frappe.get_doc("File", files[0].name).check_permission("read")
            cleaned[key] = value
    return cleaned


@frappe.whitelist(methods=["POST"])
def preview_sales_totals(doctype, values, name=None):
    """Calculate an unsaved mobile sales draft with ERPNext's own controller."""
    allowed(doctype)
    if doctype not in ("Quotation", "Sales Order"):
        frappe.throw(_("Totals preview supports quotations and sales orders only"))
    source = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
    source.check_permission("write" if name else "create")
    if name:
        source.check_permission("read")
    if source.docstatus != 0:
        frappe.throw(_("Only draft documents can be recalculated"))
    values = frappe.parse_json(values)
    if name and values.get("modified") and str(values["modified"]) != str(source.modified):
        frappe.throw(_("This record changed. Reload it before reviewing."), frappe.TimestampMismatchError)
    # A copy prevents preview calculations from altering the source document.
    draft = frappe.copy_doc(source)
    draft.update(clean_values(doctype, values))
    draft.run_method("set_missing_values")
    draft.run_method("calculate_taxes_and_totals")
    return {key: draft.get(key) for key in (
        "currency", "total_qty", "total", "net_total", "discount_amount",
        "total_taxes_and_charges", "grand_total", "rounded_total",
    )}


@frappe.whitelist(methods=["POST"])
def save_document(doctype, values, name=None, amended_from=None):
    allowed(doctype)
    if doctype in READ_ONLY:
        frappe.throw(_("This document type is read only"), frappe.PermissionError)
    values = frappe.parse_json(values)
    employee = identity()
    doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
    doc.check_permission("write" if name else "create")
    employee_field = SELF_FIELDS.get(doctype)
    if employee_field and name and doc.get(employee_field) != employee:
        frappe.throw(_("Only your own employee documents can be changed here"), frappe.PermissionError)
    if doctype == "Rivora Mobile Post" and name and doc.user != frappe.session.user:
        frappe.throw(_("Only the author can edit a post"), frappe.PermissionError)
    # Avoid silent overwrite after another person has changed the record.
    if name and values.get("modified") and str(values["modified"]) != str(doc.modified):
        frappe.throw(_("This record changed. Reload it before saving."), frappe.TimestampMismatchError)
    doc.update(clean_values(doctype, values, existing_doc=doc if name else None, validate_child_names=True))
    prepare_domain_document(doc, is_new=not bool(name))
    from .transaction_validation import require_party
    require_party(doc)
    if amended_from:
        if name or not doc.meta.is_submittable:
            frappe.throw(_("Invalid amendment"))
        original = frappe.get_doc(doctype, amended_from)
        original.check_permission("read")
        original.check_permission("amend")
        if original.docstatus != 2:
            frappe.throw(_("Only cancelled documents can be amended"))
        if employee_field and original.get(employee_field) != employee:
            frappe.throw(_("Only your own employee documents can be amended here"), frappe.PermissionError)
        doc.amended_from = original.name
    if employee_field:
        doc.set(employee_field, employee)
    if doctype == "Rivora Mobile Post":
        doc.user = frappe.session.user
        doc.employee = employee
        if not name:
            doc.post_datetime = now_datetime()
    if name:
        doc.save()
    else:
        doc.insert()
    # Associate owned private uploads with the saved parent so normal Frappe
    # attachment permissions can cover approvers, rather than leaving orphan files.
    for url in attachment_urls(doc):
        for file_name in frappe.get_list("File", filters={"file_url": url, "owner": frappe.session.user}, pluck="name"):
            file_doc = frappe.get_doc("File", file_name)
            if not file_doc.attached_to_name:
                file_doc.check_permission("write")
                file_doc.attached_to_doctype = doc.doctype
                file_doc.attached_to_name = doc.name
                file_doc.save()
    return {"name": doc.name, "docstatus": doc.docstatus}


def distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


def validate_fence(employee, captured, latitude, longitude):
    settings = frappe.get_single("Rivora Mobile Settings")
    if settings.get("location_validate"):
        return
    if settings.get("geofencing_based_on") not in ("Branch", "Rivora Mobile Location"):
        frappe.throw(_("Configure Branch or Rivora Mobile Location geofencing for Rivora"))
    locations = []
    if settings.get("geofencing_based_on") == "Branch":
        branch = frappe.db.get_value("Employee", employee, "branch")
        if branch:
            locations = [frappe.get_doc("Branch", branch)]
    elif settings.get("geofencing_based_on") == "Rivora Mobile Location":
        assignments = frappe.get_all("Rivora Mobile Location Assignment", filters=[
            ["employee", "=", employee], ["from_date", "<=", captured.date()],
            ["to_date", ">=", captured.date()],
        ], pluck="location")
        locations = [frappe.get_doc("Rivora Mobile Location", loc) for loc in assignments]
    for location in locations:
        if location.get("latitude") is None or location.get("longitude") is None:
            continue
        if float(location.get("radius") or 0) > 0 and distance(latitude, longitude,
                float(location.latitude), float(location.longitude)) <= float(location.radius):
            return
    frappe.throw(_("Attendance location is outside your assigned geofence"), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def attendance(event_id, log_type, captured_at, latitude, longitude, accuracy):
    employee = identity()
    if not re.fullmatch(r"[a-f0-9]{48}", event_id or "") or log_type not in ("IN", "OUT"):
        frappe.throw(_("Invalid attendance event"))
    key = hashlib.sha256(f"{frappe.session.user}:{event_id}".encode()).hexdigest()
    payload = json.dumps([log_type, captured_at, str(latitude), str(longitude), str(accuracy)], separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    def existing(current=False):
        rows = frappe.db.sql("SELECT payload_hash, checkin, user FROM `tabRivora Mobile Event` WHERE name=%s FOR UPDATE", (key,), as_dict=True) if current else None
        row = (rows[0] if rows else None) if current else frappe.db.get_value("Rivora Mobile Event", key, ["payload_hash", "checkin", "user"], as_dict=True)
        if row:
            if row.user != frappe.session.user or row.payload_hash != digest:
                frappe.throw(_("Event identifier was reused with different data"), frappe.PermissionError)
            return {"checkin": row.checkin, "duplicate": True}
        return None
    found = existing()
    if found:
        return found
    if not frappe.has_permission("Employee Checkin", "create"):
        frappe.throw(_("Employee Checkin create permission is required"), frappe.PermissionError)
    captured = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
    if captured.tzinfo is None:
        frappe.throw(_("Capture time must include a timezone"))
    captured_utc = captured.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    max_days = min(30, max(1, cint(frappe.conf.get("rivora_offline_days") or 7)))
    if captured_utc > now + timedelta(minutes=5) or captured_utc < now - timedelta(days=max_days):
        frappe.throw(_("Attendance capture time is outside the allowed sync window"))
    lat, lon, acc = float(latitude), float(longitude), float(accuracy)
    if not all(math.isfinite(v) for v in (lat, lon, acc)) or not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= acc <= 100):
        frappe.throw(_("A valid location with accuracy within 100 metres is required"))
    # Frappe stores naive datetimes in site timezone, never the phone timezone.
    from zoneinfo import ZoneInfo
    site_zone = ZoneInfo(frappe.utils.get_system_timezone())
    local_time = captured_utc.astimezone(site_zone).replace(tzinfo=None)
    validate_fence(employee, local_time, lat, lon)
    # The unique event name is reserved in the same DB transaction as the checkin.
    # A concurrent retry waits on the unique index and then reads the committed event.
    frappe.db.savepoint("mobile_event")
    try:
        event = frappe.get_doc({"doctype": "Rivora Mobile Event", "event_key": key,
            "user": frappe.session.user, "employee": employee, "payload_hash": digest})
        event.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.db.rollback(save_point="mobile_event")
        # Use locking/current read rather than a stale repeatable-read snapshot.
        frappe.db.sql("SELECT name FROM `tabRivora Mobile Event` WHERE name=%s FOR UPDATE", (key,))
        return existing(current=True)
    checkin = frappe.new_doc("Employee Checkin")
    checkin.employee, checkin.log_type, checkin.time = employee, log_type, local_time
    if checkin.meta.has_field("location"):
        checkin.location = f"{lat},{lon}"
    if checkin.meta.has_field("latitude"):
        checkin.latitude = lat
    if checkin.meta.has_field("longitude"):
        checkin.longitude = lon
    checkin.insert()  # Normal document and user permission validation.
    event.checkin = checkin.name
    event.save(ignore_permissions=True)
    return {"checkin": checkin.name, "duplicate": False}


@frappe.whitelist(methods=["GET"])
def approvals(start=0, page_length=30):
    identity()
    rows = frappe.get_list("Workflow Action", filters={"status": "Open"},
        fields=["reference_doctype", "reference_name"], start=max(0, cint(start)),
        page_length=min(100, max(1, cint(page_length))), order_by="modified desc")
    results, seen = [], set()
    for row in rows:
        key = (row.reference_doctype, row.reference_name)
        if key in seen:
            continue
        seen.add(key)
        if not frappe.has_permission(row.reference_doctype, "read", doc=row.reference_name):
            continue
        doc = frappe.get_doc(*key)
        actions = [t.action for t in get_transitions(doc)]
        if actions:
            results.append({**row, "actions": actions})
    return {"items": results, "has_more": len(rows) == min(100, max(1, cint(page_length))), "next_start": max(0, cint(start)) + len(rows)}


@frappe.whitelist(methods=["POST"])
def approve(doctype, name, action):
    allowed(doctype)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    doc.check_permission("write")
    if action not in [t.action for t in get_transitions(doc)]:
        frappe.throw(_("Workflow action is no longer available"), frappe.PermissionError)
    updated = apply_workflow(doc, action)
    return {"name": updated.name, "docstatus": updated.docstatus}


@frappe.whitelist(methods=["GET"])
def manager_dashboard():
    employee = identity()
    team = frappe.get_list("Employee", filters={"reports_to": employee, "status": "Active"},
        fields=["name", "employee_name"], limit_page_length=500)
    if not team:
        return {"team": [], "leave_requests": [], "expenses": []}
    names = [row.name for row in team]
    return {"team": team,
        "leave_requests": frappe.get_list("Leave Application", filters={"employee": ["in", names], "status": "Open"},
            fields=["name", "employee", "from_date", "to_date", "status"], limit_page_length=100),
        "expenses": frappe.get_list("Expense Claim", filters={"employee": ["in", names], "approval_status": "Draft"},
            fields=["name", "employee", "total_claimed_amount", "approval_status"], limit_page_length=100)}


@frappe.whitelist(methods=["POST"])
def like_post(name):
    identity()
    doc = frappe.get_doc("Rivora Mobile Post", name)
    doc.check_permission("read")
    from frappe.desk.like import toggle_like
    return toggle_like("Rivora Mobile Post", name, add="No" if frappe.session.user in frappe.parse_json(doc.get("_liked_by") or "[]") else "Yes")


@frappe.whitelist(methods=["POST"])
def vote(name, answer):
    identity()
    # Lock the parent so two votes cannot race before the user's row exists.
    frappe.db.sql("SELECT name FROM `tabRivora Mobile Post` WHERE name=%s FOR UPDATE", (name,))
    doc = frappe.get_doc("Rivora Mobile Post", name)
    doc.check_permission("read")
    doc.check_permission("write")
    if doc.post_type != "Poll" or not doc.publish or doc.get("poll_closed"):
        frappe.throw(_("Poll is not open"))
    if doc.get("poll_start_date") and getdate(doc.poll_start_date) > getdate(now_datetime()):
        frappe.throw(_("Poll has not started"))
    if doc.get("poll_end_date") and getdate(doc.poll_end_date) < getdate(now_datetime()):
        frappe.throw(_("Poll has ended"))
    options = [row.get("option") or row.get("answer") for row in doc.poll_options]
    if answer not in options:
        frappe.throw(_("Invalid poll answer"))
    if any(row.user == frappe.session.user for row in doc.poll_votes):
        frappe.throw(_("You already voted"))
    original_dates = {"poll_start_date": doc.poll_start_date, "poll_end_date": doc.poll_end_date}
    doc.append("poll_votes", {"user": frappe.session.user, "answer": answer})
    doc.save()
    frappe.db.set_value("Rivora Mobile Post", doc.name, original_dates, update_modified=False)
    return {"voted": True}


@frappe.whitelist(methods=["POST"])
def register_device(device_id, token, language=None):
    identity()
    if not re.fullmatch(r"[a-f0-9]{48}", device_id or "") or not token or len(token) > 4096:
        frappe.throw(_("Invalid device registration"))
    key = hashlib.sha256(f"{frappe.session.user}:{device_id}".encode()).hexdigest()
    if frappe.db.exists("Rivora Mobile Device", key):
        doc = frappe.get_doc("Rivora Mobile Device", key)
        if doc.user != frappe.session.user:
            frappe.throw(_("Device belongs to another user"), frappe.PermissionError)
    else:
        doc = frappe.get_doc({"doctype": "Rivora Mobile Device", "device_key": key,
            "user": frappe.session.user, "device_id": device_id})
    if language is not None:
        if language not in {"en", "ar", "hi", "ur"}:
            frappe.throw(_("Invalid app language"))
        doc.language = language
    doc.token, doc.last_seen = token, now_datetime()
    doc.save(ignore_permissions=True)
    return {"registered": True}


@frappe.whitelist(methods=["POST"])
def set_device_language(device_id, language):
    identity()
    if not re.fullmatch(r"[a-f0-9]{48}", device_id or "") or language not in {"en", "ar", "hi", "ur"}:
        frappe.throw(_("Invalid device language details"))
    key = hashlib.sha256(f"{frappe.session.user}:{device_id}".encode()).hexdigest()
    if not frappe.db.exists("Rivora Mobile Device", {"name": key, "user": frappe.session.user}):
        return {"registered": False}
    doc = frappe.get_doc("Rivora Mobile Device", key)
    if doc.user != frappe.session.user:
        frappe.throw(_("Device belongs to another user"), frappe.PermissionError)
    doc.language = language
    doc.save(ignore_permissions=True)
    return {"registered": True, "language": language}


def clean_devices():
    # Attendance events deliberately remain retained: removing dedupe keys could
    # allow old events to be recreated after backup/retry.
    frappe.db.delete("Rivora Mobile Device", {"last_seen": ["<", now_datetime() - timedelta(days=90)]})

@frappe.whitelist(methods=["POST"])
def unregister_device(device_id):
    identity()
    key = hashlib.sha256(f"{frappe.session.user}:{device_id}".encode()).hexdigest()
    if frappe.db.exists("Rivora Mobile Device", {"name": key, "user": frappe.session.user}):
        frappe.db.delete("Rivora Mobile Device", {"name": key, "user": frappe.session.user})
    return {"registered": False}


def push_update(doc, method=None):
    """Queue the saved alert reference so phone text matches the notification."""
    if doc.get("type") == "Assignment":
        # Frappe may reference either the ToDo or its business document here.
        # Preserve its Desk log. The dedicated ToDo hook sends one mobile alert
        # to allocated_to, avoiding a second phone alert through this hook.
        return
    user = doc.get("for_user")
    if not user or not doc.get("name"):
        return
    frappe.enqueue("rivora.api.send_push", queue="short", enqueue_after_commit=True,
        user=user, notification_name=doc.get("name"))


def send_push(user, notification_name=None, notification_source="Notification Log"):
    from .push_delivery import send_user_push
    return send_user_push(user, notification_name=notification_name,
        notification_source=notification_source)



def attachment_urls(doc):
    urls = []
    for field in doc.meta.fields:
        if field.fieldtype in ("Attach", "Attach Image") and doc.get(field.fieldname):
            urls.append(doc.get(field.fieldname))
        elif field.fieldtype == "Table":
            for row in doc.get(field.fieldname) or []:
                urls.extend(attachment_urls(row))
    return urls

@frappe.whitelist(methods=["GET"])
def attachments(doctype, name):
    allowed(doctype)
    frappe.get_doc(doctype, name).check_permission("read")
    return frappe.get_list("File", filters={"attached_to_doctype": doctype, "attached_to_name": name},
        fields=["name", "file_name", "file_url", "is_private"], limit_page_length=100)


@frappe.whitelist(methods=["POST"])
def comment(doctype, name, content):
    allowed(doctype)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    if not isinstance(content, str) or not content.strip() or len(content) > 5000:
        frappe.throw(_("Enter a comment of at most 5000 characters"))
    # add_comment uses Frappe's normal comment permission/notification path.
    result = doc.add_comment("Comment", text=frappe.utils.escape_html(content.strip()))
    return {"name": result.name}





@frappe.whitelist(methods=["GET"])
def post_detail(name):
    identity()
    doc = frappe.get_doc("Rivora Mobile Post", name)
    doc.check_permission("read")
    result = doc.as_dict()
    if doc.user != frappe.session.user:
        result.pop("poll_votes", None)
    return result


def document_action_catalog(doc):
    """Actions are recomputed from the current document, never trusted from a phone."""
    doc.check_permission("read")
    workflow = get_workflow_name(doc.doctype)
    transitions = get_transitions(doc) if workflow else []
    actions = []
    own = not SELF_FIELDS.get(doc.doctype) or doc.get(SELF_FIELDS[doc.doctype]) == identity()
    if doc.doctype == "Rivora Mobile Post":
        own = doc.user == frappe.session.user
    writable = doc.doctype not in READ_ONLY
    def add(action_id, label, primary=False, destructive=False):
        actions.append({"id": action_id, "label": label, "primary": primary, "destructive": destructive})
    if writable and doc.has_permission("write"):
        for transition in transitions:
            if has_approval_access(frappe.session.user, doc, transition):
                add("workflow:" + transition.action, _(transition.action), primary=True)
    if writable and own and doc.docstatus == 0 and doc.has_permission("write"):
        add("edit", _("Edit"), primary=not actions)
    if writable and own and not workflow and doc.meta.is_submittable:
        if doc.docstatus == 0 and doc.has_permission("submit") and doc.has_permission("write"):
            add("submit", _("Submit"), primary=True)
        if doc.docstatus == 1 and doc.has_permission("cancel"):
            add("cancel", _("Cancel document"), destructive=True)
    if writable and own and doc.has_permission("create"):
        add("duplicate", _("Duplicate"))
        if doc.docstatus == 2 and doc.meta.is_submittable and doc.has_permission("amend"):
            add("amend", _("Amend"), primary=True)
    if writable and own and doc.docstatus != 1 and doc.has_permission("delete"):
        add("delete", _("Delete"), destructive=True)
    if doc.has_permission("print"):
        add("pdf", _("Open PDF"))
    if writable and own and doc.docstatus != 2 and doc.has_permission("write"):
        add("attach", _("Attach photo"))
    return {"actions": actions, "modified": str(doc.modified), "docstatus": doc.docstatus,
            "status": doc.get("workflow_state") or doc.get("status") or
                {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(doc.docstatus)}


@frappe.whitelist(methods=["GET"])
def document_actions(doctype, name):
    allowed(doctype)
    return document_action_catalog(frappe.get_doc(doctype, name))


@frappe.whitelist(methods=["POST"])
def perform_document_action(doctype, name, action, modified):
    allowed(doctype)
    doc = frappe.get_doc(doctype, name)
    catalog = document_action_catalog(doc)
    if str(doc.modified) != str(modified):
        frappe.throw(_("This record changed. Refresh before continuing."), frappe.TimestampMismatchError)
    if action not in {item["id"] for item in catalog["actions"]}:
        frappe.throw(_("This action is no longer available"), frappe.PermissionError)
    if action.startswith("workflow:"):
        updated = apply_workflow(doc, action[len("workflow:"):])
        return {"name": updated.name, "docstatus": updated.docstatus}
    if action == "submit":
        doc.submit()
    elif action == "cancel":
        doc.cancel()
    elif action == "delete":
        frappe.delete_doc(doctype, name)
        return {"deleted": True}
    elif action in ("duplicate", "amend"):
        copy = frappe.copy_doc(doc)
        return {"values": clean_values(doctype, copy.as_dict()),
                "amended_from": name if action == "amend" else None}
    else:
        frappe.throw(_("Unsupported document operation"))
    return {"name": doc.name, "docstatus": doc.docstatus}


DASHBOARD_TYPES = (
    ("Quotation", "Quotations"), ("Sales Order", "Sales orders"), ("Customer", "Customers"),
    ("Lead", "Leads"), ("Task", "Tasks"), ("Issue", "Issues"),
    ("Expense Claim", "Expenses"), ("Leave Application", "Leave"),
    ("Payment Entry", "Payments"), ("Journal Entry", "Journal entries"), ("Timesheet", "Timesheets"),
    ("Salary Slip", "Salary slips"), ("Attendance Request", "Attendance requests"),
    ("Shift Request", "Shift requests"), ("Holiday List", "Holidays"),
    ("Event", "Events"), ("Rivora Mobile Post", "Community"), ("Rivora Mobile Document", "Documents"), ("Rivora Mobile Visit", "RivoraVisits"),
    ('Sales Invoice', 'Sales invoices'),
    ('Purchase Invoice', 'Purchase invoices'),
    ('Account', 'Accounts'),
    ('Cost Center', 'Cost centers'),
    ('GL Entry', 'General ledger'),
    ('Stock Entry', 'Stock entries'),
    ('Material Request', 'Material requests'),
    ('Delivery Note', 'Delivery notes'),
    ('Purchase Receipt', 'Purchase receipts'),
    ('Stock Reconciliation', 'Stock reconciliation'),
    ('Item', 'Items'),
    ('Warehouse', 'Warehouses'),
    ('Bin', 'Stock balances'),
    ('Stock Ledger Entry', 'Stock ledger'),
    ('Work Order', 'Work orders'),
    ('Job Card', 'Job cards'),
    ('BOM', 'Bills of materials'),
    ('Production Plan', 'Production plans'),
    ('Operation', 'Operations'),
    ('Workstation', 'Workstations'),
    ('Purchase Order', 'Purchase orders'),
    ('Supplier', 'Suppliers'),
)


@frappe.whitelist(methods=["GET"])
def dashboard_summary():
    employee = identity()
    items = []
    for doctype, label in DASHBOARD_TYPES:
        if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
            continue
        filters = {}
        if SELF_FIELDS.get(doctype):
            filters[SELF_FIELDS[doctype]] = employee
        try:
            # get_list, unlike db.count/get_all, applies row-level permissions and
            # permission_query_conditions before aggregation. Counts match mobile lists.
            rows = frappe.get_list(doctype, filters=filters,
                fields=["docstatus", {"COUNT": "name", "as": "total"}], group_by="docstatus",
                order_by="docstatus", limit_page_length=3)
            counts = {cint(row.docstatus): cint(row.total) for row in rows}
            items.append({"doctype": doctype, "label": _(label), "total": sum(counts.values()),
                "draft": counts.get(0, 0), "submitted": counts.get(1, 0),
                "cancelled": counts.get(2, 0), "submittable": bool(frappe.get_meta(doctype).is_submittable),
                "can_create": bool(doctype not in READ_ONLY and frappe.has_permission(doctype, "create"))})
        except frappe.PermissionError:
            continue
    stock_types = []
    if any(item["doctype"] == "Stock Entry" and item["can_create"] for item in items):
        try:
            stock_types = frappe.get_list("Stock Entry Type", fields=["name", "purpose"],
                filters={"purpose": ["in", ["Material Receipt", "Material Transfer", "Material Issue"]]},
                order_by="name", limit_page_length=30)
        except frappe.PermissionError:
            pass
    return {"items": items, "scope": _("All records you can access"), "stock_entry_types": stock_types}

RECORD_PREVIEW_FIELDS = (
    "title", "customer_name", "supplier_name", "item_name", "item_code", "production_item",
    "operation", "work_order", "company", "status", "purpose", "payment_type", "voucher_type",
    "posting_date", "transaction_date", "schedule_date", "planned_start_date", "currency",
    "grand_total", "outstanding_amount", "paid_amount", "total_debit", "total_credit",
    "qty", "produced_qty", "for_quantity", "total_completed_qty", "percent_completed",
    "warehouse", "actual_qty", "reserved_qty", "projected_qty", "stock_uom",
    "from_warehouse", "to_warehouse", "account_name", "account_currency",
    "voucher_no", "account", "debit", "credit", "paid_from_account_currency",
)


@frappe.whitelist(methods=["GET"])
def mobile_records(doctype, text="", start=0, page_length=30, docstatus=None):
    allowed(doctype)
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("No permission to read this document type"), frappe.PermissionError)
    meta = frappe.get_meta(doctype)
    fields = ["name", "modified", "docstatus"]
    if doctype == "ToDo":
        fields.append("creation")
    search_fields = ["name"]
    for name in RECORD_PREVIEW_FIELDS:
        field = meta.get_field(name)
        if field and cint(field.get("permlevel", 0)) == 0:
            fields.append(name)
            if name in ("title", "customer_name", "supplier_name", "item_name", "item_code", "production_item", "work_order", "warehouse", "account_name", "account", "voucher_no"):
                search_fields.append(name)
    filters = {}
    if SELF_FIELDS.get(doctype):
        filters[SELF_FIELDS[doctype]] = identity()
    if docstatus not in (None, ""):
        if str(docstatus) not in ("0", "1", "2"):
            frappe.throw(_("Invalid document status"))
        filters["docstatus"] = cint(docstatus)
    offset = max(0, cint(start))
    size = min(100, max(1, cint(page_length)))
    text = str(text or "").strip()[:100]
    rows = frappe.get_list(doctype, fields=fields, filters=filters,
        or_filters=[[name, "like", "%" + text + "%"] for name in search_fields] if text else None,
        order_by="modified desc, name desc", limit_start=offset, limit_page_length=size + 1)
    return {"items": rows[:size], "has_more": len(rows) > size, "next_start": offset + size,
        "can_create": bool(doctype not in READ_ONLY and frappe.has_permission(doctype, "create")),
        "submittable": bool(meta.is_submittable)}


def prepare_domain_document(doc, is_new):
    """Use ERPNext controllers for domain defaults; no client-supplied method dispatch."""
    if doc.doctype == "Stock Entry" and doc.get("stock_entry_type"):
        doc.purpose = frappe.get_cached_value("Stock Entry Type", doc.stock_entry_type, "purpose")
    if doc.doctype == "Work Order" and is_new and doc.get("bom_no"):
        frappe.get_doc("BOM", doc.bom_no).check_permission("read")
        doc.get_items_and_operations_from_bom()
