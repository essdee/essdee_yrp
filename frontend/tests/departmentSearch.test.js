import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { getDepartmentEntries } from "../src/departments/search/departmentCards.js"
import * as departmentCards from "../src/departments/search/departmentCards.js"
import { dedupeEntries, getResultRank, searchResults } from "../src/departments/search/departmentSearch.js"
import * as departmentSearch from "../src/departments/search/departmentSearch.js"
import { getLockedDepartment } from "../src/router/departmentLock.js"

const read = { can_read: true }
const ADMIN = { user: { name: "Administrator" } }
const PAYLOAD = {
	cutting: { "cutting-plans": read, "bulk-lay-sheets": read, "lay-sheet-planner": read, reports: read },
	cutting_reports: { "daily-production": true },
	fabric_store: { sections: { goods_received_notes: read, work_orders: read } },
	sewing: { sections: { plans: read, work_orders: read } },
	quality: { sections: { lots: read, cutting_plans: read } },
	merch: { sections: { lots: read, item_production_details: read, cutting_plans: read, process_costs: read, suppliers: read, work_orders: read }, reports: {} },
	purchase: { sections: { lots: read } },
	merch_purchase: { sections: { lots: read, suppliers: read, goods_received_notes: read } },
	planning: { sections: { lots: read, cutting_plans: read, item_production_details: read, work_orders: read } },
}
const describe = (result) => `${result.label} @ ${typeof result.to === "string" ? result.to : result.to.path}`
const results = async (payload = PAYLOAD, options = { boot: ADMIN, lock: null }) => dedupeEntries(await getDepartmentEntries(payload, options))

test("a card offered by several departments shows once, from its home department", async () => {
	const all = await results()
	const lots = all.filter((result) => result.id === "SD YRP Lot")
	assert.deepEqual(lots.map(describe), ["Lot @ /planning/lots"])
	assert.equal(lots[0].department, "Planning")
	assert.deepEqual(searchResults(all, "cutting plan").slice(0, 1).map(describe), ["Cutting Plans @ /cutting/plans"])
	assert.deepEqual(searchResults(all, "ipd").map(describe), ["Item Production Detail @ /merch/item-production-details"])
	assert.deepEqual(searchResults(all, "supplier").slice(0, 1).map(describe), ["Supplier @ /merch/suppliers"])
	assert.equal(searchResults(all, "process cost")[0].department, "Merch")
})

test("without the home department the card falls back to a department of its own before a combined one", async () => {
	const { planning, ...withoutPlanning } = PAYLOAD
	const lots = (await results(withoutPlanning)).filter((result) => result.id === "SD YRP Lot")
	assert.deepEqual(lots.map(describe), ["Lot @ /merch/lots"])
})

test("department-scoped pages stay one per department; the same route offered twice shows once", async () => {
	const all = await results()
	const workOrders = searchResults(all, "work orders").filter((result) => result.kind === "card" && result.label.startsWith("Work Order"))
	assert.deepEqual(workOrders.map((result) => result.department), ["Fabric Store", "Accessory Store", "Sewing", "Merch", "Planning"])
	const grns = all.filter((result) => describe(result) === "Goods Received Notes @ /purchase/goods-received-notes")
	assert.equal(grns.length, 1)
})

test("only cards the user may read and the UI layout allows are searchable", async () => {
	const boot = { user: { name: "someone@example.com", can_read: ["SD YRP Cutting Plan"] } }
	const limited = await results(PAYLOAD, { boot, lock: null })
	assert.equal(limited.some((result) => result.id === "SD YRP Lot"), false)
	assert.equal(limited.some((result) => result.id === "SD YRP Cutting Plan"), true)

	const lock = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "planning" }, config: { experience_props: { workspaces: ["lots"] } } } })
	const locked = await results(PAYLOAD, { boot: ADMIN, lock })
	assert.deepEqual(locked.map(describe), ["Lot @ /planning/lots"])
})

test("reports are searchable only with the department's Reports card", async () => {
	const all = await results()
	const daily = searchResults(all, "daily prod")
	assert.deepEqual(daily.map((result) => [result.kind, result.department, result.to.path, result.to.query.report]), [["report", "Cutting", "/cutting/reports", "daily-production"]])
	const hidden = await results({ ...PAYLOAD, cutting: { ...PAYLOAD.cutting, reports: { can_read: false } } })
	assert.equal(searchResults(hidden, "daily prod").length, 0)
})

const lotCut = { can_read: true, can_report: true }
const REPORT_PAYLOAD = {
	sewing: { sections: { reports: read }, reports: { lot_cut_quantity: lotCut, inhouse_quantity: lotCut } },
	finishing: { sections: { reports: { can_read: true, reports: { lot_cut_quantity: read } } } },
	quality: { sections: { reports: read }, reports: { lot_cut_quantity: read } },
	merch: { sections: { reports: read }, reports: { lot_cut_quantity: read, work_in_progress: read, planning_work_in_progress: read } },
	merch_purchase: { sections: { reports: read }, reports: { lot_cut_quantity: read } },
	planning: { sections: { reports: { can_read: true, groups: { sewing: true, finishing: true, production: true }, production: { work_in_progress: read } } } },
}

