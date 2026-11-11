frappe.pages["employee-location-tr"].on_page_load = function (wrapper) {
    wrapper.rivora_mobile_location_ready = frappe.require("/assets/rivora/js/rivora_employee_location_desk.js")
        .then(() => { wrapper.rivora_mobile_location = new rivora.LiveLocationDesk(wrapper); return wrapper.rivora_mobile_location; });
};
frappe.pages["employee-location-tr"].on_page_show = function (wrapper) {
    wrapper.rivora_mobile_location_ready.then(view => view.show());
};
