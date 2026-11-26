import { formatAdd, formatMoney, formatPercent, formatPerUnitQty, formatQty, shortDoc } from "./lotValuation.js"

const row = (label, value, strong = false) => ({ label, value, strong })

const CATEGORY_NOTES = {
	material: "Value carried in from material inputs (yarn, cloth, panels, pieces), including what they inherited upstream.",
	process: "Job-work charge of each process (GRN qty × work order rate), plus freight and rounding.",
	accessories: "Bought trims consumed at IPD BOM quantity.",
	pi: "Purchase invoice rate difference: supplier invoice rate minus GRN rate, posted by a stock valuation adjustment.",
	wo_close: "Work order close: inputs issued to the supplier that did not come back are charged into the goods that did.",
}

const ADD_NOTES = {
	process: "Job-work charge of this process per unit, including freight and rounding.",
	accessories: "Accessories consumed per unit; see the accessories table of this process.",
	pi: "Purchase invoice rate difference posted on this receipt.",
	wo_close: "Unused inputs absorbed at work order close, shared over the goods received.",
	unattributed: "Value the lineage cannot attribute: pending adjustments, unexplained differences or missing lineage.",
}

export function categoryHover(category, summary) {
	const total = summary.ledger_value || 0
	return {
		title: category.label,
		rows: [row("Total", formatMoney(category.value), true), row("Per unit", formatMoney(summary.qty ? category.value / summary.qty : 0)), row("Share", formatPercent(category.value, total))],
		notes: [CATEGORY_NOTES[category.key] || "Value the lineage cannot attribute further: pending adjustments, negative stock, reconciliation or missing lineage."],
	}
}

export function waterfallHover(item, summary) {
	return {
		title: item.stage,
		rows: [row("Per unit", formatMoney(summary.qty ? item.value / summary.qty : 0), true), row("Total", formatMoney(item.value)), row("Share", formatPercent(item.value, summary.ledger_value))],
		notes: [],
	}
}

const lineRow = (line) => row(`${line.item} · ${shortDoc(line.voucher)}`, `${formatPerUnitQty(line.qty, line.unit)} × ${formatMoney(line.rate)} = ${formatMoney(line.amount)}`)

export function rateInHover(rateRow) {
	if (!rateRow.inputs.length) {
		const source = rateRow.residual ? `${rateRow.residual}: no traceable origin` : "Purchased / received value, no earlier process."
		return { title: "Rate in", rows: [row(`Rate on ${shortDoc(rateRow.voucher)}`, `${formatMoney(rateRow.purchase_rate)}/${rateRow.unit}`, true)], notes: [source] }
	}
	return {
		title: `Rate in = inputs per ${rateRow.unit}`,
		rows: [...rateRow.inputs.map(lineRow), row("Total", formatMoney(rateRow.rate_in), true)],
		notes: ["Click ▸ on the row for the same detail."],
	}
}

export function addHover(column, rateRow, section) {
	const rows = [row(`Per ${rateRow.unit}`, formatAdd(rateRow[column.key]), true)]
	if (column.key === "accessories") rows.unshift(...rateRow.accessory_inputs.map(lineRow))
	if (column.key === "wo_close") rows.unshift(...rateRow.wo_inputs.map(lineRow))
	if (column.key === "pi") rows.unshift(...rateRow.pi_docs.map((doc) => row(shortDoc(doc.name), `via ${shortDoc(doc.adjustment)}`)))
	if (column.key === "process") rows.unshift(row(`Charged on ${shortDoc(rateRow.voucher)}`, section.who || "—"))
	return { title: `${column.label.slice(2)} per ${rateRow.unit}`, rows, notes: [ADD_NOTES[column.key]] }
}

export function rateOutHover(rateRow, columns) {
	const rows = [row("Rate in", formatMoney(rateRow.rate_in)), ...columns.map((column) => row(column.label, formatAdd(rateRow[column.key]))), row("= Rate out", formatMoney(rateRow.rate_out), true)]
	const notes = []
	if (rateRow.to?.length) notes.push(`Goes to: ${rateRow.to.map((target) => target.stage + (target.wo_close ? " (WO close)" : "")).join(", ")}`)
	if (rateRow.pieces_per_box) notes.push(`Per piece ${formatMoney(rateRow.rate_out_piece)} × ${formatQty(rateRow.pieces_per_box)} pieces per box.`)
	return { title: "Rate out = valuation rate when this process finished", rows, notes }
}

export function totalHover(rateRow) {
	return {
		title: "Total ₹",
		rows: [row(`${formatQty(rateRow.qty)} ${rateRow.uom_label} × ${formatMoney(rateRow.rate_out)}`, formatMoney(rateRow.total), true)],
		notes: [`Stock ledger value of ${rateRow.lines} receipt line${rateRow.lines === 1 ? "" : "s"} on ${shortDoc(rateRow.voucher)}.`],
	}
}

export function documentHover(doc) {
	return { title: doc.name, rows: [row("Type", doc.doctype)], notes: [] }
}

export function accessoryHover(kind, accessory, unit) {
	const rate = accessory.rate + accessory.pi
	if (kind === "pi") return { title: "Purchase invoice rate difference", rows: [row(accessory.pi_doc ? shortDoc(accessory.pi_doc.name) : "PI", `${formatAdd(accessory.pi)} per ${accessory.unit}`, true)], notes: [] }
	if (kind === "added") return { title: `₹ added per ${unit}`, rows: [row(`${formatPerUnitQty(accessory.per_unit)} × ${formatMoney(rate)}`, formatMoney(accessory.added_per_unit), true)], notes: [] }
	return { title: "Total ₹", rows: [row(`${formatPerUnitQty(accessory.qty)} ${accessory.unit} × ${formatMoney(rate)}`, formatMoney(accessory.total), true)], notes: ["Value consumed, first-in first-out."] }
}
