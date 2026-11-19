/** Display rules for the "Review before approving" IPD dialog; data comes from get_ipd_approval_summary. */

export const SECTION_ORDER = ["colours", "panels", "weight", "cloth_accessories", "accessories", "embellishment"]

export function grams(weight) {
	return weight == null || Number(weight) === 0 ? "—" : `${+(Number(weight) * 1000).toFixed(1)} g`
}

export function kilograms(weight) {
	return weight == null || Number(weight) === 0 ? "—" : `${+Number(weight).toFixed(4)}`
}

export function quantity(value) {
	return `${+Number(value || 0).toFixed(3)}`
}

/** Approve needs the warnings acknowledged whenever the summary lists any. */
export function approvalGate(warnings = [], acknowledged = false, busy = false) {
	const needsAcknowledgement = warnings.length > 0
	return { needsAcknowledgement, canApprove: !busy && (!needsAcknowledgement || acknowledged) }
}

export function orderedSections(sections = []) {
	return SECTION_ORDER.map((key) => sections.find((section) => section.key === key)).filter(Boolean)
}

export function warningsFor(warnings = [], key) {
	return warnings.filter((warning) => warning.section === key)
}

export function sectionState(warnings, key) {
	const list = warningsFor(warnings, key)
	if (list.some((warning) => warning.level === "danger")) return "danger"
	if (list.some((warning) => warning.level === "warning")) return "warning"
	return "ok"
}

export function sizeRange(sizes = []) {
	if (sizes.length > 2) return `${sizes[0]} – ${sizes[sizes.length - 1]}`
	return sizes.join(", ")
}

export function weightSpan(span) {
	if (!span) return "—"
	return span.min === span.max ? `${kilograms(span.min)} kg` : `${kilograms(span.min)}–${kilograms(span.max)} kg`
}

function plural(count, word) {
	return `${count} ${word}${count === 1 ? "" : "s"}`
}

export function sectionCount(section) {
	const data = section.data
	if (section.key === "colours") return plural(data.packing.length, "colour")
	if (section.key === "panels") return plural(data.length, "panel")
	if (section.key === "embellishment") return plural(data.embellishments.length, "process")
	if (section.key === "weight") return `${plural(data.rows.length, "row")} from ${data.source_rows}`
	return plural(data.length, "item")
}

/** "All colours" when a row covers every IPD colour, else the colours it covers. */
export function weightColourChips(colours = [], allColours = []) {
	const covered = new Set(colours)
	const coversAll = allColours.length > 1 && allColours.every((colour) => covered.has(colour))
	return coversAll ? ["All colours"] : colours
}

/** Piece weight rows with the leading attribute cells shown only where they change. */
export function weightRows(weight, allColours = []) {
	let previous = {}
	return weight.rows.map((row) => {
		const changed = Object.keys(row.values).filter((key) => previous[key] !== row.values[key])
		previous = row.values
		return {
			...row,
			colourChips: weightColourChips(row.colours, allColours),
			shown: Object.fromEntries(changed.map((key) => [key, row.values[key]])),
			startsGroup: changed.length > 0,
		}
	})
}

export function weightBasis(weight) {
	return weight.basis.length ? weight.basis.join(" × ") : "whole piece"
}

export function panelsByPart(panels, attributes) {
	const parts = attributes.is_set_item ? attributes.set_parts : [""]
	return parts.map((part) => {
		const list = panels.filter((panel) => !attributes.is_set_item || panel.part === part)
		return { part, panels: list, pieces: list.reduce((sum, panel) => sum + (panel.qty || 0), 0) }
	})
}

export function perPiece(accessory) {
	const bom = `${quantity(accessory.qty_of_bom_item)} ${accessory.uom}`.trim()
	return accessory.qty_of_product === 1 ? bom : `${bom} / ${quantity(accessory.qty_of_product)} pcs`
}

/** Short "BOM value for garment values" lines of an attribute-mapped accessory. */
export function mappingLines(accessory, max = 2) {
	const summary = accessory.mapping?.summary || []
	const showQuantity = new Set(summary.map((line) => line.qty)).size > 1
	const lines = summary.slice(0, max).map((line) => ({
		bom: line.bom,
		quantity: showQuantity ? `×${quantity(line.qty)}` : "",
		for: line.for.length > 4 ? `${line.for.slice(0, 3).join(", ")} +${line.for.length - 3}` : line.for.join(", "),
	}))
	return { lines, more: Math.max(summary.length - max, 0), same: (accessory.mapping?.same || []).join(", ") }
}

export function clothAccessoryWeight(accessory) {
	const weights = accessory.weights
	const dia = [...new Set(weights.map((row) => row.dia))].join(", ")
	const same = new Set(weights.map((row) => String(row.weight))).size === 1
	if (!weights.length) return { missing: true }
	if (same) {
		const scope = weights.length > 1 ? `all ${weights.length} ${accessory.by.toLowerCase()}s` : weights[0].key
		return { single: `${kilograms(weights[0].weight)} kg`, note: `${scope} · ${dia}` }
	}
	return { list: weights.map((row) => ({ key: row.key, weight: kilograms(row.weight) })), note: dia }
}

export function clothAccessoryColours(accessory) {
	const colours = accessory.colours
	const cloths = [...new Set(colours.map((row) => row.cloth))].join(", ")
	return { empty: !colours.length, sameAsGarment: colours.every((row) => row.colour === row.major), colours, cloths }
}

export function processFlow(coreProcesses = []) {
	return coreProcesses.filter((row) => row.process).map((row) => (row.in ? `${row.process} (${row.in} → ${row.out})` : row.process)).join(" → ")
}
