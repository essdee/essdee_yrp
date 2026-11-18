import { callRead } from "./frappe.js"

const CAPABILITIES_METHOD = "essdee_yrp.cutting.web_capabilities.get_capabilities"

export function getCuttingCapabilities() {
	return callRead(CAPABILITIES_METHOD)
}

export function getCuttingPlanCcr(cuttingPlan) {
	return callRead("essdee_yrp.cutting.ccr.get_cutting_plan_ccr", { cutting_plan: cuttingPlan })
}
