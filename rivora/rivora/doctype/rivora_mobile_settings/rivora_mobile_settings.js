frappe.ui.form.on('Rivora Mobile Settings', {
  refresh(frm) {
    if (!frappe.user_roles.includes('System Manager')) return;
    const method = 'rivora.firebase_settings.';
    const updateStatus = value => frm.set_df_property('firebase_status', 'options',
      '<p>' + (value.configured
        ? __('Firebase configured') + (value.project_id ? ': ' + frappe.utils.escape_html(value.project_id) : '')
        : __('Firebase not configured. Upload the Admin SDK JSON for project rizora-5a6e6.')) + '</p>');
    frappe.call({method: method + 'configuration_status', type: 'POST'}).then(r => updateStatus(r.message));
    frm.add_custom_button(__('Upload Firebase JSON'), () => {
      if (frm.is_dirty()) {
        frappe.msgprint(__('Save the settings before uploading Firebase credentials.'));
        return;
      }
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.json,application/json';
      input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;
        if (file.size > 32768) {
          frappe.msgprint(__('Choose a Firebase service-account JSON file smaller than 32 KB.'));
          return;
        }
        await frappe.call({
          method: method + 'upload_credentials', type: 'POST',
          args: {service_account_json: await file.text()},
          freeze: true, freeze_message: __('Saving Firebase configuration...'),
          callback(r) {
            updateStatus(r.message);
            frappe.show_alert({message: __('Firebase configured. Run Server push test on your phone.'), indicator: 'green'});
          }
        });
      };
      input.click();
    });
  }
});

frappe.ui.form.on('Rivora Mobile Home Rule', {
  choose_doctypes(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const current = row.allowed_doctypes == null ? ['ToDo'] : row.allowed_doctypes.split('\n').map(value => value.trim()).filter(Boolean);
    const dialog = new frappe.ui.Dialog({
      title: __('Allowed DocTypes for {0}', [row.user_type || __('User Type')]),
      fields: [{
        fieldname: 'doctypes', fieldtype: 'MultiSelectPills', label: __('Allowed DocTypes'),
        get_data: text => frappe.db.get_link_options('DocType', text, {istable: 0, issingle: 0}),
      }],
      primary_action_label: __('Apply'),
      async primary_action(values) {
        await frappe.model.set_value(cdt, cdn, 'allowed_doctypes', [...new Set(values.doctypes || [])].join('\n'));
        frm.refresh_field('home_rules');
        dialog.hide();
      },
    });
    dialog.set_value('doctypes', current);
    dialog.show();
  },
});
