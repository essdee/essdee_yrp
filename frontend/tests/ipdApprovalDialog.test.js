import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { compile } from "@vue/compiler-dom"
import { parse } from "@vue/compiler-sfc"
import { renderToString } from "@vue/server-renderer"
import * as Vue from "vue"

import {
	SECTION_ORDER, approvalGate, grams, orderedSections, sectionCount, weightBasis, weightColourChips, weightRows,
} from "../src/departments/merch/ipd/approval/ipdApproval.js"

const read = (path) => readFileSync(new URL(`../src/departments/merch/ipd/${path}`, import.meta.url), "utf8")

const SUMMARY_SECTIONS = [
	{ key: "embellishment", label: "Embellishment processes", data: { embellishments: [], other_processes: [], core_processes: [] } },
	{ key: "colours", label: "Main colours", data: { packing: ["Black"], set_combos: [], contrast_panels: [], cloths: [] } },
	{ key: "weight", label: "Piece weight", data: { basis: ["Part"], columns: ["Part"], rows: [], source_rows: 0 } },
	{ key: "panels", label: "Panels", data: [] },
	{ key: "accessories", label: "Accessories", data: [] },
	{ key: "cloth_accessories", label: "Cloth accessory weight", data: [] },
]

function renderTemplate(path, data, stubs = []) {
	const template = parse(read(path)).descriptor.template.content
	const render = new Function("Vue", compile(template, { mode: "function" }).code)(Vue)
	const app = Vue.createSSRApp({ render, data: () => data })
	app.config.warnHandler = () => {}
	const Stub = { props: ["label", "disabled"], setup(props, { slots }) { return () => Vue.h("div", { "data-label": props.label, "data-disabled": String(Boolean(props.disabled)) }, [slots.header?.(), slots.default?.(), slots.footer?.()]) } }
	for (const name of stubs) app.component(name, Stub)
	return renderToString(app)
}

test("sections render in the approved review order", () => {
	assert.deepEqual(SECTION_ORDER, ["colours", "panels", "weight", "cloth_accessories", "accessories", "embellishment"])
	assert.deepEqual(orderedSections(SUMMARY_SECTIONS).map((section) => section.key), SECTION_ORDER)
})

test("approve stays disabled until the warnings are acknowledged", () => {
	const warnings = [{ level: "warning", section: "weight", text: "Maroon weight differs" }]
	assert.deepEqual(approvalGate(warnings, false), { needsAcknowledgement: true, canApprove: false })
	assert.deepEqual(approvalGate(warnings, true), { needsAcknowledgement: true, canApprove: true })
	assert.deepEqual(approvalGate([], false), { needsAcknowledgement: false, canApprove: true })
	assert.equal(approvalGate([], false, true).canApprove, false)
})

test("dialog shows the checkbox only with warnings and gates the Approve button", async () => {
	const base = {
		visible: true, busy: false, loading: false, error: "", hint: "", hasDanger: false, headerMeta: "v1",
		header: { name: "IPD-1", status: "Not Approved" }, stats: [], sections: [], acknowledged: false,
		close() {}, confirm() {},
	}
	const stubs = ["Dialog", "Button", "Checkbox", "Message", "Tag", "IpdApprovalAlerts", "IpdApprovalSection"]
	const blocked = await renderTemplate("approval/IpdApprovalDialog.vue", {
		...base, summary: { warnings: [{ level: "warning", text: "x" }] }, gate: approvalGate([{}], false),
	}, stubs)
	assert.match(blocked, /I have checked the warnings/)
	assert.match(blocked, /data-label="Approve" data-disabled="true"/)
	const open = await renderTemplate("approval/IpdApprovalDialog.vue", {
		...base, summary: { warnings: [] }, gate: approvalGate([], false),
	}, stubs)
	assert.doesNotMatch(open, /I have checked the warnings/)
	assert.match(open, /No warnings in this IPD/)
	assert.match(open, /data-label="Approve" data-disabled="false"/)
})

test("dialog emits confirm only from Approve and only when the gate allows", () => {
	const source = read("approval/IpdApprovalDialog.vue")
	assert.match(source, /<Button label="Approve"[^>]*@click="confirm"/)
	assert.match(source, /<Button label="Cancel"[^>]*@click="close\(false\)"/)
	assert.match(source, /function confirm\(\) \{\n\tif \(summary.value && gate.value.canApprove\) emit\("confirm"\)/)
	assert.equal((source.match(/emit\("confirm"\)/g) || []).length, 1)
})

test("view and editor open the review instead of approving, and approve only on confirm", () => {
	const page = read("IpdPage.vue")
	assert.match(page, /approve: \(\) => \{ approvalVisible.value = true \}/)
	assert.match(page, /<IpdApprovalDialog v-model:visible="approvalVisible"[^>]*@confirm="runCommand\('approve'\)"/)
	assert.equal((page.match(/runCommand\(["']approve["']\)/g) || []).length, 1)
	const editor = read("IpdEditor.vue")
	assert.match(editor, /approve: \(\) => \{ approvalVisible.value = true \}/)
	assert.match(editor, /<IpdApprovalDialog[^>]*@confirm="confirmApprove"/)
	assert.match(editor, /async function confirmApprove\(\) \{\n\tawait approve\(\)/)
	assert.match(read("useIpdEditor.js"), /executeIpdCommand\(name.value, "approve"/)
})

test("piece weight rows show the basis, grams with kilograms and the first value of each group", () => {
	const weight = {
		basis: ["Part", "Colour", "Panel"], columns: ["Part", "Panel", "Colour"], source_rows: 4,
		rows: [
			{ values: { Part: "Top", Panel: "Front" }, colours: ["Black", "Navy"], weight: 0.029 },
			{ values: { Part: "Top", Panel: "Back" }, colours: ["Black"], weight: 0.029 },
		],
	}
	assert.equal(weightBasis(weight), "Part × Colour × Panel")
	assert.equal(sectionCount({ key: "weight", data: weight }), "2 rows from 4")
	assert.equal(grams(0.029), "29 g")
	assert.equal(grams(0), "—")
	assert.deepEqual(weightRows(weight).map((row) => row.shown), [{ Part: "Top", Panel: "Front" }, { Panel: "Back" }])
})

test("piece weight shows All colours when a row covers every IPD colour, else the covered subset", () => {
	const all = ["Black", "Navy", "Maroon"]
	assert.deepEqual(weightColourChips(["Navy", "Black", "Maroon"], all), ["All colours"])
	assert.deepEqual(weightColourChips(["Black", "Navy"], all), ["Black", "Navy"])
	assert.deepEqual(weightColourChips(["Black"], ["Black"]), ["Black"])
	const rows = weightRows({ rows: [{ values: { Panel: "Front" }, colours: all }] }, all)
	assert.deepEqual(rows[0].colourChips, ["All colours"])
})

test("colours show as plain text chips with no swatch anywhere in the popup", () => {
	const sources = ["IpdApprovalDialog.vue", "IpdApprovalSection.vue", "IpdApprovalWeight.vue", "approval.css", "ipdApproval.js"].map((file) => read(`approval/${file}`)).join("\n")
	assert.doesNotMatch(sources, /swatch|colour_code|colourCode|repeating-linear-gradient/i)
	assert.match(read("approval/IpdApprovalWeight.vue"), /<span v-for="colour in row.colourChips" :key="colour" class="ipd-approval__chip">\{\{ colour \}\}<\/span>/)
})
