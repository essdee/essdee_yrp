import { callRead } from "./frappe.js"

/** Every department's capability payload, keyed by source, for the Departments search. */
export function getDepartmentCapabilities() {
	return callRead("essdee_yrp.web_search.get_department_capabilities")
}
