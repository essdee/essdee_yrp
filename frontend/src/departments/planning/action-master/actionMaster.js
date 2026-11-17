import { PLANNING_ROUTES } from "../planningRoutes.js"

const SHARED_HEADER_FIELDS = ["description", "min_qty", "max_qty", "fabric", "product_type", "emblishment"]
const SHARED_LIST_COLUMNS = ["description", "quantity", "fabric", "product_type", "emblishment", "lead_time"]

export const ACTION_MASTER_DOCTYPE = "SD YRP Action Master"
export const ACTION_MASTER_TEMPLATE_DOCTYPE = "SD YRP Action Master Template"
export const TEMPLATE_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_action_master.sd_yrp_action_master.get_template_details"

/** Action Master and its Template share one page; these say what differs. */
export const ACTION_MASTER_KINDS = {
	master: {
		doctype: ACTION_MASTER_DOCTYPE,
		label: "Action Master",
		pluralLabel: "Action Masters",
		headerFields: [...SHARED_HEADER_FIELDS, "action_master_template", "disable"],
		listColumns: [...SHARED_LIST_COLUMNS, "disable"],
		routes: { list: PLANNING_ROUTES.actionMasters, new: PLANNING_ROUTES.actionMasterNew, view: PLANNING_ROUTES.actionMaster },
		listPath: "/planning/action-masters",
	},
	template: {
		doctype: ACTION_MASTER_TEMPLATE_DOCTYPE,
		label: "Action Master Template",
		pluralLabel: "Action Master Templates",
		headerFields: SHARED_HEADER_FIELDS,
		listColumns: SHARED_LIST_COLUMNS,
		routes: { list: PLANNING_ROUTES.actionMasterTemplates, new: PLANNING_ROUTES.actionMasterTemplateNew, view: PLANNING_ROUTES.actionMasterTemplate },
		listPath: "/planning/action-master-templates",
	},
}

let nextKey = 0

export function newStep(values = {}) {
	return { key: `step-${++nextKey}`, action: "", lead_time: null, department: "", dependent_action: [], ...values }
}

/** Steps in Details order, each carrying the actions it depends on. */
export function stepsFromDoc(doc = {}) {
	const dependencies = {}
	for (const row of doc.action_master_dependent_details || []) (dependencies[row.action] ||= []).push(row.dependent_action)
	return (doc.details || []).map((row) => newStep({
		action: row.action, lead_time: row.lead_time, department: row.department || "", dependent_action: dependencies[row.action] || [],
	}))
}

/** The child tables Desk stores for these steps (target is always 0). */
export function stepTables(steps) {
	const filled = steps.filter((step) => step.action)
	return {
		details: filled.map(({ action, lead_time, department }) => ({ action, lead_time, department: department || null, target: 0 })),
		action_master_dependent_details: filled.flatMap(({ action, dependent_action }) => dependent_action.map((dependency) => ({ action, dependent_action: dependency }))),
	}
}

/** Actions of the steps above `index`, the only valid dependencies of that step. */
export function dependencyOptions(steps, index) {
	return [...new Set(steps.slice(0, index).map((step) => step.action).filter(Boolean))]
}

/** Drops dependencies that no longer point at an earlier step. */
export function pruneDependencies(steps) {
	return steps.map((step, index) => {
		const allowed = dependencyOptions(steps, index)
		const kept = step.dependent_action.filter((action) => allowed.includes(action))
		return kept.length === step.dependent_action.length ? step : { ...step, dependent_action: kept }
	})
}

export function moveStep(steps, from, to) {
	if (to < 0 || to >= steps.length) return steps
	const moved = [...steps]
	moved.splice(to, 0, moved.splice(from, 1)[0])
	return pruneDependencies(moved)
}

export function removeStep(steps, index) {
	return pruneDependencies(steps.filter((_, position) => position !== index))
}

export function headerValues(fieldnames, doc = {}) {
	return Object.fromEntries(fieldnames.map((fieldname) => [fieldname, doc[fieldname] ?? null]))
}

export function actionMasterPayload(header, steps, amendedFrom = "") {
	return { ...header, ...stepTables(steps), ...(amendedFrom ? { amended_from: amendedFrom } : {}) }
}
