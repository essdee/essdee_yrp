frappe.provide("essdee_yrp.ipd");

/** Approve confirmation listing the IPD's submitted Work Orders, changed processes highlighted. */
essdee_yrp.ipd.show_approve_dialog = function (frm, on_approve) {
	const dialog = new frappe.ui.Dialog({
		title: __("Approve {0}?", [frm.doc.name]),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "work_orders" }],
		primary_action_label: __("Approve"),
		primary_action() {
			dialog.hide();
			on_approve();
		},
	});
	const wrapper = dialog.fields_dict.work_orders.$wrapper;
	wrapper.html(`<div class="ipd-wo-loading text-muted">${__("Loading submitted Work Orders…")}</div>`);
	dialog.$wrapper.on("hidden.bs.modal", () => essdee_yrp.ipd.hide_wo_card(true));
	dialog.show();
	frappe
		.xcall("essdee_yrp.merch.ipd_workspace.get_ipd_approval_work_orders", { name: frm.doc.name })
		.then((data) => {
			wrapper.html(essdee_yrp.ipd.work_orders_html(data));
			essdee_yrp.ipd.bind_wo_cards(wrapper, data.orders);
		})
		.catch(() => wrapper.html(`<div class="text-danger">${__("Unable to load the Work Orders.")}</div>`));
};

essdee_yrp.ipd.display_date = function (value) {
	const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
	return match ? `${match[3]}-${match[2]}-${match[1]}` : "—";
};

essdee_yrp.ipd.quantity = (value) => `${+Number(value || 0).toFixed(3)}`;

essdee_yrp.ipd.work_order_groups = function (orders) {
	const groups = new Map();
	orders.forEach((order) => {
		const process = order.process_name || "—";
		if (!groups.has(process)) groups.set(process, { process, orders: [], affected: false });
		const group = groups.get(process);
		group.orders.push(order);
		group.affected = group.affected || Boolean(order.is_affected);
	});
	return [...groups.values()].sort((first, second) => Number(second.affected) - Number(first.affected));
};

