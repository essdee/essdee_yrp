import { formatDisplayDate } from "../../../utils/dateFormat.js"

export function todayIso(now = new Date()) {
	return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`
}

export function dayCount(count) {
	return `${count} ${Math.abs(count) === 1 ? "day" : "days"}`
}

function workingDayCount(count) {
	return `${count} working ${Math.abs(count) === 1 ? "day" : "days"}`
}

/** Desk T&A Update rule: only In Progress T&As, and only the user's departments unless Administrator. */
export function canEditRow(data, row) {
	return data?.status === "In Progress" && Boolean(data.is_administrator || data.departments?.includes(row.department))
}

export function isLate(row) {
	return Boolean(row.actual_date && row.actual_date > row.rescheduled_date)
}

/** Dependencies of an undated row that have no actual date yet, from the server's `depends_on`. */
export function getBlockedBy(row) {
	if (row.actual_date) return []
	return Object.entries(row.depends_on || {}).filter(([, actual]) => !actual).map(([name]) => name)
}

/** Client chip for one action: error (server rejected the date), done, blocked, overdue or due. */
export function getRowStatus(row, { hasError = false, today = todayIso() } = {}) {
	if (hasError) return "error"
	if (row.actual_date) return "done"
	if (getBlockedBy(row).length) return "blocked"
	return today > row.rescheduled_date ? "overdue" : "due"
}

export const STATUS_LABELS = { done: "Done", due: "Due", overdue: "Overdue", blocked: "Blocked", error: "Check date" }

export function countStatuses(statuses) {
	const counts = { done: 0, due: 0, overdue: 0, blocked: 0, error: 0 }
	for (const status of statuses) counts[status] += 1
	return counts
}

/** Delay cell from the server's Rescheduled Delay (`date_diff`) and Planned Delay (`actual_delay`); negative = late. */
export function getDelay(row) {
	if (!row.actual_date) return null
	const diff = Number(row.date_diff) || 0
	if (diff < 0) return { text: `${dayCount(-diff)} late`, tone: "late", planned: row.actual_delay }
	return { text: diff === 0 ? "On time" : `${dayCount(diff)} early`, tone: "ok", planned: row.actual_delay }
}

/** T&A running delay (`delay`): last action's Planned Date vs its expected or actual date, working days, negative = late. */
export function getRunningDelay(delay) {
	const days = Number(delay) || 0
	if (!days) return { tone: "none", text: "On schedule" }
	return { tone: days < 0 ? "late" : "ok", text: `${workingDayCount(Math.abs(days))} ${days < 0 ? "late" : "early"}` }
}

/** Save bar impact line from `preview_actual_dates`; days are working days, later = positive. */
export function getImpact(data, hasChanges) {
	const days = Number(data?.delivery_days_moved) || 0
	if (!hasChanges || !days) {
		return { tone: "none", text: hasChanges ? "No change to expected delivery" : "Enter actual dates to see the effect on delivery" }
	}
	const from = formatDisplayDate(data.delivery_date_before, "")
	const to = formatDisplayDate(data.delivery_date_after, "")
	if (days > 0) return { tone: "late", from, to, text: `+${workingDayCount(days)}` }
	return { tone: "early", from, to, text: `${workingDayCount(-days)} earlier` }
}

export function getPendingSummary({ changes = 0, errors = 0, missingReasons = 0 }) {
	return [
		changes && `${changes} unsaved ${changes === 1 ? "change" : "changes"}`,
		errors && `${errors} ${errors === 1 ? "date" : "dates"} to fix`,
		missingReasons && `${missingReasons} ${missingReasons === 1 ? "reason" : "reasons"} missing`,
	].filter(Boolean)
}

export function getSaveMessage(data) {
	const days = Number(data?.delivery_days_moved) || 0
	const before = formatDisplayDate(data?.delivery_date_before, "")
	if (!days) return `Expected delivery stays ${before}.`
	const after = formatDisplayDate(data.delivery_date_after, "")
	return `Expected delivery moves ${before} to ${after}, ${days > 0 ? "+" : ""}${workingDayCount(days)}.`
}

export function getReviseMessage(data) {
	const last = data?.rows?.[data.rows.length - 1]
	if (!last) return ""
	return `Every action's Freeze Date is replaced by its current Rescheduled Date, and the old dates are logged with your reason. Revisions are limited per T&A. Dispatch date changes from ${formatDisplayDate(last.date, "")} to ${formatDisplayDate(last.rescheduled_date, "")}.`
}

export const REVISE_HELP = "Revise Dates makes the current Rescheduled Dates the new baseline: every action's Freeze Date is replaced by its Rescheduled Date, and the old dates are logged with your reason. Only the revised-date approver role can do it, a limited number of times per T&A."

/** Desk label of a T&A's `against` DocType. */
export function againstLabel(doctype) {
	return doctype === "SD YRP Lot" ? "Lot" : doctype === "YRP Production Order" ? "Production Order" : doctype || ""
}

/** Next Action chip of a list row: Overdue once its Rescheduled Date has passed, else Due on that date. */
export function getNextActionChip(row, today = todayIso()) {
	if (!row.next_action) return null
	if (today > row.next_action_date) return { tone: "overdue", label: "Overdue" }
	return { tone: "due", label: `Due ${formatDisplayDate(row.next_action_date, "")}` }
}

/** The 12 columns of the Lot "Time and Action" report view, Desk labels and Desk value mapping. */
export const REPORT_COLUMNS = [
	{ key: "action", label: "Action" },
	{ key: "department", label: "Department" },
	{ key: "lead_time", label: "Lead Time", number: true },
	{ key: "work_station", label: "Work Station" },
	{ key: "planned_start_date", label: "Planned Date", date: true },
	{ key: "date", label: "Freeze Date", date: true },
	{ key: "rescheduled_date", label: "Rescheduled Date", date: true },
	{ key: "actual_date", label: "Actual Date", date: true },
	{ key: "actual_delay", label: "Planned Delay", number: true, signed: true },
	{ key: "date_diff", label: "Rescheduled Delay", number: true, signed: true },
	{ key: "reason", label: "Reason" },
	{ key: "performance", label: "Performance", number: true, suffix: "%" },
]

export function reportCell(row, column) {
	const value = row[column.key]
	if (column.date) return formatDisplayDate(value, "")
	if (value === null || value === undefined) return ""
	return `${value}${column.suffix || ""}`
}

export function reportTone(row, column) {
	if (!column.signed) return ""
	const value = Number(row[column.key]) || 0
	return value < 0 ? "neg" : value > 0 ? "pos" : ""
}
