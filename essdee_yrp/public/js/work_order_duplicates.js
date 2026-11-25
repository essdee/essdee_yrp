frappe.ui.form.on("YRP Work Order", {
	on_submit(frm) {
		show_duplicate_work_orders(frm.doc.name);
	},
});

function show_duplicate_work_orders(work_order) {
	frappe
		.call({
			method: "essdee_yrp.work_order_duplicates.get_duplicate_work_orders",
			args: { work_order },
		})
		.then(({ message: rows }) => {
			if (!rows?.length) return;
			new frappe.ui.Dialog({
				title: __("Work Order already created"),
				size: "large",
				fields: [{ fieldtype: "HTML", fieldname: "summary", options: duplicate_work_orders_html(rows) }],
			}).show();
		});
}

function duplicate_work_orders_html(rows) {
	const escape = frappe.utils.escape_html;
	const number = (value) => frappe.format(value || 0, { fieldtype: "Int" });
	const date = (value) => (value ? String(value).split("-").reverse().join("-") : "");
	const body = rows
		.map(
			(row) => `<tr>
				<td class="text-nowrap"><a style="text-decoration: underline" href="${frappe.utils.get_form_link("YRP Work Order", row.name)}">${escape(row.name)}</a></td>
				<td class="text-nowrap">${date(row.wo_date)}</td>
				<td>${escape(row.status || "")}</td>
				<td class="text-right">${number(row.planned_quantity)}</td>
				<td class="text-right">${number(row.total_no_of_pieces_delivered)}</td>
				<td class="text-right">${number(row.total_no_of_pieces_received)}</td>
				<td>${escape(row.created_by || "")}</td>
			</tr>`
		)
		.join("");
	return `<p>${__("A Work Order was already created against this Supplier for the same Lot, Item and Process.")}</p>
		<table class="table table-bordered table-condensed">
			<thead><tr>
				<th>${__("Work Order")}</th><th>${__("Date")}</th><th>${__("Status")}</th>
				<th class="text-right">${__("Planned")}</th><th class="text-right">${__("Delivered")}</th>
				<th class="text-right">${__("Received")}</th><th>${__("Created By")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table>`;
}
