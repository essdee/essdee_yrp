frappe.provide("essdee_yrp.work_order");

(() => {
	const METHOD = "essdee_yrp.work_order_recalculate";
	const KINDS = ["added", "updated", "removed", "kept", "unchanged"];
	const LABELS = {
		added: __("Added"),
		updated: __("Updated"),
		removed: __("Removed"),
		kept: __("Kept"),
		unchanged: __("No change"),
	};
	const COLOURS = { added: "green", updated: "green", removed: "red", kept: "orange", unchanged: "gray" };

	function quantity(value, uom) {
		if (value === null || value === undefined) return "&mdash;";
		return `${format_number(value, null, 3)} ${frappe.utils.escape_html(uom || "")}`;
	}

	function counts_text(plan) {
		const count = (kind) => (plan[kind] || []).length;
		return __("{0} added, {1} updated, {2} removed, {3} row(s) kept.", [
			count("added"),
			count("updated"),
			count("removed"),
			count("kept"),
		]);
	}

	function render_plan(plan) {
		const rows = KINDS.flatMap((kind) =>
			(plan[kind] || []).map((row) => `<tr>
				<td>${frappe.utils.escape_html(row.item_variant || "")}</td>
				<td class="text-right">${quantity(row.old_qty, row.uom)}</td>
				<td class="text-right">${quantity(row.new_qty, row.uom)}</td>
				<td><span class="indicator-pill ${COLOURS[kind]}">${LABELS[kind]}</span>
					${row.reason ? `<div class="text-muted small">${frappe.utils.escape_html(row.reason)}</div>` : ""}</td>
			</tr>`)
		);
		if (!rows.length) {
			return `<p class="text-muted">${__("This Work Order has no accessory deliverables to recalculate.")}</p>`;
		}
		const intro = plan.has_changes
			? counts_text(plan)
			: (plan.kept || []).length
				? __("No changes to apply. {0} row(s) kept.", [(plan.kept || []).length])
				: __("Deliverables already match the Item Production Detail.");
		return `<p class="text-muted">${intro}</p>
			<div style="max-height: 55vh; overflow: auto;">
				<table class="table table-bordered table-condensed">
					<thead><tr>
						<th>${__("Item")}</th>
						<th class="text-right">${__("Current Qty")}</th>
						<th class="text-right">${__("Recalculated Qty")}</th>
						<th>${__("Result")}</th>
					</tr></thead>
					<tbody>${rows.join("")}</tbody>
				</table>
			</div>`;
	}

	function apply(frm, dialog) {
		frappe.call({
			method: `${METHOD}.apply_recalculate_deliverables`,
			args: { work_order: frm.doc.name, modified: frm.doc.modified },
			freeze: true,
			freeze_message: __("Recalculating deliverables..."),
			callback(r) {
				const plan = r.message || {};
				dialog.hide();
				frappe.msgprint({
					title: __("Deliverables Recalculated"),
					message: render_plan(plan),
					indicator: plan.has_changes ? "green" : "blue",
					wide: true,
				});
				frm.reload_doc();
			},
		});
	}

	essdee_yrp.work_order.open_recalculate_deliverables_dialog = function (frm) {
		frappe.call({
			method: `${METHOD}.get_recalculate_deliverables_preview`,
			args: { work_order: frm.doc.name },
			freeze: true,
			freeze_message: __("Recalculating deliverables..."),
			callback(r) {
				const plan = r.message || {};
				const dialog = new frappe.ui.Dialog({
					title: __("Recalculate Deliverables"),
					size: "extra-large",
					fields: [
						{
							fieldtype: "HTML",
							fieldname: "intro",
							options: `<p>${__(
								"Accessory deliverables are rebuilt from the current Item Production Detail. Delivered items stay unchanged; for a delivered item whose variant changed, use Change Item. Sewing Plan and Quality Inspection entries are not affected."
							)}</p>`,
						},
						{ fieldtype: "HTML", fieldname: "plan", options: render_plan(plan) },
					],
					primary_action_label: __("Recalculate"),
					primary_action() {
						apply(frm, dialog);
					},
				});
				dialog.show();
				if (!plan.has_changes) dialog.get_primary_btn().prop("disabled", true);
			},
		});
	};
})();
