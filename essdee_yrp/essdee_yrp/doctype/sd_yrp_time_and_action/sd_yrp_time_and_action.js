// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.ui.form.on("SD YRP Time and Action", {
	refresh(frm) {
		frm.set_df_property("details", "cannot_add_rows", true);
		frm.set_df_property("details", "cannot_delete_rows", true);
		if (frm.doc.status === "Completed" && frappe.user.has_role("System Manager")) {
			frm.add_custom_button(__("Reopen T&A"), () => reopen_time_and_action(frm));
		}
	},
});

function reopen_time_and_action(frm) {
	frappe.confirm(__("Reopen {0}? The actual date of the last action is removed.", [frm.doc.name]), () => {
		frappe.call({
			method: "essdee_yrp.time_and_action.update.reopen_time_and_action",
			args: { time_and_action: frm.doc.name },
			freeze: true,
			callback: () => frm.reload_doc(),
		});
	});
}
