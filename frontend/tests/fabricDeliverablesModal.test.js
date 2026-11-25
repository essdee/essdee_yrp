import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { compile } from "@vue/compiler-dom"
import { parse } from "@vue/compiler-sfc"
import { renderToString } from "@vue/server-renderer"
import * as Vue from "vue"
import { collectManualKnittingContract, createFabricEntries } from "../src/composables/useFabricDeliverableContext.js"

import { buildFabricPayload, canCalculateFabric, fabricColourError, fabricContractError, fabricContractLists, fabricEntryError, fabricEntryLabel, fabricPlanningHint, fabricWarnings, fabricYarnTotals, hydrateFabricRows } from "../src/departments/fabric-store/fabricCalculate.js"
import { fabricClothTotal } from "../src/departments/fabric-store/workOrderTotals.js"

const source = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderActionPanel.vue", import.meta.url), "utf8")
const template = parse(source).descriptor.template.content
const render = new Function("Vue", compile(template, { mode: "function" }).code)(Vue)
const SlotStub = { setup(_, { slots }) { return () => Vue.h("div", [slots.default?.(), slots.footer?.()]) } }

async function renderPanel(row, sourceProcess = {}, hydrated = null) {
	const Root = {
		render,
		data: () => ({
			workOrder: {}, closeConfirmVisible: false, confirmClose() {}, busy: false, canSubmit: true, submitLabel: "Apply", visible: true, title: "Calculate Fabric Deliverables", largePanel: true,
			mode: "calculate_fabric", loading: false, acting: "", error: "", draft: {},
			fabricContext: { source_process: sourceProcess, warnings: [], source_process_options: [] },
			fabricRows: hydrated ? [hydrated] : hydrateFabricRows({ rows: [row] }), isCloseMode: false, canApply: true, discardVisible: false,
		}),
		computed: {
			fabricQuantityWarnings() { return fabricWarnings(this.fabricRows) },
		},
		methods: {
			fabricColourError, fabricContractError, fabricContractLists, fabricEntryError, fabricEntryLabel, fabricPlanningHint, fabricYarnTotals, fabricClothTotal,
			discardAction() {}, submit() {}, requestVisibility() {}, refreshFabricSource() {}, apply() {}, discardAndClose() {},
			attributeText: (attrs) => Object.values(attrs || {}).join(" · "),
			number: (value) => String(value || 0), sourcePreview: () => "",
		},
	}
	const app = Vue.createSSRApp(Root)
	app.config.warnHandler = () => {}
	for (const name of ["Dialog", "Button", "Select", "InputNumber", "LinkField", "Message", "DocumentErrorDialog"]) app.component(name, SlotStub)
	return renderToString(app)
}

test("current fabric panel edits physical knitting inputs and outputs with exact route keys", async () => {
	const row = {
		fabric_row: "FABRIC-1", kind: "knitting", cloth_item: "Cloth", manual_io: true,
		reference_routed: true, entries: [],
		qty_rows: [{ key: "opaque-route:1", output_item: "Cloth", out_attrs: { Dia: "26", Colour: "Navy" }, prefill: 7, knitting_inputs: [{ key: "opaque-yarn:1", item: "Yarn", attrs: { Colour: "Navy" }, qty_per_output: 1, prefill: 7 }] }],
	}
	const [hydrated] = hydrateFabricRows({ rows: [row] })
	hydrated.manualEntry.manualDeliverables[0].qty = 8
	const html = await renderPanel(row, {}, hydrated)
	assert.match(html, /Yarn Deliverables/)
	assert.match(html, /Fabric Receivables/)
	assert.match(html, /Cloth total · 7 Kg/)
	const contract = collectManualKnittingContract(hydrated, hydrated.manualEntry)
	assert.equal(contract.routes[0].qr.key, "opaque-route:1")
	assert.deepEqual(contract.routes[0].manualInputs, [{ key: "opaque-yarn:1", qty: 8 }])
})

test("manual knitting shows one Greige receivable per Dia and saves per finished-colour routes", () => {
	const colours = ["Black", "Navy", "Red", "Green", "White"]
	const dias = ["24 Dia", "26 Dia"]
	const row = {
		fabric_row: "FABRIC-1", kind: "knitting", cloth_item: "Cloth", manual_io: true, reference_routed: true, has_colour: true,
		qty_rows: dias.flatMap((dia) => colours.map((colour) => ({
			key: `${colour}-${dia}`, output_item: "Cloth", output_uom: "Kg", out_attrs: { Dia: dia }, knit_colour: "Greige", label: `${colour} · ${dia}`,
			reference_item_variant: `Cloth-${colour}-${dia}`, prefill: 73, balance: 73, program: 73,
			knitting_inputs: [{ key: "input:0", item: "Yarn", attrs: {}, uom: "Kg", qty_per_output: 1, prefill: 73 }],
		}))),
	}
	const [hydrated] = hydrateFabricRows({ rows: [row] })
	const [deliverables, receivables] = fabricContractLists(hydrated)
	assert.deepEqual(receivables.items.map((item) => [item.attrs.Dia, item.attrs.Colour, item.qty]), [["24 Dia", "Greige", 365], ["26 Dia", "Greige", 365]])
	assert.deepEqual(deliverables.items.map((item) => [item.item, item.qty]), [["Yarn", 730]])
	receivables.items[0].qty = 100
	deliverables.items[0].qty = 465
	assert.equal(fabricContractError(hydrated), "")
	assert.equal(canCalculateFabric([hydrated]), true)
	const [payload] = buildFabricPayload({}, [hydrated]).rows
	assert.equal(payload.entries.length, 10)
	const total = (filter, pick) => Math.round(payload.entries.filter(filter).reduce((sum, line) => sum + pick(line), 0) * 1000) / 1000
	assert.equal(total((line) => line.key.endsWith("24 Dia"), (line) => line.qty), 100)
	assert.equal(total((line) => line.key.endsWith("26 Dia"), (line) => line.qty), 365)
	assert.equal(total(() => true, (line) => line.inputs[0].qty), 465)
	assert.ok(payload.entries.every((line) => line.colour === "Greige" && line.inputs[0].key === "input:0"))
	receivables.items.forEach((item) => { item.qty = 0 })
	assert.match(fabricContractError(hydrated), /Enter a fabric receivable quantity before sending Yarn/)
})

test("unavailable predecessor stock neither nags nor blocks Calculate", async () => {
	const html = await renderPanel({ fabric_row: "FABRIC-1", entries: [] }, { unavailable: true, label: "Knitting" })
	assert.doesNotMatch(html, /No predecessor stock available|Submit an unallocated/)
})

test("legacy actual-Dia source rows send the received Item to Calculate", () => {
	const row = {
		fabric_row: "FABRIC-1", kind: "dyeing", cloth_item: "Cloth",
		qty_rows: [{
			key: "M:0|Cloth-26-Greige", matrix_key: "M:0", out_attrs: { Dia: "26 Dia", Colour: "Red" },
			label: "26 Dia (actual, for 24 Dia): Greige → Red", source_process: "Knitting", source_available: 30,
			source_item_variant: "Cloth-26-Greige", prefill: 0,
		}],
	}
	const [hydrated] = hydrateFabricRows({ rows: [row] })
	hydrated.entries[0].qty = 25
	const [payload] = buildFabricPayload({}, [hydrated]).rows
	assert.deepEqual(payload.entries, [{ key: "M:0|Cloth-26-Greige", matrix_key: "M:0", out_attrs: { Dia: "26 Dia", Colour: "Red" }, qty: 25, source_item_variant: "Cloth-26-Greige" }])
})
