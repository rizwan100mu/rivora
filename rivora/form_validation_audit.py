"""Read-only, bench-only inspection of effective form/child metadata and hooks."""
import frappe
from frappe.utils import cint
from .api import ALLOWED, READ_ONLY

def audit(all_installed=0):
    if frappe.session.user != 'Administrator' and 'System Manager' not in frappe.get_roles():
        frappe.throw('System Manager is required for the form metadata audit',frappe.PermissionError)
    types=sorted(frappe.get_all('DocType',filters={'istable':0,'issingle':0},pluck='name') if cint(all_installed) else ALLOWED)
    fields=('fieldname','fieldtype','label','options','reqd','hidden','read_only','permlevel','depends_on','mandatory_depends_on','read_only_depends_on','fetch_from','allow_on_submit')
    hooks=frappe.get_hooks('doc_events') or {}
    report=[]
    for doctype in types:
        if not frappe.db.exists('DocType',doctype):
            report.append({'doctype':doctype,'status':'not_installed'});continue
        meta=frappe.get_meta(doctype)
        parent=[{key:f.get(key) for key in fields} for f in meta.fields]
        children={}
        for f in meta.fields:
            if f.fieldtype in ('Table','Table MultiSelect') and f.options and frappe.db.exists('DocType',f.options):
                children[f.fieldname]={'doctype':f.options,'fields':[{key:child.get(key) for key in fields} for child in frappe.get_meta(f.options).fields]}
        scripts=frappe.get_all('Client Script',filters={'dt':doctype,'enabled':1},pluck='name')
        report.append({'doctype':doctype,'status':'metadata_read','app_read_only':doctype in READ_ONLY,
                       'is_submittable':bool(meta.is_submittable),'fields':parent,'child_tables':children,
                       'enabled_client_scripts':scripts,'doc_events':{'all':hooks.get('*',{}),'doctype':hooks.get(doctype,{})}})
    return {'scope':'all_installed' if cint(all_installed) else 'supported_app_doctypes',
            'doctype_count':len(report),'forms':report,'business_records_read_or_written':False,
            'warning':'Metadata and hook inventory only. This does not execute browser scripts, create/edit/submit documents, or certify domain/ledger parity. The app commit path uses the installed ERPNext form engine.'}
