// Mappings of an approved IPD, or of an IPD the user cannot write, open read only.
(function install_ipd_mapping_lock() {
	if (frappe.essdee_ipd_mapping_lock_installed) return;
	frappe.essdee_ipd_mapping_lock_installed = true;

	const DOCTYPES = [
		"YRP Item Item Attribute Mapping",
		"YRP Item Dependent Attribute Mapping",
		"YRP Item BOM Attribute Mapping",
	];
	for (const doctype of DOCTYPES) {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				const reason = frm.doc.__onload?.ipd_mapping_lock;
				if (!reason) return;
				frm.set_intro(reason, "orange");
				frm.disable_form();
			},
		});
	}
})();
