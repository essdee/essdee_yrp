import { formatDisplayDatetime } from "../../../../utils/dateFormat.js"

export const VALUATION_TAB = { key: "valuation", label: "Valuation" }

/** Summary categories in stacked-bar order; `unattributed` only shows when non-zero. */
export const CATEGORIES = [
	{ key: "material", label: "Material in" },
	{ key: "process", label: "Process cost" },
	{ key: "accessories", label: "Accessories" },
	{ key: "pi", label: "PI adj" },
	{ key: "wo_close", label: "WO close" },
	{ key: "unattributed", label: "Unattributed" },
]

const money = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const quantity = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 })

export function formatMoney(value) {
	const amount = Math.abs(Number(value) || 0) < 0.005 ? 0 : Number(value) || 0
	return `₹${money.format(amount)}`
}

export function formatQty(value, uom = "") {
	return `${quantity.format(Number(value) || 0)}${uom ? ` ${uom}` : ""}`
}

export function formatPercent(part, whole) {
	return whole ? `${((part / whole) * 100).toFixed(1)}%` : "0.0%"
}

/** Valuation tab only for System Managers; the API refuses everyone else too. */
export function valuationTabs(tabs, isSystemManager) {
	return isSystemManager ? [...tabs, VALUATION_TAB] : tabs
}

export function isRunning(status) {
	return status === "Queued" || status === "Running"
}

export function computedAtLabel(state) {
	return state?.computed_at ? formatDisplayDatetime(state.computed_at) : ""
}

/** Waterfall bars: each row starts where the previous one ended. */
export function waterfallRows(summary) {
	const rows = summary?.waterfall || []
	const total = rows.reduce((sum, row) => sum + row.value, 0)
	let running = 0
	let low = 0
	let high = 0
	const placed = rows.map((row) => {
		const start = running
		running += row.value
		low = Math.min(low, start, running)
		high = Math.max(high, start, running)
		return { ...row, start, end: running }
	})
	const span = high - low || 1
	return {
		total,
		rows: placed.map((row) => ({
			...row,
			category: waterfallCategory(row.stage),
			left: ((Math.min(row.start, row.end) - low) / span) * 100,
			width: (Math.abs(row.value) / span) * 100,
		})),
	}
}

export function waterfallCategory(stage) {
	if (stage.endsWith(" WO close")) return "wo_close"
	if (stage.endsWith(" PI adj")) return "pi"
	if (stage.endsWith(" cost") || stage === "Freight") return "process"
	if (stage === "Purchased accessories") return "accessories"
	if (["Pending adjustment", "Negative stock", "Stock Reconciliation", "Untraced ledger stock", "Ledger replay difference", "Lineage missing", "Adjustment via inactive link", "Unexplained"].includes(stage)) return "unattributed"
	return "material"
}

export function categoryRows(summary) {
	const categories = summary?.categories || {}
	return CATEGORIES.filter((category) => category.key !== "unattributed" || Math.abs(categories.unattributed || 0) > 0.005).map((category) => ({
		...category,
		value: categories[category.key] || 0,
	}))
}

const perUnitQuantity = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 })

/** Fixed addition columns of every rate section, in order; `unattributed` only when the lot has any. */
const ADD_COLUMNS = [
	{ key: "process", label: "+ Process cost" },
	{ key: "accessories", label: "+ Accessories" },
	{ key: "pi", label: "+ PI adjustment" },
	{ key: "wo_close", label: "+ WO close" },
	{ key: "unattributed", label: "+ Unattributed" },
]

export function addColumns(rateSections) {
	return ADD_COLUMNS.filter((column) => column.key !== "unattributed" || rateSections?.has_unattributed)
}

export function isZero(value) {
	return Math.abs(Number(value) || 0) < 0.005
}

/** An addition: "—" when zero, else signed money. */
export function formatAdd(value) {
	if (isZero(value)) return "—"
	return `${value < 0 ? "−" : "+"}${formatMoney(Math.abs(value))}`
}

export function formatPerUnitQty(value, unit = "") {
	return `${perUnitQuantity.format(Number(value) || 0)}${unit ? ` ${unit}` : ""}`
}

export function shortDoc(name) {
	return String(name || "").replace(/^YRP-/, "").replace(/-\d{4}-/, "-")
}

/** Results computed before the rate build-up existed have no sections and need a recalculation. */
export function hasRateSections(result) {
	return Boolean(result?.rate_sections?.sections?.length)
}

/** Packed root valued per box: box count and per-box rate per item, or null when the root is not boxed. */
export function packedBoxes(rateSections) {
	const perBox = rateSections?.pieces_per_box
	if (!perBox || !rateSections.sections?.length) return null
	const items = new Map()
	for (const row of rateSections.sections.at(-1).rows) {
		const entry = items.get(row.item) || { item: row.item, boxes: 0, total: 0 }
		entry.boxes += row.qty
		entry.total += row.total
		items.set(row.item, entry)
	}
	const sizes = [...items.values()].map((entry) => ({ ...entry, rate: entry.boxes ? entry.total / entry.boxes : 0 }))
	return { perBox, sizes, boxes: sizes.reduce((sum, size) => sum + size.boxes, 0), total: sizes.reduce((sum, size) => sum + size.total, 0) }
}

/** Root section total against the stock ledger value of the root receipts, to the paisa. */
export function rateReconciliation(result) {
	const ledger = result?.summary?.ledger_value || 0
	const total = result?.rate_sections?.root_total || 0
	const difference = Math.round(ledger * 100) / 100 - Math.round(total * 100) / 100
	const unexplained = result?.summary?.checks?.unexplained_value || 0
	const unattributed = result?.summary?.categories?.unattributed || 0
	return { ledger, total, difference, unexplained, unattributed, ok: isZero(difference) && isZero(unexplained) }
}

export function itemLabel(row, section) {
	return section.pieces_per_box ? `Packed box · ${row.item}` : row.item
}

/** Small tags after an item: lineage gaps and where a row goes only at work order close. */
export function itemTags(row) {
	const tags = row.residual ? [{ label: row.residual, tone: "warn" }] : []
	for (const target of row.to || []) {
		if (target.wo_close) tags.push({ label: `→ ${target.stage} (WO close)`, tone: "wo_close" })
	}
	return tags
}

export function howToRead(result) {
	const boxes = packedBoxes(result.rate_sections)
	const summary = result.summary
	const output = boxes ? `these ${formatQty(boxes.boxes)} boxes (${formatQty(summary.qty)} pieces)` : `these ${formatQty(summary.qty, summary.uom?.toLowerCase())}`
	const boxed = boxes ? ` ${result.root_stage} is valued per box of ${formatQty(boxes.perBox)} pieces, so its rates are per box.` : ""
	return `Rows are the receipts that feed ${output}; Total ₹ = Qty × Rate out.${boxed} Hover any figure for its source.`
}