essdee_yrp.ipd.grid_html = function (grid) {
	const esc = frappe.utils.escape_html;
	if (!grid.total) return `<span class="text-muted">${__("No quantities")}</span>`;
	const head = grid.sizes.map((size) => `<th>${esc(size || __("Qty"))}</th>`).join("");
	const rows = grid.colours
		.map((colour, index) => {
			const cells = grid.cells[index]
				.map((cell) => `<td>${cell == null ? "" : essdee_yrp.ipd.quantity(cell)}</td>`)
				.join("");
			return `<tr><th>${esc(colour || "—")}</th>${cells}</tr>`;
		})
		.join("");
	return `<table class="ipd-wo-grid"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
};

essdee_yrp.ipd.order_html = function (order, index) {
	const esc = frappe.utils.escape_html;
	const closed = order.open_status === "Close" ? `<span class="ipd-wo-tag">${__("Closed")}</span>` : "";
	return `<div class="ipd-wo-order ${order.is_affected ? "is-affected" : ""}" tabindex="0" data-index="${index}">
		<div class="ipd-wo-order-head"><a href="/app/yrp-work-order/${encodeURIComponent(order.name)}" target="_blank">${esc(order.name)}</a>${closed}</div>
		<div class="ipd-wo-supplier">${esc(order.supplier_name || order.supplier || "")}</div>
		${essdee_yrp.ipd.grid_html(order.grid)}
		<div class="ipd-wo-total">${__("Total")} ${essdee_yrp.ipd.quantity(order.grid.total)}</div>
	</div>`;
};

essdee_yrp.ipd.work_orders_html = function (data) {
	const esc = frappe.utils.escape_html;
	const orders = data.orders || [];
	const index_of = new Map(orders.map((order, index) => [order.name, index]));
	const affected = orders.filter((order) => order.is_affected).length;
	const changes = (data.changes.processes || [])
		.map((entry) => {
			const more = entry.changes.length > 4 ? ` <span class="text-muted">+${entry.changes.length - 4} ${__("more")}</span>` : "";
			return `<p><b>${esc(entry.process)}</b> ${__("changed since the last approval")}: ${esc(entry.changes.slice(0, 4).join(" · "))}${more}</p>`;
		})
		.join("");
	const groups = essdee_yrp.ipd
		.work_order_groups(orders)
		.map((group) => {
			const note = group.affected ? `<span class="ipd-wo-tag is-warning">${__("Review: cancel and recreate if needed")}</span>` : "";
			const cards = group.orders.map((order) => essdee_yrp.ipd.order_html(order, index_of.get(order.name))).join("");
			return `<div class="ipd-wo-group ${group.affected ? "is-affected" : ""}">
				<div class="ipd-wo-process"><b>${esc(group.process)}</b> <span class="text-muted">${group.orders.length}</span> ${note}</div>
				<div class="ipd-wo-row">${cards}</div>
			</div>`;
		})
		.join("");
	const affected_tag = affected ? `<span class="ipd-wo-tag is-warning">${affected} ${__("in changed processes")}</span>` : "";
	return `${essdee_yrp.ipd.styles()}<div class="ipd-wo" data-testid="ipd-approval-work-orders">
		<div class="ipd-wo-header"><b>${__("Work Orders submitted")}</b> <span class="ipd-wo-tag">${orders.length}</span> ${affected_tag}</div>
		${changes ? `<div class="ipd-wo-changes">${changes}</div>` : ""}
		${orders.length ? groups : `<p class="text-muted">${__("No submitted Work Orders")}</p>`}
	</div>`;
};

essdee_yrp.ipd.card_html = function (order) {
	const esc = frappe.utils.escape_html;
	const row = (label, value) => `<dt>${__(label)}</dt><dd>${esc(String(value ?? "—"))}</dd>`;
	const note = order.is_affected
		? `<p class="ipd-wo-note">${esc(order.process_name)} ${__("changed since the last approval. Cancel and recreate this Work Order if it needs the change.")}</p>`
		: "";
	return `<b>${esc(order.name)}</b><dl>
		${row("Process", order.process_name + (order.is_rework ? " (rework)" : ""))}
		${row("Supplier", order.supplier_name || order.supplier)}
		${row("Lot", order.lot || "—")}
		${row("Date", essdee_yrp.ipd.display_date(order.wo_date))}
		${row("Status", order.open_status === "Close" ? "Closed" : "Open")}
		${row("Planned", essdee_yrp.ipd.quantity(order.planned_quantity))}
	</dl>${note}`;
};

essdee_yrp.ipd.hide_wo_card = function (now) {
	clearTimeout(essdee_yrp.ipd._card_timer);
	const hide = () => $(".ipd-wo-card").remove();
	if (now) hide();
	else essdee_yrp.ipd._card_timer = setTimeout(hide, 150);
};

essdee_yrp.ipd.bind_wo_cards = function (wrapper, orders) {
	wrapper.on("mouseenter focusin", ".ipd-wo-order", function () {
		essdee_yrp.ipd.hide_wo_card(true);
		const order = orders[Number(this.dataset.index)];
		const rect = this.getBoundingClientRect();
		const card = $(`<div class="ipd-wo-card">${essdee_yrp.ipd.card_html(order)}</div>`).appendTo(document.body);
		const top = rect.bottom + card.outerHeight() + 8 > window.innerHeight ? rect.top - card.outerHeight() - 6 : rect.bottom + 6;
		const left = Math.min(rect.left, window.innerWidth - card.outerWidth() - 8);
		card.css({ top: Math.max(top, 8), left: Math.max(left, 8) });
	});
	wrapper.on("mouseleave focusout", ".ipd-wo-order", () => essdee_yrp.ipd.hide_wo_card());
};

essdee_yrp.ipd.styles = function () {
	return `<style>
		.ipd-wo-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
		.ipd-wo-tag { display: inline-flex; padding: 1px 8px; border-radius: 999px; background: var(--subtle-fg); color: var(--text-muted); font-size: 11px; white-space: nowrap; }
		.ipd-wo-tag.is-warning { background: var(--bg-orange); color: var(--text-on-orange); }
		.ipd-wo-changes { background: var(--bg-orange); color: var(--text-on-orange); border-radius: 6px; padding: 6px 10px; margin-bottom: 8px; font-size: 12px; }
		.ipd-wo-changes p { margin: 2px 0; }
		.ipd-wo-group { border-top: 1px solid var(--border-color); padding: 6px 0 4px; }
		.ipd-wo-group.is-affected .ipd-wo-process b { color: var(--text-on-orange); }
		.ipd-wo-process { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 12px; }
		.ipd-wo-row { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; align-items: flex-start; }
		.ipd-wo-order { flex: none; display: grid; gap: 3px; min-width: 170px; padding: 7px 9px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--card-bg); font-size: 11px; }
		.ipd-wo-order.is-affected { border-color: var(--orange-500, #f59e0b); box-shadow: inset 3px 0 0 var(--orange-500, #f59e0b); background: var(--bg-orange); }
		.ipd-wo-order-head { display: flex; justify-content: space-between; gap: 6px; font-size: 12px; font-weight: 600; }
		.ipd-wo-supplier { color: var(--text-muted); max-width: 260px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.ipd-wo-total { color: var(--text-muted); font-weight: 600; }
		.ipd-wo-grid { border-collapse: collapse; font-variant-numeric: tabular-nums; }
		.ipd-wo-grid th, .ipd-wo-grid td { padding: 1px 5px; border: 1px solid var(--border-color); white-space: nowrap; }
		.ipd-wo-grid thead th { color: var(--text-muted); background: var(--subtle-fg); }
		.ipd-wo-grid tbody th { text-align: left; }
		.ipd-wo-grid td { text-align: right; }
		.ipd-wo-card { position: fixed; z-index: 1100; min-width: 220px; max-width: 320px; padding: 10px 12px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-bg); box-shadow: var(--shadow-lg); font-size: 12px; pointer-events: none; }
		.ipd-wo-card dl { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; margin: 6px 0 0; }
		.ipd-wo-card dt { color: var(--text-muted); font-weight: 400; }
		.ipd-wo-card dd { margin: 0; }
		.ipd-wo-note { margin: 6px 0 0; color: var(--text-on-orange); font-weight: 600; }
	</style>`;
};
