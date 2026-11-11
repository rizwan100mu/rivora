"""Permission-aware list/dashboard totals; this module never writes documents."""
import frappe
from frappe.utils import cint, getdate, nowdate
from frappe.desk.reportview import validate_args
from frappe.query_builder.functions import Count
from .api import ALLOWED, SELF_FIELDS, identity


@frappe.whitelist(methods=["GET"])
def get_summary(doctype, filters=None, or_filters=None, date_from=None, date_to=None, use_fiscal_year=1):
    employee = identity()
    if doctype not in ALLOWED | {"ToDo", "Leave Request"}:
        frappe.throw("Document type is not supported", frappe.PermissionError)
    if not frappe.has_permission(doctype, "read"):
        frappe.throw("No permission to read this document type", frappe.PermissionError)
    meta = frappe.get_meta(doctype)
    filters = frappe.parse_json(filters) or []
    or_filters = frappe.parse_json(or_filters) or []
    if not isinstance(filters, list) or not isinstance(or_filters, list):
        frappe.throw("Filters must be a list")
    filters = list(filters)
    own_field = SELF_FIELDS.get(doctype)
    if doctype == "Leave Request":
        own_field = "employee" if meta.has_field("employee") else "user" if meta.has_field("user") else None
    if own_field:
        filters.append([doctype, own_field, "=", frappe.session.user if own_field == "user" else employee])
    if doctype == "Rivora Mobile Post":
        filters.append([doctype, "publish", "=", 1])
    if doctype == "ToDo":
        filters.append([doctype, "allocated_to", "=", frappe.session.user])
    date_field = next((key for key in ("posting_date", "transaction_date", "date", "from_date")
                       if meta.has_field(key) and meta.get_field(key).fieldtype in ("Date", "Datetime")), "creation")
    fiscal_year = None
    if date_from or date_to:
        if not date_from or not date_to or getdate(date_to) < getdate(date_from):
            frappe.throw("Choose a valid start and end date")
    elif cint(use_fiscal_year):
        from erpnext.accounts.utils import get_fiscal_year
        company = next((row[3] for row in filters if isinstance(row, list) and len(row) == 4
                        and row[0] == doctype and row[1] == "company" and row[2] == "="), None)
        fiscal_year, date_from, date_to = get_fiscal_year(nowdate(), company=company, verbose=0)[:3]
    if date_from and date_to:
        start, end = str(getdate(date_from)), str(getdate(date_to))
        if date_field == "creation" or meta.get_field(date_field).fieldtype == "Datetime":
            start += " 00:00:00"
            end += " 23:59:59.999999"
        filters.append([doctype, date_field, "between", [start, end]])
    status_field = "docstatus" if meta.is_submittable else "status" if meta.has_field("status") else "docstatus"
    # Distinct parent IDs prevent multiple matching child rows inflating counts.
    qualified_status = f"`tab{doctype}`.`{status_field}`"
    args = frappe._dict(doctype=doctype, filters=filters, or_filters=or_filters,
                        fields=[f"{qualified_status} as status", "name"],
                        group_by=qualified_status, order_by=qualified_status, limit_page_length=500)
    # Report-view validation accepts field strings/dicts, not query-builder terms.
    # Validate the source fields and filters first; get_list still enforces normal
    # query permissions. A Count term is needed because COUNT's dictionary syntax
    # has no DISTINCT flag in Frappe 16. Never embed SQL functions in field strings.
    validate_args(args)
    args.fields = [f"{qualified_status} as status",
                   Count(frappe.qb.DocType(doctype).name).distinct().as_("total")]
    rows = frappe.get_list(**args)
    labels = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
    counts = [{"label": labels.get(cint(row.status), str(row.status)) if meta.is_submittable else str(row.status or "Not set") if status_field == "status" else "Entries",
               "count": cint(row.total), "value": row.status} for row in rows]
    if meta.is_submittable:
        found = {cint(row["value"]) for row in counts}
        counts += [{"label": label, "count": 0, "value": value} for value, label in labels.items() if value not in found]
        counts.sort(key=lambda row: cint(row["value"]))
    total = sum(row["count"] for row in counts)
    if not meta.is_submittable and not meta.has_field("status"):
        counts = []
    return {"total": total, "counts": counts,
            "status_field": status_field, "date_field": date_field,
            "date_from": str(getdate(date_from)) if date_from else None,
            "date_to": str(getdate(date_to)) if date_to else None,
            "fiscal_year": fiscal_year}
