import { bulkOutcome } from "../../../components/common/listBulkActions.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"

export const APPROVE_ACTION = { label: "Approve", icon: "pi pi-check", severity: "primary", done: "approved" }

export const GRAMMAGE_FILTERS = [
	{ key: "lot", label: "Lot", doctype: "SD YRP Lot" },
	{ key: "item", label: "Item", doctype: "Item" },
	{ key: "cutting_plan", label: "Cutting Plan", doctype: "SD YRP Cutting Plan" },
	{ key: "work_order", label: "Work Order", doctype: "YRP Work Order" },
]

export const GRAMMAGE_COLUMNS = [
	{ field: "lot", label: "Lot" },
	{ field: "cutting_plan", label: "Cutting Plan" },
	{ field: "work_order", label: "Work Order" },
	{ field: "lay_no", label: "Lay No" },
	{ field: "posting_date", label: "LaySheet Date", date: true },
	{ field: "item_name", label: "Item" },
	{ field: "required_pcs_weight", label: "REQD Weight", numeric: true },
	{ field: "piece_weight", label: "Actual Weight", numeric: true },
]

/** Display text for one cell; dates read DD-MM-YYYY. */
export function grammageCellText(row, column) {
	const value = row?.[column.field]
	if (column.numeric) return formatPieceWeight(value)
	if (column.date) return formatDisplayDate(value, "—")
	return value || value === 0 ? String(value) : "—"
}

export function emptyGrammageFilters() {
	return Object.fromEntries(GRAMMAGE_FILTERS.map((filter) => [filter.key, ""]))
}

/** Only the filters with a value, so the server sees no empty filters. */
export function grammageFilterArgs(filters) {
	return Object.fromEntries(Object.entries(filters).filter(([, value]) => value))
}

export function formatPieceWeight(value) {
	return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })
}

/** Rows left after approval, and the result to show when any LaySheet failed. */
export function applyApprovalResult(rows, { approved = [], failed = [] }) {
	const done = new Set(approved)
	const outcome = bulkOutcome("approve", { done: approved, failed }, APPROVE_ACTION)
	return { rows: rows.filter((row) => !done.has(row.name)), outcome: failed.length ? outcome : null, notice: approved.length ? outcome.notice : "" }
}
