import { callMethod, callRead } from "./frappe.js"

const STEPS = "essdee_yrp.time_and_action.steps"

export function getActionLeadTime(action) {
	return callRead("frappe.client.get_value", { doctype: "SD YRP Action", filters: action, fieldname: "lead_time" })
		.then((value) => Number(value?.lead_time) || 1)
}

export function previewUpdateActions(timeAndAction, add, remove) {
	return callMethod(`${STEPS}.preview_update_actions`, { time_and_action: timeAndAction, add: JSON.stringify(add), remove: JSON.stringify(remove) })
}

export function updateActions(timeAndAction, add, remove) {
	return callMethod(`${STEPS}.update_actions`, { time_and_action: timeAndAction, add: JSON.stringify(add), remove: JSON.stringify(remove) })
}