test("a report offered by several departments shows once, from its home department", async () => {
	const all = await results(REPORT_PAYLOAD)
	const lotCuts = searchResults(all, "lot cut").filter((result) => result.kind === "report")
	assert.deepEqual(lotCuts.map((result) => [result.label, result.department, result.to.path, result.to.query.report]), [["Lot Cut Quantity", "Planning", "/planning/reports", "sewing-lot-cut-quantity"]])
	assert.match(lotCuts[0].description, /^In Sewing, Finishing, Quality, Merch, Merch & Purchase, Planning$/)
	const { planning, ...withoutPlanning } = REPORT_PAYLOAD
	const fallback = searchResults(await results(withoutPlanning), "lot cut").filter((result) => result.kind === "report")
	assert.deepEqual(fallback.map((result) => result.department), ["Sewing"])
})

test("different reports with the same label stay apart; Planning aliases join their twin", async () => {
	const wip = searchResults(await results(REPORT_PAYLOAD), "work in progress").filter((result) => result.kind === "report")
	assert.deepEqual(wip.map((result) => [result.id, result.department]), [["report:work-in-progress", "Merch"], ["report:planning-work-in-progress", "Planning"]])
})

test("matching is case-insensitive word prefix over label, description, synonyms and department", () => {
	const result = { label: "Bulk LaySheets", description: "Manage multi-lot lay sheets", department: "Cutting", text: "Bulk LaySheets Manage multi-lot lay sheets Cutting laysheet bundle" }
	assert.equal(getResultRank("BULK", result), 0)
	assert.equal(getResultRank("lays", result), 2)
	assert.equal(getResultRank("cutting laysheet", result), 3)
	assert.equal(getResultRank("bundle", result), 3)
	assert.equal(getResultRank("aysheet", result), -1)
	assert.equal(getResultRank("", result), -1)
	assert.equal(getResultRank("ipd", { label: "Item Production Detail", text: "" }), 1)
})

test("results rank label matches first and cards before reports", () => {
	const all = [
		{ id: "a", kind: "report", label: "Lot Cut Quantity", text: "" },
		{ id: "b", kind: "card", label: "Production Order", text: "lot" },
		{ id: "c", kind: "card", label: "Lot", text: "" },
	]
	assert.deepEqual(searchResults(all, "lot").map((result) => result.id), ["c", "a", "b"])
})

const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }

test("the search box focuses on load, moves with arrows, opens with Enter and clears with Escape", async (t) => {
	const listeners = {}
	const focused = []
	globalThis.window = { addEventListener: (name, handler) => { listeners[name] = handler }, removeEventListener() {} }
	globalThis.document = { getElementById: (id) => ({ focus: () => focused.push(id) }) }
	t.after(() => { delete globalThis.window; delete globalThis.document })
	const pushed = []
	const InputText = (props) => Vue.h("input", props)
	const RouterLink = (props, { slots }) => Vue.h("a", props, slots.default?.())
	const component = loadComponent(resolve(rootPath, "frontend/src/departments/search/DepartmentSearch.vue"), {
		"primevue/inputtext": InputText,
		"vue-router": { RouterLink, useRouter: () => ({ push: (to) => pushed.push(to) }) },
		"../../api/departmentSearch.js": { getDepartmentCapabilities: async () => PAYLOAD },
		"./departmentCards.js": { getDepartmentEntries: (all) => departmentCards.getDepartmentEntries(all, { boot: ADMIN, lock: null }) },
		"./departmentSearch.js": departmentSearch,
	})
	const root = mountComponent(component, {})
	await tick()
	const input = findNodes(root, (node) => node.type === "input")[0]
	assert.equal(focused.length, 1)
	assert.ok(listeners.keydown)

	input.props["onUpdate:modelValue"]("lot")
	await tick()
	const links = () => findNodes(root, (node) => node.type === "a")
	assert.ok(links().length > 1)
	const key = (name) => input.props.onKeydown({ key: name, preventDefault() {} })
	key("ArrowDown")
	key("Enter")
	assert.deepEqual(pushed, [links()[1].props.to])
	key("Escape")
	await tick()
	assert.equal(links().length, 0)
})

test("the Departments home page puts the search beside the heading without the intro text", () => {
	const source = readFileSync(resolve(rootPath, "frontend/src/components/AdministratorPage.vue"), "utf8")
	const header = source.match(/<header class="administrator-page__header">[\s\S]*?<\/header>/)[0]
	assert.match(header, /<h1>Good work starts here\.<\/h1>[\s\S]*<DepartmentSearch class="administrator-page__search" \/>/)
	assert.doesNotMatch(source, /Choose a department workspace|administrator-page__description/)
	const css = readFileSync(resolve(rootPath, "frontend/src/styles/main.css"), "utf8")
	assert.match(css, /\.administrator-page__header \{[^}]*justify-content: space-between/)
	assert.match(css, /@media \(max-width: 640px\) \{\s*\.administrator-page__search \{\s*flex-basis: 100%/)
	const component = readFileSync(resolve(rootPath, "frontend/src/departments/search/DepartmentSearch.vue"), "utf8")
	const dropdown = component.match(/\.department-search__results \{[^}]*\}/)[0]
	for (const rule of ["position: absolute", "right: 0", "z-index: 30", "overflow-y: auto", "min-width: 100%"]) assert.ok(dropdown.includes(rule), rule)
	assert.match(component, /@media \(max-width: 640px\) \{\s*\.department-search__results \{\s*left: 0;\s*width: 100%/)
})
