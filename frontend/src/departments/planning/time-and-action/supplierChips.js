/** Supplier chips on T&A rows: planned suppliers (information only) and live Work Order / Purchase Order actuals. */
const NUMBER = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 })

export function supplierChipTone(chip) {
	if (!chip.is_planned) return "unplanned"
	return chip.actuals?.length ? "planned" : "hollow"
}

function actualLine(entry) {
	const isWorkOrder = entry.doctype === "YRP Work Order"
	const label = isWorkOrder ? "Work Order" : "Purchase Order"
	const documents = `${label}${entry.documents.length === 1 ? "" : "s"} ${entry.documents.join(", ")}`
	const sent = isWorkOrder ? `delivered ${NUMBER.format(entry.delivered)}` : `ordered ${NUMBER.format(entry.ordered)}`
	return `${documents}: ${sent}, received ${NUMBER.format(entry.received)}`
}

export function supplierChipTitle(chip) {
	const name = chip.supplier_name && chip.supplier_name !== chip.supplier ? `${chip.supplier_name} (${chip.supplier})` : chip.supplier
	const lines = [`${name} · ${chip.is_planned ? "Planned" : "Not planned"}`]
	if (!chip.actuals?.length) lines.push("No Work Order or Purchase Order yet")
	for (const entry of chip.actuals || []) lines.push(actualLine(entry))
	return lines.join("\n")
}

export function plannedSupplierValues(chips) {
	return (chips || []).filter((chip) => chip.is_planned).map((chip) => chip.supplier)
}

/** `{action: [supplier]}` for create: actions of the previewed master that have suppliers. */
export function withoutEmptySuppliers(plannedSuppliers, actions) {
	return Object.fromEntries(
		Object.entries(plannedSuppliers || {}).filter(([action, suppliers]) => suppliers?.length && actions.includes(action)),
	)
}
