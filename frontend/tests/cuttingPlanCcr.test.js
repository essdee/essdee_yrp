import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as printUrl from "../src/utils/printUrl.js"
import * as printPreparers from "../src/utils/printPreparers.js"
import { LOT_PLAN_SHORTCUTS, noPlanMessage, planOptions, planRoute, resolvePlanTarget } from "../src/departments/planning/lot/lotPlanShortcuts.js"

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)
const text = node => node.text + node.children.map(text).join("")
const read = path => readFileSync(resolve("frontend/src", path), "utf8")
const tag = type => (props, { slots }) => Vue.h(type, props, slots.default?.())

test("CCR tab sits just before Stock Transfers and follows the route tab both ways", async () => {
	const component = loadComponent(resolve("frontend/src/departments/cutting/CuttingPlanTabs.vue"), {
		"primevue/message": tag("message"), "primevue/skeleton": tag("skeleton"), "primevue/tab": tag("tab"), "primevue/tablist": tag("tablist"),
		"primevue/tabpanel": tag("tab-panel"), "primevue/tabpanels": tag("tab-panels"), "primevue/tabs": tag("tabs"),
		"../../components/common/DocumentLink.vue": () => null, "../../components/documents/DocumentOverview.vue": () => null,
		"./CuttingPlanCpm.vue": () => null, "./CuttingPlanStockTransfers.vue": () => null, "./shared/MaterialRequirementGroups.vue": () => null,
		"./CuttingPlanCcr.vue": props => Vue.h("ccr-panel", props),
	})
	const emitted = []
	const props = Vue.reactive({
		doc: { name: "CP-1" }, tab: "ccr", "onUpdate:tab": tab => emitted.push(tab),
		data: { permissions: { can_read_movement: true, can_read_stock_transfers: true } },
	})
	const root = mountComponent(component, props)
	await tick()
	assert.deepEqual(nodes(root, "tab").map(node => node.props.value), ["details", "summary", "planned", "cpm", "ccr", "stock-transfers"])
	assert.equal(nodes(root, "tabs")[0].props.value, "ccr")
	assert.equal(nodes(root, "ccr-panel").length, 1)
	assert.deepEqual(emitted, [])

	nodes(root, "tabs")[0].props["onUpdate:value"]("details")
	await tick()
	assert.deepEqual(emitted, ["details"])
	assert.equal(nodes(root, "ccr-panel").length, 0)

	props.tab = "details"
	await tick()
	props.tab = "ccr"
	await tick()
	assert.equal(nodes(root, "tabs")[0].props.value, "ccr")
})

test("CCR tab renders marker tables with print totals", async () => {
	const requests = []
	const payload = {
		marker_groups: [{
			panels: "Back, Front", sizes: ["S", "M"],
			rows: [{ colour: "Red", cloth_type: "Body", received_weight: 10, used_weight: 6, balance_weight: 4, sizes: { S: 20, M: 10 }, total_pieces: 30, piece_weight: 0.2, required_weight: 0.21 }],
			totals: { received_weight: 10, used_weight: 6, balance_weight: 4, sizes: { S: 20, M: 10 }, total_pieces: 30, piece_weight: 0.2, required_weight: 0.21 },
		}],
		accessories: [], print_panels: [], recuts: [],
		cloth_groups: [{ cloth_type: "Body", rows: [{ item: "Cotton", cloth_type: "Body", colour: "Red", dia: "20", weight: 10, used_weight: 6, balance_weight: 4 }] }],
		completed: [{ pack_attr: "Colour", set_item_attr: null, primary_values: ["S", "M"], rows: [{ label: "Red", values: { S: 20, M: 0 } }] }],
		excess: [{ pack_attr: "Colour", set_item_attr: null, primary_values: ["S"], rows: [{ label: "Red", values: { S: { Front: 2, Back: 0 } } }] }],
	}
	const component = loadComponent(resolve("frontend/src/departments/cutting/CuttingPlanCcr.vue"), {
		"primevue/message": tag("message"), "primevue/skeleton": tag("skeleton"),
		"../../api/cuttingWorkspaces.js": { getCuttingPlanCcr: async name => { requests.push(name); return payload } },
	})
	const root = mountComponent(component, { cuttingPlan: "CP-1" })
	await tick()
	assert.deepEqual(requests, ["CP-1"])
	const [marker, cloth, completed, excess] = nodes(root, "table")
	assert.deepEqual(nodes(marker, "th").map(text), ["S.No.", "Colour", "Cloth Type", "Received Weight", "Used Weight", "Balance Weight", "S", "M", "Total", "Piece Weight", "Reqd Weight"])
	assert.deepEqual(nodes(marker, "tr").slice(1).map(row => nodes(row, "td").map(text)), [
		["1", "Red", "Body", "10.000", "6.000", "4.000", "20", "10", "30", "0.2000", "0.2100"],
		["", "Total", "", "10.000", "6.000", "4.000", "20", "10", "30", "0.2000", "0.2100"],
	])
	assert.ok(text(root).includes("Cloth Summary · Body"))
	assert.deepEqual(nodes(cloth, "tr").at(-1).children.map(text), ["Total", "", "", "", "", "10.000", "6.000", "4.000"])
	assert.deepEqual(nodes(completed, "tr").slice(1).map(row => nodes(row, "td").map(text)), [["1", "Red", "20", "--", "20"], ["Total", "", "20", "0", "20"]])
	assert.deepEqual(nodes(excess, "td").map(text), ["1", "Red", "Front 2"])
})

