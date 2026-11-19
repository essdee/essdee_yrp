import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { PLANNING_ROUTES } from "../planningRoutes.js"

export const LOT_PLAN_SHORTCUTS = {
	ccr: {
		label: "CCR",
		documentLabel: "Cutting Plan",
		routeName: PLANNING_ROUTES.cuttingPlan,
		param: "cuttingPlanId",
		tab: "ccr",
		statusField: "cp_status",
		dateField: "cutting_start_date",
	},
	ocr: {
		label: "OCR",
		documentLabel: "Finishing Plan",
		routeName: PLANNING_ROUTES.finishingPlan,
		param: "finishingPlanId",
		tab: "ocr",
		statusField: "fp_status",
		dateField: "finishing_start_date",
	},
}

/** One plan opens directly, several need a choice, none is reported. */
export function resolvePlanTarget(plans = []) {
	if (!plans.length) return { kind: "none" }
	if (plans.length === 1) return { kind: "open", name: plans[0].name }
	return { kind: "choose" }
}

export function planRoute(shortcut, name) {
	return { name: shortcut.routeName, params: { [shortcut.param]: name }, query: { tab: shortcut.tab } }
}

export function planOptions(shortcut, plans = []) {
	return plans.map((plan) => ({
		name: plan.name,
		status: plan[shortcut.statusField] || (plan.docstatus === 0 ? "Draft" : ""),
		date: formatDisplayDate(plan[shortcut.dateField] || plan.creation),
	}))
}

export function noPlanMessage(shortcut, lot) {
	return `No ${shortcut.documentLabel} found for Lot ${lot}.`
}

/** Shortcuts the server allows: `access` is `plan_access` ({ ccr, ocr }) from the lot or tracking payload. */
export function visiblePlanShortcuts(access = {}) {
	return Object.entries(LOT_PLAN_SHORTCUTS).filter(([key]) => access[key]).map(([key, shortcut]) => ({ key, ...shortcut }))
}
