import { callMethod } from "./frappe.js"

const CREATE = "essdee_yrp.time_and_action.create"
const UPDATE = "essdee_yrp.time_and_action.update"
const WEB = "essdee_yrp.time_and_action.web"
const PRODUCTION_ORDER = "essdee_yrp.time_and_action.production_order"

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

export function createTimeAndAction(against, againstId, master, startDate, workStations, plannedSuppliers) {
	return callMethod(`${CREATE}.create_time_and_action`, {
		against,
		against_id: againstId,
		master,
		start_date: startDate,
		work_stations: JSON.stringify(workStations || {}),
		planned_suppliers: JSON.stringify(plannedSuppliers || {}),
	})
}

export function getProductionOrderTimeAndAction(productionOrder) {
	return callMethod(`${PRODUCTION_ORDER}.get_production_order_time_and_action`, { production_order: productionOrder })
}

export function getConvertibleLots(timeAndAction) {
	return callMethod(`${PRODUCTION_ORDER}.get_convertible_lots`, { time_and_action: timeAndAction })
}

export function convertToLotTimeAndAction(timeAndAction, lots) {
	return callMethod(`${PRODUCTION_ORDER}.convert_to_lot_time_and_action`, { time_and_action: timeAndAction, lots: JSON.stringify(lots) })
}

const SPLIT = "essdee_yrp.time_and_action.split"

export function getSplitLots(timeAndAction, txt) {
	return callMethod(`${SPLIT}.get_split_lots`, { time_and_action: timeAndAction, txt: txt || null })
}

export function splitTimeAndAction(timeAndAction, lots) {
	return callMethod(`${SPLIT}.split_time_and_action`, { time_and_action: timeAndAction, lots: JSON.stringify(lots) })
}

const SUPPLIERS = "essdee_yrp.time_and_action.suppliers"

export function getSupplierChips(timeAndAction) {
	return callMethod(`${SUPPLIERS}.get_supplier_chips`, { time_and_action: timeAndAction })
}

export function setPlannedSuppliers(timeAndAction, action, suppliers) {
	return callMethod(`${SUPPLIERS}.set_planned_suppliers`, { time_and_action: timeAndAction, action, suppliers: JSON.stringify(suppliers) })
}

export function revertTimeAndAction(timeAndAction) {
	return callMethod(`${UPDATE}.revert_time_and_action`, { time_and_action: timeAndAction })
}

export function getActionProcessQuantities(timeAndAction, action) {
	return callMethod("essdee_yrp.time_and_action.process_quantities.get_action_process_quantities", { time_and_action: timeAndAction, action })
}
