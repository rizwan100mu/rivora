# Copyright (c) 2022, Nesscale Solutions Private Limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from rivora.setup import disable_geolocation_tracking


class RivoraSettings(Document):
    def on_update(self):
        disable_geolocation_tracking()
