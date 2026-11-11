"""Native document assignment/sharing through Frappe's own permission APIs."""
import frappe
from frappe import _
from frappe.utils import cint
from .api import allowed


def _document(doctype, name):
    allowed(doctype)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    return doc


def _sharing(doc):
    if frappe.get_system_settings("disable_document_sharing"):
        frappe.throw(_("Document sharing is disabled"), frappe.PermissionError)
    doc.check_permission("share")


def _user(user):
    if not isinstance(user, str) or not user or len(user) > 140 or user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
        frappe.throw(_("Select an enabled ERPNext user"))


@frappe.whitelist(methods=["GET"])
def status(doctype, name):
    doc = _document(doctype, name)
    can_share = bool(doc.has_permission("share")) and not frappe.get_system_settings("disable_document_sharing")
    assignees = frappe.parse_json(doc.get("_assign") or "[]") or []
    shares = frappe.get_all("DocShare", filters={"share_doctype": doctype, "share_name": name},
        fields=["user", "read", "write", "submit", "share", "everyone"], limit_page_length=500) if can_share else []
    return {"can_assign": not bool(doc.meta.issingle), "can_share": bool(can_share),
        "can_write": bool(doc.has_permission("write")), "can_submit": bool(doc.has_permission("submit")),
        "assignees": assignees, "shares": shares}


@frappe.whitelist(methods=["POST"])
def assign(doctype, name, users, description=None, priority="Medium", due_date=None):
    _document(doctype, name)
    users = frappe.parse_json(users)
    if not isinstance(users, list) or not 1 <= len(users) <= 20 or not all(isinstance(user, str) for user in users):
        frappe.throw(_("Select between one and twenty users"))
    if priority not in {"Low", "Medium", "High"}:
        frappe.throw(_("Invalid priority"))
    users = list(dict.fromkeys(users))
    for user in users:
        _user(user)
    from frappe.desk.form.assign_to import add
    args = {"doctype": doctype, "name": name, "assign_to": users,
        "description": str(description or "")[:5000], "priority": priority}
    if due_date:
        args["date"] = due_date
    # Do not pass ignore_permissions, assigned_by, or client-supplied rules.
    add(args)
    return {"assigned": users}


@frappe.whitelist(methods=["POST"])
def unassign(doctype, name, user):
    _document(doctype, name)
    from frappe.desk.form.assign_to import remove
    remove(doctype, name, assign_to=user)
    return {"removed": user}


@frappe.whitelist(methods=["POST"])
def share(doctype, name, user, write=0, submit=0, share=0, notify=1):
    doc = _document(doctype, name)
    _sharing(doc)
    _user(user)
    from frappe.share import add
    # Public API checks every requested permission against the acting user.
    add(doctype, name, user=user, read=1, write=cint(write), submit=cint(submit),
        share=cint(share), everyone=0, notify=cint(notify))
    return {"shared": user}


@frappe.whitelist(methods=["POST"])
def unshare(doctype, name, user):
    doc = _document(doctype, name)
    _sharing(doc)
    from frappe.share import remove
    # This wrapper enforces share permission before the internal removal helper.
    remove(doctype, name, user)
    return {"removed": user}
