frappe.pages['t_and_a_update'].on_page_load = function(wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Time and Action Update',
		single_column: true
	});
	wrapper.ta_update = new frappe.production.ui.TandAUpdate($(wrapper).find(".layout-main-section"));
}

frappe.pages['t_and_a_update'].refresh = function(wrapper) {
	wrapper.ta_update?.load_from_route();
}
