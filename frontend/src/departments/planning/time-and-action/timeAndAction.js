import { formatDisplayDate } from "../../../utils/dateFormat.js"

/** Desk T&A Update rule: only In Progress T&As, and only the user's departments unless Administrator. */
export function canEditRow(data, row) {
	return data?.status === "In Progress" && Boolean(data.is_administrator || data.departments?.includes(row.department))
}

export function isLate(row) {
	return Boolean(row.actual_date && row.actual_date > row.rescheduled_date)
}

export function actualTone(row) {
	if (!row.actual_date) return ""
	return isLate(row) ? "late" : "on-time"
}

export function leadTimeLabel(row) {
	return `${row.lead_time} ${Number(row.lead_time) === 1 ? "Day" : "Days"} · ${row.department || ""}`
}

export function dependencyTitle(row) {
	const names = Object.keys(row.depends_on || {})
	return names.length ? `Depends on: ${names.join(", ")}` : "No dependencies"
}

/** Expected-delivery impact line, worded like the Desk T&A Update page; empty when delivery does not move. */
export function deliveryMessage(data) {
	const days = data?.delivery_days_moved
	if (!days) return ""
	const moves = `Expected delivery date moves from ${formatDisplayDate(data.delivery_date_before, "")} to ${formatDisplayDate(data.delivery_date_after, "")}`
	const count = Math.abs(days) === 1 ? "1 working day" : `${Math.abs(days)} working days`
	return days > 0 ? `${moves} — delayed by ${count} more` : `${moves} — pulled in by ${count}`
}

export function reviseMessage(data) {
	const last = data?.rows?.[data.rows.length - 1]
	if (!last) return ""
	return `Dispatch date changes from ${formatDisplayDate(last.date, "")} to ${formatDisplayDate(last.rescheduled_date, "")}. Revise the dates?`
}

/** Rows for the Rescheduled Details dialog: every frozen baseline per action. */
export function revisionRows(data) {
	const rows = data?.rows || []
	const count = Math.max(0, ...rows.map((row) => (data.revisions?.[row.action] || []).length))
	return Array.from({ length: count }, (_, index) => ({
		label: `Rescheduled Date ${index + 1}`,
		values: rows.map((row) => data.revisions?.[row.action]?.[index] || null),
	}))
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
	{ key: "actual_delay", label: "Planned Delay", number: true },
	{ key: "date_diff", label: "Rescheduled Delay", number: true },
	{ key: "reason", label: "Reason" },
	{ key: "performance", label: "Performance", number: true, suffix: "%" },
]

export function reportCell(row, column) {
	const value = row[column.key]
	if (column.date) return formatDisplayDate(value, "")
	if (value === null || value === undefined) return ""
	return `${value}${column.suffix || ""}`
}
