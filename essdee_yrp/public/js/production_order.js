frappe.ui.form.on("YRP Production Order", {
	refresh(frm) {
		render_lot_ordered_details(frm);
		render_price_requests(frm);
		render_time_and_action(frm);
	},
});

const PRODUCTION_ORDER_TA_GROUP = __("Time and Action");

function render_time_and_action(frm) {
	if (frm.is_new()) return;
	const requested_name = frm.doc.name;
	frappe.call({
		method: "essdee_yrp.time_and_action.production_order.get_production_order_time_and_action",
		args: { production_order: requested_name },
		callback({ message }) {
			if (frm.doc.name !== requested_name || !message) return;
			add_time_and_action_buttons(frm, message);
			show_time_and_action(frm, message);
		},
	});
}

function add_time_and_action_buttons(frm, context) {
	const time_and_action = context.time_and_action;
	if (context.can_create) {
		frm.add_custom_button(__("Create T&A"), () => frappe.production.time_and_action.open_create_dialog({
			against: "YRP Production Order",
			against_id: frm.doc.name,
			label: __("Production Order"),
			item: context.item,
			qty: context.qty,
			on_created: () => frm.reload_doc(),
		}), PRODUCTION_ORDER_TA_GROUP);
	}
	if (time_and_action && context.status === "In Progress") {
		frm.add_custom_button(__("Update T&A"), () => {
			frappe.route_options = { time_and_action };
			frappe.set_route("t_and_a_update");
		}, PRODUCTION_ORDER_TA_GROUP);
	}
	if (context.can_convert) {
		frm.add_custom_button(__("Convert to Lot T&A"), () => frappe.production.time_and_action.open_convert_dialog({
			time_and_action,
			on_done: () => frm.reload_doc(),
		}), PRODUCTION_ORDER_TA_GROUP);
	}
}

function show_time_and_action(frm, context) {
	frm.dashboard.parent.find(".production-order-time-and-action").remove();
	if (!context.time_and_action) return;
	const body = frm.dashboard.add_section(
		`<p>${time_and_action_summary(context)}</p><div class="production-order-time-and-action-report"></div>`,
		__("Time and Action"),
		"custom production-order-time-and-action",
	);
	frm.time_action_report = new frappe.production.ui.TimeActionReport(
		body.find(".production-order-time-and-action-report").get(0),
		context.time_and_action,
	);
	frm.dashboard.show();
}

function time_and_action_summary(context) {
	const link = frappe.utils.get_form_link("SD YRP Time and Action", context.time_and_action, true);
	const copies = context.copies.map((row) => `${frappe.utils.get_form_link("SD YRP Time and Action", row.name, true)} (${frappe.utils.escape_html(row.lot)})`);
	if (context.status !== "Frozen") return `${link} · ${frappe.utils.escape_html(__(context.status))}`;
	return `${link} · <span class="indicator-pill blue">${__("Frozen — converted to Lot T&A")}</span> ${copies.join(", ")}`;
}

function render_lot_ordered_details(frm) {
	const field = frm.fields_dict["lot_ordered_html"];
	if (!field) return;

	field.$wrapper.html("");
	frm.lot_ordered_view = null;

	if (frm.is_new()) return;

	const view = new frappe.production.ui.LotOrderedDetail(field.wrapper);
	const requested_name = frm.doc.name;
	frm.lot_ordered_view = view;
	frappe.call({
		method: "essdee_yrp.production_order.get_lot_ordered_details",
		args: { production_order: requested_name },
		callback(response) {
			// Ignore stale responses after switching to another record.
			if (frm.lot_ordered_view !== view || frm.doc.name !== requested_name) return;
			view.load_data(response.message || {});
		},
	});
}

const PRICE_REQUEST_STATUS_COLORS = { Approved: "green", Rejected: "red" };

function render_price_requests(frm) {
	const field = frm.fields_dict["ppo_price_request_html"];
	if (!field) return;

	const requests = (frm.doc.__onload || {}).price_requests || [];
	const heading = `<div class="control-label">${__("Price Changes")}</div>`;
	if (!requests.length) {
		field.$wrapper.html(
			`${heading}<div class="text-muted" style="padding:15px;">${__("No price change requests")}</div>`
		);
		return;
	}

	const headers = [
		"Request",
		"Status",
		"Requested By",
		"Requested At",
		"Approved/Rejected By",
		"Approved/Rejected At",
	].map((label) => `<th>${__(label)}</th>`);
	field.$wrapper.html(`${heading}<div style="padding:10px 0;">
		<table class="table table-bordered table-sm">
			<thead><tr>${headers.join("")}</tr></thead>
			<tbody>${requests.map(price_request_row).join("")}</tbody>
		</table>
	</div>`);
}

function price_request_row(request) {
	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
	const user = (value) => (value ? frappe.user.full_name(value) : "");
	const datetime = (value) => (value ? frappe.datetime.str_to_user(value) : "");
	const url = `/app/sd-yrp-ppo-price-request/${encodeURIComponent(String(request.name ?? ""))}`;
	const color = PRICE_REQUEST_STATUS_COLORS[request.status] || "orange";
	return `<tr>
		<td><a href="${url}">${escape(request.name)}</a></td>
		<td><span class="indicator-pill ${color}">${escape(request.status)}</span></td>
		<td>${escape(user(request.requested_by))}</td>
		<td>${escape(datetime(request.requested_at))}</td>
		<td>${escape(user(request.approved_by))}</td>
		<td>${escape(datetime(request.approved_at))}</td>
	</tr>`;
}
