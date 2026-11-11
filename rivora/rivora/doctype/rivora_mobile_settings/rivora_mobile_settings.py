from frappe.model.document import Document

class RivoraMobileSettings(Document):
    def validate(self):
        from rivora.presentation import validate_home_rules
        validate_home_rules(self)
        from rivora.entry_notifications import validate_settings
        validate_settings(self)
