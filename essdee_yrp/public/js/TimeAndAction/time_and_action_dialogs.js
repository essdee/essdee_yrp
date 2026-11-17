frappe.provide("frappe.production.time_and_action");

/** Create T&A for a Lot or Production Order: submitted Action Master, Start Date, Preview with Work Stations and Planned Suppliers. */
frappe.production.time_and_action.open_create_dialog = function ({ against, against_id, label, item, qty, on_created }) {
	const info = [
		[label, against_id],
		[__("Item"), item || ""],
		[__("Qty"), qty || 0],
	].map(([name, value]) => `<b>${name}</b> ${frappe.utils.escape_html(String(value))}`).join(" · ");
	const dialog = new frappe.ui.Dialog({
		title: __("Create Time and Action"),
		fields: [
			{ fieldtype: "HTML", fieldname: "against_info", options: `<p>${info}</p>` },
			{
				label: __("Action Master"),
				fieldname: "master",
				fieldtype: "Link",
				options: "SD YRP Action Master",
				reqd: 1,
				get_query: () => ({ filters: { disable: 0, docstatus: 1 } }),
			},
			{ label: __("Start Date"), fieldname: "start_date", fieldtype: "Date", reqd: 1 },
		],
		primary_action_label: __("Create"),
		primary_action: (values) => {
			dialog.disable_primary_action();
			frappe.call({
				method: "essdee_yrp.time_and_action.create.create_time_and_action",
				args: {
					against,
					against_id,
					master: values.master,
					start_date: values.start_date,
					work_stations: get_chosen_work_stations(dialog, values.master),
					planned_suppliers: get_chosen_planned_suppliers(dialog, values.master),
				},
				freeze: true,
				freeze_message: __("Creating Time and Action..."),
				callback: () => {
					dialog.hide();
					on_created?.();
				},
				always: () => dialog.enable_primary_action(),
			});
		},
		secondary_action_label: __("Preview"),
		secondary_action: () => preview_time_and_action(dialog),
	});
	dialog.show();
	return dialog;
};

function preview_time_and_action(dialog) {
	const values = dialog.get_values();
	if (!values) return;
	frappe.call({
		method: "essdee_yrp.time_and_action.create.get_schedule_preview",
		args: { master: values.master, start_date: values.start_date },
		callback: (response) => {
			const chosen = get_chosen_work_stations(dialog, values.master);
			const suppliers = get_chosen_planned_suppliers(dialog, values.master);
			response.message.forEach((row) => {
				row.work_station = chosen[row.action] || row.work_station;
				row.planned_suppliers = suppliers[row.action] || [];
			});
			const preview = new frappe.ui.Dialog({
				title: __("Time and Action Preview"),
				size: "extra-large",
				fields: [{ fieldname: "preview_html", fieldtype: "HTML" }],
				primary_action_label: __("Close"),
				primary_action: () => preview.hide(),
			});
			const view = new frappe.production.ui.TimeActionPreview(preview.fields_dict.preview_html.wrapper);
			view.load_data({ [values.master]: response.message }, values.start_date);
			dialog.work_station_preview = { master: values.master, view };
			preview.show();
		},
	});
}

function get_chosen_work_stations(dialog, master) {
	const preview = dialog.work_station_preview;
	return preview?.master === master ? preview.view.get_work_stations() : {};
}

function get_chosen_planned_suppliers(dialog, master) {
	const preview = dialog.work_station_preview;
	return preview?.master === master ? preview.view.get_planned_suppliers() : {};
}

/** Convert to Lot T&A: pick linked Lots without a T&A, confirm, then show links to the created T&As. */
frappe.production.time_and_action.open_convert_dialog = function ({ time_and_action, on_done }) {
	frappe.call({
		method: "essdee_yrp.time_and_action.production_order.get_convertible_lots",
		args: { time_and_action },
		callback: ({ message: lots }) => {
			if (!lots?.length) {
				frappe.msgprint(__("Every Lot linked to this Production Order already has a Time and Action, or none is linked."));
				return;
			}
			show_convert_dialog(time_and_action, lots, on_done);
		},
	});
};

