import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as shortcuts from "../src/departments/planning/lot/lotPlanShortcuts.js"

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)
const read = path => readFileSync(resolve("frontend/src", path), "utf8")

function mountButtons(props, plans = {}) {
	const pushed = []
	const toasts = []
	const component = loadComponent(resolve("frontend/src/departments/planning/lot/LotPlanShortcutButtons.vue"), {
		"primevue/button": props => Vue.h("button", props),
		"primevue/usetoast": { useToast: () => ({ add: toast => toasts.push(toast) }) },
		"vue-router": { useRouter: () => ({ push: route => pushed.push(route) }) },
		"../../../api/planning.js": { getLotCuttingPlans: async () => plans.ccr || [], getLotFinishingPlans: async () => plans.ocr || [] },
		"./LotPlanPickerDialog.vue": props => Vue.h("picker", props),
		"./lotPlanShortcuts.js": shortcuts,
	})
	return { root: mountComponent(component, props), pushed, toasts }
}

test("CCR and OCR show only for plan doctypes the server says the user can read", () => {
	const keys = access => shortcuts.visiblePlanShortcuts(access).map(shortcut => shortcut.key)
	assert.deepEqual(keys({ ccr: true, ocr: true }), ["ccr", "ocr"])
	assert.deepEqual(keys({ ccr: true, ocr: false }), ["ccr"])
	assert.deepEqual(keys({ ccr: false, ocr: true }), ["ocr"])
	assert.deepEqual(keys({}), [])
	assert.deepEqual(keys(undefined), [])

	const labels = access => nodes(mountButtons({ lot: "LOT-1", access }).root, "button").map(node => node.props.label)
	assert.deepEqual(labels({ ccr: true, ocr: true }), ["CCR", "OCR"])
	assert.deepEqual(labels({ ccr: false, ocr: true }), ["OCR"])
	assert.deepEqual(labels({ ccr: true, ocr: false }), ["CCR"])
	assert.deepEqual(labels({ ccr: false, ocr: false }), [])
})

test("shortcut buttons open one plan, pick among several and warn on none, without bubbling", async () => {
	const twoPlans = [{ name: "CP-1", docstatus: 1 }, { name: "CP-2", docstatus: 0 }]
	const { root, pushed, toasts } = mountButtons({ lot: "LOT-1", access: { ccr: true, ocr: true }, compact: true }, { ccr: twoPlans, ocr: [{ name: "FP-1" }] })
	const [wrapper] = nodes(root, "span")
	assert.equal(typeof wrapper.props.onClick, "function")
	let stopped = false
	wrapper.props.onClick({ stopPropagation: () => { stopped = true } })
	assert.ok(stopped, "clicks inside the shortcuts never reach the row")

	const [ccr, ocr] = nodes(root, "button")
	assert.equal(ccr.props.size, "small")
	ocr.props.onClick()
	await tick()
	assert.deepEqual(pushed, [{ name: "planning-finishing-plan", params: { finishingPlanId: "FP-1" }, query: { tab: "ocr" } }])

	ccr.props.onClick()
	await tick()
	const [picker] = nodes(root, "picker")
	assert.equal(picker.props.visible, true)
	assert.deepEqual(picker.props.options.map(option => option.name), ["CP-1", "CP-2"])
	picker.props.onPick("CP-2")
	await tick()
	assert.deepEqual(pushed.at(-1), { name: "planning-cutting-plan", params: { cuttingPlanId: "CP-2" }, query: { tab: "ccr" } })

	const empty = mountButtons({ lot: "LOT-2", access: { ccr: true } })
	nodes(empty.root, "button")[0].props.onClick()
	await tick()
	assert.deepEqual(empty.toasts.map(toast => toast.summary), ["No Cutting Plan found for Lot LOT-2."])
	assert.deepEqual(empty.pushed, [])
})

test("Planning Lot page and PPO Tracking lot rows share the shortcut buttons with server access", () => {
	assert.match(read("departments/planning/lot/LotPage.vue"), /<LotPlanShortcutButtons :lot="lotId" :access="workspace\.plan_access" :disabled="Boolean\(busy\)" \/>/)
	assert.match(read("departments/planning/dashboard/TrackingLotRow.vue"), /<LotPlanShortcutButtons :lot="row\.lot" :access="planAccess" compact \/>/)
	assert.match(read("departments/planning/dashboard/TrackingLotsTable.vue"), /<TrackingLotRow [^>]*:plan-access="planAccess"/)
	assert.match(read("departments/planning/dashboard/PpoTrackingView.vue"), /:plan-access="data\.plan_access"/)
	const api = read("api/planning.js")
	assert.match(api, /callRead\(`\$\{LOT_METHOD\}\.get_lot_cutting_plans`, \{ lot \}\)/)
	assert.match(api, /callRead\(`\$\{LOT_METHOD\}\.get_lot_finishing_plans`, \{ lot \}\)/)
})
