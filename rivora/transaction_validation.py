"""Additional mobile party-selection policy; normal ERPNext validation follows."""
import frappe
from frappe import _

PARTY_FIELDS = {
    'Quotation':'party_name','Sales Order':'customer','Sales Invoice':'customer','Delivery Note':'customer',
    'Supplier Quotation':'supplier','Purchase Order':'supplier','Purchase Invoice':'supplier','Purchase Receipt':'supplier',
}

def require_party(doc):
    field=PARTY_FIELDS.get(doc.doctype)
    if not field:
        return
    if doc.doctype=='Quotation' and not doc.get('quotation_to'):
        frappe.throw(_('Quotation To is required for mobile saving'),frappe.MandatoryError)
    if not str(doc.get(field) or '').strip():
        label='Quotation party' if field=='party_name' else field.title()
        frappe.throw(_('{0} is required for mobile saving').format(_(label)),frappe.MandatoryError)

def before_validate(doc, method=None):
    # Covers the normal REST Save/Submit paths used by the app as well as the
    # explicit mobile save endpoint. Desk's own Quotation policy is unchanged.
    if getattr(frappe,'get_request_header',lambda key:None)('X-Rivora-Mobile')=='1':
        require_party(doc)
