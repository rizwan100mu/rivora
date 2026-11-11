"""Small authenticated context for native form scripts; no business writes."""
import frappe


@frappe.whitelist(methods=['GET'])
def get_context():
    if frappe.session.user == 'Guest':
        frappe.throw('Sign in to load form rules.', frappe.AuthenticationError)
    keys = set(frappe.defaults.get_defaults(frappe.session.user))
    keys.update(frappe.defaults.get_user_permissions(frappe.session.user))
    keys.update(('company', 'currency', 'selling_price_list', 'buying_price_list', 'cost_center'))
    defaults = {key: frappe.defaults.get_user_default(key) for key in keys}
    settings = ('number_format', 'float_precision', 'currency_precision', 'rounding_method')
    return {
        'user': frappe.session.user,
        'roles': list(frappe.get_roles(frappe.session.user)),
        'defaults': defaults,
        'system_defaults': {key: frappe.db.get_single_value('System Settings', key) for key in settings},
    }
