import { callMethod, callRead } from "./frappe.js"

const METHOD = "essdee_yrp.web_workspace_layout"

/** Existing Layout Builder layouts and the built-in names they cannot take. */
export function getBuilderData() {
	return callRead(`${METHOD}.get_builder_data`)
}

/** `payload` is `{ title, sections, original_name }` from layoutBuilder.getPayload. */
export function saveLayout(payload) {
	return callMethod(`${METHOD}.save_layout`, payload)
}

export function deleteLayout(name) {
	return callMethod(`${METHOD}.delete_layout`, { name })
}

/** `payload` is `{ layout, sections }` for a built-in department layout. */
export function saveDepartmentOverride(payload) {
	return callMethod(`${METHOD}.save_department_override`, payload)
}

export function resetDepartmentOverride(layout) {
	return callMethod(`${METHOD}.reset_department_override`, { layout })
}