function show_convert_dialog(time_and_action, lots, on_done) {
	const dialog = new frappe.ui.Dialog({
		title: __("Convert to Lot T&A"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "help",
				options: `<p class="text-muted">${__("Each selected Lot gets a copy of {0}: rows, dependencies, work stations, dates, actual dates and reasons. {0} is then frozen.", [time_and_action])}</p>`,
			},
			{
				label: __("Lots"),
				fieldname: "lots",
				fieldtype: "MultiCheck",
				options: lots.map((lot) => ({ label: `${lot.name} · ${lot.item || ""} · ${lot.qty || 0}`, value: lot.name })),
			},
		],
		primary_action_label: __("Convert"),
		primary_action: ({ lots: selected }) => {
			if (!selected?.length) {
				frappe.msgprint(__("Select at least one Lot."));
				return;
			}
			frappe.confirm(__("Create a Lot T&A for {0} and freeze {1}?", [selected.join(", "), time_and_action]), () => {
				dialog.hide();
				convert(time_and_action, selected, on_done);
			});
		},
	});
	dialog.show();
}

function convert(time_and_action, lots, on_done) {
	frappe.call({
		method: "essdee_yrp.time_and_action.production_order.convert_to_lot_time_and_action",
		args: { time_and_action, lots },
		freeze: true,
		freeze_message: __("Converting to Lot T&A..."),
		callback: ({ message: created }) => {
			const links = (created || []).map((name, index) => `${frappe.utils.get_form_link("SD YRP Time and Action", name, true)} (${frappe.utils.escape_html(lots[index])})`);
			frappe.msgprint({ title: __("Lot T&A created"), message: links.join("<br>"), indicator: "green" });
			on_done?.();
		},
	});
}

/** Split T&A: pick Lots without a T&A (searchable), confirm, then show links to the created T&As. The source continues. */
frappe.production.time_and_action.open_split_dialog = function ({ time_and_action, on_done }) {
	const dialog = new frappe.ui.Dialog({
		title: __("Split T&A"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "help",
				options: `<p class="text-muted">${__("Each selected Lot gets a copy of {0}: rows, dependencies, work stations, dates, actual dates and reasons. {0} continues, and each Lot is updated on its own.", [time_and_action])}</p>`,
			},
			{
				label: __("Lots"),
				fieldname: "lots",
				fieldtype: "MultiSelectList",
				reqd: 1,
				get_data: (txt) => get_split_lot_options(time_and_action, txt),
			},
		],
		primary_action_label: __("Split"),
		primary_action: ({ lots: selected }) => {
			if (!selected?.length) {
				frappe.msgprint(__("Select at least one Lot."));
				return;
			}
			frappe.confirm(__("Copy {0} to {1}? {0} continues.", [time_and_action, selected.join(", ")]), () => {
				dialog.hide();
				split(time_and_action, selected, on_done);
			});
		},
	});
	dialog.show();
	return dialog;
};

function get_split_lot_options(time_and_action, txt) {
	return frappe
		.xcall("essdee_yrp.time_and_action.split.get_split_lots", { time_and_action, txt })
		.then((lots) => (lots || []).map((lot) => ({
			value: lot.name,
			label: frappe.utils.escape_html(lot.name),
			description: frappe.utils.escape_html(`${lot.item || ""} · ${__("Qty")} ${lot.qty || 0}`),
		})));
}

function split(time_and_action, lots, on_done) {
	frappe.call({
		method: "essdee_yrp.time_and_action.split.split_time_and_action",
		args: { time_and_action, lots },
		freeze: true,
		freeze_message: __("Splitting Time and Action..."),
		callback: ({ message: created }) => {
			const links = (created || []).map((name, index) => `${frappe.utils.get_form_link("SD YRP Time and Action", name, true)} (${frappe.utils.escape_html(lots[index])})`);
			frappe.msgprint({ title: __("T&A split"), message: links.join("<br>"), indicator: "green" });
			on_done?.();
		},
	});
}
