"""Read-only inventory for a reviewed existing-site ownership migration."""
from pathlib import Path
import json
import frappe
def inspect():
    if frappe.session.user != 'Administrator' and 'System Manager' not in frappe.get_roles():
        frappe.throw('System Manager is required', frappe.PermissionError)
    mapping=json.loads((Path(__file__).parent/'rename_map.json').read_text())
    rows=[]
    for old,new in mapping.items():
        present=bool(frappe.db.exists('DocType', old))
        target=bool(frappe.db.exists('DocType', new))
        rows.append({'old':old,'new':new,'source_exists':present,'target_exists':target,'collision':present and target})
    return {'installed_apps':frappe.get_installed_apps(),'renames':rows,'writes_performed':False,'migration_ready':False,'note':'Review ownership, custom scripts, SQL, reports, custom fields, links and field renames on a backed-up staging clone. No automatic existing-site conversion is supplied.'}
