import {
	buildFabricPayload, canCalculateFabric, fabricColourError, fabricContractError, fabricContractLists, fabricWarnings, hydrateFabricRows,
} from "../../../frontend/src/departments/fabric-store/fabricCalculate.js"

/** Knitting WOs whose fabric rows are all manual yarn/cloth contracts, as in /web. */
export function isKnittingContract(context) {
	const rows = context.rows || []
	return rows.length > 0 && rows.every((row) => row.manual_io)
}

function contractItemLabel(item) {
	const attributes = Object.values(item.attrs || {}).filter(Boolean)
	return `${[item.item, ...attributes].join(" · ")} (${item.uom || "Kg"})`
}

function contractFieldname(rowIndex, listIndex, itemIndex) {
	return `contract_${rowIndex}_${listIndex}_${itemIndex}`
}

function contractListFields(list, rowIndex, listIndex) {
	return [
		{ fieldtype: "HTML", options: `<div class="yrp-knitting-contract-head"><b>${list.title}</b> <span class="text-muted small">${list.hint}</span></div>` },
		...list.items.map((item, itemIndex) => ({
			fieldtype: "Float",
			fieldname: contractFieldname(rowIndex, listIndex, itemIndex),
			label: contractItemLabel(item),
			default: item.qty,
		})),
	]
}

export function getKnittingContractFields(rows) {
	return rows.flatMap((row, rowIndex) => {
		const fields = [{ fieldtype: "Section Break", label: `${row.cloth_item} (${row.production_detail})` }]
		if (row.needs_colour) {
			fields.push({ fieldtype: "Autocomplete", label: "Cloth Colour", fieldname: `colour_${rowIndex}`, options: row.colour_options || [], default: row.colour || undefined })
		}
		fabricContractLists(row).forEach((list, listIndex) => {
			if (listIndex) fields.push({ fieldtype: "Column Break" })
			fields.push(...contractListFields(list, rowIndex, listIndex))
		})
		return fields
	})
}

function applyContractValues(rows, values) {
	rows.forEach((row, rowIndex) => {
		if (row.needs_colour) row.colour = values[`colour_${rowIndex}`] || ""
		fabricContractLists(row).forEach((list, listIndex) => {
			list.items.forEach((item, itemIndex) => {
				item.qty = Number(values[contractFieldname(rowIndex, listIndex, itemIndex)] || 0)
			})
		})
	})
}

/** Applies dialog values to the hydrated rows and returns the /web calculate payload. */
export function getKnittingContractPayload(context, rows, values) {
	applyContractValues(rows, values)
	const error = rows.map((row) => fabricColourError(row) || fabricContractError(row)).find(Boolean)
		|| (canCalculateFabric(context, rows) ? "" : "Enter a quantity for at least one row.")
	return { error, payload: error ? null : buildFabricPayload(context, rows) }
}

export function renderKnittingContractDialog(frm, context) {
	const rows = hydrateFabricRows(context)
	const dialog = new frappe.ui.Dialog({
		title: __("Calculate Fabric Deliverables — {0}", [frm.doc.process_name]),
		size: "large",
		fields: [
			{ fieldtype: "HTML", options: `<div class="text-muted small">${__("Left: yarn you deliver. Right: fabric you expect back. Each IPD-valid physical variant appears once.")}</div>` },
			...getKnittingContractFields(rows),
		],
		primary_action_label: __("Calculate"),
		primary_action(values) {
			const { error, payload } = getKnittingContractPayload(context, rows, values)
			if (error) return frappe.msgprint(__(error))
			fabricWarnings(rows).forEach((warning) => frappe.msgprint({ message: warning, indicator: "orange" }))
			frappe.call({
				method: "essdee_yrp.api.work_order.calculate_fabric_deliverables",
				args: { work_order: frm.doc.name, rows: payload.rows, source_process: payload.source_process },
				freeze: true,
				callback(response) {
					dialog.hide()
					const result = response.message || {}
					frappe.show_alert({
						message: __("Calculated {0} deliverable(s) and {1} receivable(s).", [result.deliverables, result.receivables]),
						indicator: "green",
					})
					frm.reload_doc()
				},
			})
		},
	})
	dialog.show()
	return dialog
}
