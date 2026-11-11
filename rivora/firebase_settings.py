"""System Manager credential upload; private keys stay in Frappe encrypted storage."""
import json
import frappe
from frappe import _

SETTINGS = 'Rivora Mobile Settings'
FIELD = 'firebase_service_account_json'


def service_account():
    from frappe.utils.password import get_decrypted_password
    value = get_decrypted_password(SETTINGS, SETTINGS, FIELD, raise_exception=False)
    return json.loads(value) if value else None


@frappe.whitelist(methods=['POST'])
def upload_credentials(service_account_json):
    frappe.only_for('System Manager')
    settings = frappe.get_single(SETTINGS)
    settings.check_permission('write')
    try:
        if not isinstance(service_account_json, str) or len(service_account_json.encode('utf-8')) > 32768:
            raise ValueError()
        data = json.loads(service_account_json)
        if not isinstance(data, dict) or data.get('type') != 'service_account':
            raise ValueError()
        if not all(isinstance(data.get(key), str) and data[key].strip() for key in ['project_id', 'client_email', 'private_key', 'token_uri']):
            raise ValueError()
        if data['token_uri'] not in {'https://oauth2.googleapis.com/token', 'https://accounts.google.com/o/oauth2/token'}:
            raise ValueError()
        from google.oauth2.service_account import Credentials
        Credentials.from_service_account_info(data)
    except Exception:
        frappe.throw(_('Upload a valid Firebase Admin service-account JSON file. The Android google-services.json is a different file.'))
    from frappe.utils.password import set_encrypted_password
    set_encrypted_password(SETTINGS, SETTINGS, json.dumps(data), FIELD)
    return {'configured': True, 'project_id': data['project_id']}


@frappe.whitelist(methods=['POST'])
def configuration_status():
    frappe.only_for('System Manager')
    frappe.get_single(SETTINGS).check_permission('read')
    try:
        data = service_account()
    except Exception:
        return {'configured': False, 'status': 'invalid_saved_credentials'}
    if data:
        return {'configured': True, 'source': 'settings', 'project_id': data.get('project_id')}
    return {'configured': bool(frappe.conf.get('rivora_firebase_credentials')), 'source': 'site_config'}
