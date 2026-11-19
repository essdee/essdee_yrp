import { workspaceSearchRank } from "../../components/common/workspaceSearch.js"
import { getListDoctype } from "../../router/listPermission.js"

/** Segments whose pages are scoped to their department, so the same DocType there is a different card. */
const DEPARTMENT_SCOPED_SEGMENTS = new Set(["work-orders", "delivery-challans", "goods-received-notes", "purchase-orders", "stock-transfers", "item-conversions", "item-prices", "reports", "bulk-close"])

/** Department that owns a card offered by several departments. */
export const HOME_DEPARTMENTS = {
	"SD YRP Lot": "planning",
	"SD YRP Cutting Plan": "cutting",
	"SD YRP Cutting Order": "cutting",
	"SD YRP Cutting Laysheet Planner": "cutting",
	"SD YRP Sewing Plan": "sewing",
	"SD YRP Finishing Plan": "finishing",
	"rework-details": "finishing",
	dispatches: "finishing",
	"YRP Item Production Detail": "merch",
	"YRP Process Cost": "merch",
	Supplier: "merch",
	"YRP Production Order": "sales",
	"YRP Bill Tracking": "accounts",
	"YRP Purchase Invoice": "accounts",
	"YRP Debit": "accounts",
	"SD YRP Product": "pd",
	"SD YRP Product Release": "pd",
	"SD YRP Lotwise Item Profit": "pd",
	"SD YRP Box Sticker Print": "cut-panel-store",
	"YRP Excel Sticker Print": "cut-panel-store",
}

/** Department that owns a report offered by several departments, keyed by its base report value. */
export const REPORT_HOME_DEPARTMENTS = {
	...Object.fromEntries(["daily-production", "daily-cut-sheet", "multi-ccr", "cutting-detail"].map((value) => [value, "cutting"])),
	...Object.fromEntries(["status-summary", "dpr", "scr", "monthly-summary", "item-summary", "finishing-inward-updates"].map((value) => [value, "sewing"])),
	...Object.fromEntries(["packing-dpr", "dispatch-report", "ironing-dpr", "finishing-plan-report", "rejection-details", "rework-completion", "finishing-dispatch"].map((value) => [value, "finishing"])),
	...Object.fromEntries(["lot-cut-quantity", "inhouse-quantity", "inward-quantity", "planning-work-in-progress", "work-order", "size-wise-stock"].map((value) => [value, "planning"])),
	...Object.fromEntries(["grn-report", "grn-summary", "dc-report", "purchase-order-log", "lot-purchase-summary", "purchase-order-itemwise", "lot-consumption-report"].map((value) => [value, "purchase"])),
	"stock-balance": "fabric-store",
	"ppo-report": "sales",
	"purchase-audit-report": "accounts",
	"quality-inspection-rft": "quality",
	attendance: "hr",
}

/** Planning production reports whose value differs from the same report elsewhere. */
const PLANNING_REPORT_ALIASES = { "work-in-progress": "planning-work-in-progress", "finishing-plan": "finishing-plan-report" }

/** Base value of a report: Planning prefixes the reports it borrows with their source group. */
export function getReportValue(entry) {
	const value = String(entry.item.value || "")
	if (entry.department.key !== "planning") return value
	return PLANNING_REPORT_ALIASES[value] || value.replace(/^(cutting|sewing|finishing)-/, "")
}

const SYNONYMS = {
	"SD YRP Lot": ["order"],
	"SD YRP Cutting Bulk Lay Sheets": ["lay sheet", "laysheet", "bundle"],
	"SD YRP Cutting Laysheet Planner": ["lay sheet", "laysheet", "marker"],
	"YRP Item Production Detail": ["ipd", "bom"],
	"YRP Production Order": ["ppo"],
	"YRP Process Cost": ["costing", "rate"],
	Supplier: ["vendor", "party"],
	"YRP Bill Tracking": ["vendor bill"],
	"SD YRP Essdee Quality Inspection": ["qc"],
	"time-and-action-update": ["t&a", "tna", "dates"],
}

const pathOf = (to) => String((typeof to === "string" ? to : to?.path) || "").toLowerCase()
const words = (text) => String(text || "").toLowerCase().split(/[^a-z0-9&]+/).filter(Boolean)

/** Same identity means the same card or report: a report's base value, a card's list DocType, else its route segment; department-scoped pages keep their own route. */
export function getEntryIdentity(entry) {
	if (entry.kind === "report") return `report:${getReportValue(entry)}`
	const path = pathOf(entry.item.to)
	const segment = path.split("/")[2] || path
	if (DEPARTMENT_SCOPED_SEGMENTS.has(segment)) return path
	return getListDoctype(path) || segment
}

/** Home department first, then a department of its own before a combined one, each preferring a card that opens its own route. */
function canonicalScore(entry, identity) {
	const home = entry.kind === "report" ? REPORT_HOME_DEPARTMENTS[identity.slice("report:".length)] : HOME_DEPARTMENTS[identity]
	if (home === entry.department.key) return 0
	const opensOwnRoute = pathOf(entry.item.to).startsWith(`${entry.department.path}/`)
	return (entry.department.combines ? 3 : 1) + (opensOwnRoute ? 0 : 1)
}

function toResult(group, identity) {
	const best = group.reduce((current, entry) => (canonicalScore(entry, identity) < canonicalScore(current, identity) ? entry : current))
	const departments = [...new Set(group.map((entry) => entry.department.label))]
	return {
		id: identity,
		kind: best.kind,
		label: best.item.label,
		description: best.kind === "report" ? `In ${departments.join(", ")}` : best.item.description || best.item.group || "",
		icon: best.item.icon || (best.kind === "report" ? "pi pi-table" : "pi pi-th-large"),
		to: best.item.to,
		department: best.department.label,
		text: [...group.map((entry) => `${entry.item.label} ${entry.item.description || ""} ${entry.item.group || ""}`), ...departments, ...(SYNONYMS[identity] || [])].join(" "),
	}
}

/** One result per card identity, in first-seen order, each opening its canonical department's card. */
export function dedupeEntries(entries) {
	const groups = new Map()
	for (const entry of entries) {
		const identity = getEntryIdentity(entry)
		groups.set(identity, [...(groups.get(identity) || []), entry])
	}
	return [...groups].map(([identity, group]) => toResult(group, identity))
}

const isWordPrefixMatch = (queryWords, text) => {
	const textWords = words(text)
	return queryWords.every((queryWord) => textWords.some((word) => word.startsWith(queryWord)))
}

/** 0 label prefix, 1 initials or alias, 2 label word prefixes, 3 description, synonym or department word prefixes, -1 no match. */
export function getResultRank(query, result) {
	const queryWords = words(query)
	if (!queryWords.length) return -1
	const labelRank = workspaceSearchRank(query, { label: result.label })
	if (labelRank === 0 || labelRank === 1) return labelRank
	if (isWordPrefixMatch(queryWords, result.label)) return 2
	return isWordPrefixMatch(queryWords, result.text) ? 3 : -1
}

/** Results matching `query`, best rank first, cards before reports, then in department order. */
export function searchResults(results, query, limit = 30) {
	return results
		.map((result, index) => ({ result, index, rank: getResultRank(query, result) }))
		.filter(({ rank }) => rank >= 0)
		.sort((left, right) => left.rank - right.rank || (left.result.kind === "report") - (right.result.kind === "report") || left.index - right.index)
		.slice(0, limit)
		.map(({ result }) => result)
}