test("print dialog preselects the requested format and letter head when they are available", async () => {
	const Select = Vue.defineComponent({ props: { modelValue: String, options: Array }, setup: props => () => Vue.h("select", props) })
	const dialog = loadComponent(resolve("frontend/src/components/documents/DocumentPrintDialog.vue"), {
		"primevue/button": props => Vue.h("button", props), "primevue/dialog": (props, { slots }) => Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]),
		"primevue/select": Select, "primevue/inputnumber": () => null,
		"../../api/frappe.js": { getPrintOptions: async () => ({ formats: ["Essdee Cutting Plan", "Essdee Cutting Plan CCR"], default_format: "Essdee Cutting Plan", letter_heads: ["Blank", "Essdee Knitting Mills Private Limited"], default_letter_head: "Blank" }) },
		"../../api/qzPrinter.js": {}, "../../utils/printUrl.js": printUrl, "../../utils/printPreparers.js": printPreparers,
	})
	const selected = async props => {
		const root = mountComponent(dialog, { visible: true, doctype: "SD YRP Cutting Plan", name: "CP-1", ...props })
		await tick()
		return nodes(root, "select").map(node => node.props.modelValue)
	}
	assert.deepEqual(await selected({ defaultFormat: "Essdee Cutting Plan CCR", defaultLetterHead: "Essdee Knitting Mills Private Limited" }), ["Essdee Cutting Plan CCR", "Essdee Knitting Mills Private Limited"])
	assert.deepEqual(await selected({ defaultFormat: "Missing", defaultLetterHead: "Missing" }), ["Essdee Cutting Plan", "Blank"])
	assert.deepEqual(await selected({}), ["Essdee Cutting Plan", "Blank"])
})

test("Cutting Plan shows Print CCR beside Print with the CCR format and letter head", () => {
	const source = read("departments/CuttingPlan.vue")
	assert.match(source, /const CCR_PRINT_FORMAT = "Essdee Cutting Plan CCR"/)
	assert.match(source, /const CCR_LETTER_HEAD = "Essdee Knitting Mills Private Limited"/)
	assert.match(source, /<DocumentPrintButton\s+v-if="canPrintCcr"[\s\S]*?label="Print CCR"\s+:default-format="CCR_PRINT_FORMAT"\s+:default-letter-head="CCR_LETTER_HEAD"/)
	assert.match(source, /:tab="String\(route\.query\.tab \|\| ''\)"\s+@update:tab="showTab"/)
})

test("Lot plan shortcuts open one plan, ask for several and report none", () => {
	const { ccr, ocr } = LOT_PLAN_SHORTCUTS
	assert.deepEqual(resolvePlanTarget([]), { kind: "none" })
	assert.deepEqual(resolvePlanTarget([{ name: "CP-1" }]), { kind: "open", name: "CP-1" })
	assert.deepEqual(resolvePlanTarget([{ name: "CP-1" }, { name: "CP-2" }]), { kind: "choose" })
	assert.deepEqual(planRoute(ccr, "CP-1"), { name: "planning-cutting-plan", params: { cuttingPlanId: "CP-1" }, query: { tab: "ccr" } })
	assert.deepEqual(planRoute(ocr, "FP-1"), { name: "planning-finishing-plan", params: { finishingPlanId: "FP-1" }, query: { tab: "ocr" } })
	assert.deepEqual(planOptions(ccr, [
		{ name: "CP-1", cp_status: "Completed", docstatus: 1, cutting_start_date: "2026-11-05" },
		{ name: "CP-2", cp_status: "", docstatus: 0, creation: "2026-11-07 10:00:00" },
	]), [{ name: "CP-1", status: "Completed", date: "05-11-2026" }, { name: "CP-2", status: "Draft", date: "07-11-2026" }])
	assert.equal(noPlanMessage(ocr, "LOT-1"), "No Finishing Plan found for Lot LOT-1.")
})

test("only the Planning Lot view offers CCR and OCR beside Print", () => {
	const page = read("departments/planning/lot/LotPage.vue")
	assert.match(page, /<template #print-actions="\{ acting: busy \}">\s*<Button v-for="\(shortcut, key\) in LOT_PLAN_SHORTCUTS"/)
	assert.match(page, /const planLoaders = \{ ccr: getLotCuttingPlans, ocr: getLotFinishingPlans \}/)
	assert.match(read("departments/fabric-store/FabricDocumentWorkspace.vue"), /<slot name="print-actions"[^>]*\/>\s*<CustomPrintButtons/)
	for (const path of ["merch/lot/MerchLotPage.vue", "purchase/lot/LotPage.vue", "merch-purchase/lot/MerchLotPage.vue"]) {
		assert.doesNotMatch(read(`departments/${path}`), /LOT_PLAN_SHORTCUTS|print-actions/, path)
	}
	const api = read("api/planning.js")
	assert.match(api, /filters: \[\["lot", "=", lot\], \["docstatus", "!=", 2\]\]/)
	assert.match(read("departments/finishing/FinishingPlanTabs.vue"), /\{ value: "ocr", label: "OCR", source: "ocr" \}/)
})
