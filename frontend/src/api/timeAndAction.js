import { callMethod } from "./frappe.js"

const CREATE = "essdee_yrp.time_and_action.create"
const UPDATE = "essdee_yrp.time_and_action.update"
const WEB = "essdee_yrp.time_and_action.web"

export function getOpenTimeAndActions(filters) {
	return callMethod(`${WEB}.get_open_time_and_actions`, { lot: filters.lot || null, item: filters.item || null })
}

export function getLotTimeAndAction(lot) {
	return callMethod(`${WEB}.get_lot_time_and_action`, { lot })
}

export function getUpdateData(timeAndAction) {
	return callMethod(`${UPDATE}.get_update_data`, { time_and_action: timeAndAction })
}

export function previewActualDates(timeAndAction, changes, modified) {
	return callMethod(`${UPDATE}.preview_actual_dates`, { time_and_action: timeAndAction, changes: JSON.stringify(changes), modified })
}

export function updateActualDates(timeAndAction, changes, modified) {
	return callMethod(`${UPDATE}.update_actual_dates`, { time_and_action: timeAndAction, changes: JSON.stringify(changes), modified })
}

export function completeTimeAndAction(timeAndAction) {
	return callMethod(`${UPDATE}.complete_time_and_action`, { time_and_action: timeAndAction })
}

export function reviseDates(timeAndAction, reason) {
	return callMethod(`${UPDATE}.revise_dates`, { time_and_action: timeAndAction, reason })
}

export function getSchedulePreview(master, startDate) {
	return callMethod(`${CREATE}.get_schedule_preview`, { master, start_date: startDate })
}

export function createTimeAndAction(lot, master, startDate, workStations) {
	return callMethod(`${CREATE}.create_time_and_action`, {
		against: "SD YRP Lot", against_id: lot, master, start_date: startDate, work_stations: JSON.stringify(workStations || {}),
	})
}
