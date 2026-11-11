import frappe


def execute():
    for row in frappe.get_all('Rivora Mobile Home Rule',
            filters={'parent': 'Rivora Mobile Settings', 'parenttype': 'Rivora Mobile Settings'},
            fields=['name', 'allowed_doctypes']):
        if row.get('allowed_doctypes') is None:
            frappe.db.set_value('Rivora Mobile Home Rule', row.name,
                'allowed_doctypes', 'ToDo', update_modified=False)
