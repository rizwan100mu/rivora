"""Personal ERPNext and Rivora notification history, scoped before pagination."""
import frappe
from frappe import _
from frappe.utils import cint
from .notification_scope import personal_alert

@frappe.whitelist(methods=['GET'])
def list_notifications(start=0, page_length=30, language=None):
    user=frappe.session.user
    if not user or user=='Guest':
        frappe.throw(_('Sign in required'),frappe.AuthenticationError)
    start=max(0,cint(start));size=min(100,max(1,cint(page_length)))
    if start>10000:
        frappe.throw(_('Notification history offset is too large'))
    rows=[]
    for doctype,recipient,optional in (
        ('Notification Log','for_user',('subject','title','email_content','description','read','type','document_type','document_name')),
        ('Rivora Mobile Notification','recipient',('subject','message','read','type','document_type','document_name','reference_type','reference_name')),
        ('Rivora Notification Log','recipient',('subject','message','read','reference_document','reference_name'))):
        if not frappe.db.exists('DocType',doctype):
            continue
        meta=frappe.get_meta(doctype)
        if not meta.has_field(recipient):
            frappe.throw(_('Notification history recipient field is missing'))
        fields=['name','creation']+[f for f in optional if meta.has_field(f)]
        accepted=[]
        # Scan each source until the requested personal page is filled. Never let
        # a page of unrelated alerts hide older personal assignments.
        for offset in range(0,10000,200):
            saved=frappe.get_all(doctype,filters={recipient:user},fields=fields,order_by='creation desc, name desc',start=offset,page_length=200)
            for row in saved:
                item=dict(row)
                if not personal_alert(item,user):
                    continue
                item['notification_source']=doctype
                if language:
                    from .push_delivery import render_alert,translated,normalize_language
                    selected_language=normalize_language(language)
                    reference_type=item.get('reference_type') or item.get('reference_document') or item.get('document_type')
                    if reference_type:
                        item['display_document_type']=translated(reference_type,selected_language)
                    localized_title,item['localized_subject']=render_alert(item,selected_language)
                accepted.append(item)
            if len(saved)<200 or len(accepted)>=start+size:
                break
        rows.extend(accepted)
    rows.sort(key=lambda row:(str(row.get('creation') or ''),str(row.get('name') or ''),row['notification_source']),reverse=True)
    return rows[start:start+size]

@frappe.whitelist(methods=['GET'])
def personal_notifications(start=0,page_length=30,language=None):
    return {'scope':'owner_or_assignee','notifications':list_notifications(start,page_length,language)}
