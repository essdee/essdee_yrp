import assert from "node:assert/strict"
import test from "node:test"

import { weightSpan } from "../src/departments/merch/ipd/approval/ipdApproval.js"
import { groupPanels, panelsByPart, ungroupPanel } from "../src/departments/merch/ipd/sections/garmentGrids.js"

const cell = (weight) => ({ dia: "26 Dia", weight })
const single = (panel, part, weight = null) => ({
	group_id: panel,
	panel_value: panel,
	panel_values: [panel],
	part,
	packing_values: ["Navy"],
	rows: [{ primary_value: "S", values: { Navy: weight == null ? { dia: null, weight: null } : cell(weight) } }],
})
const setMatrix = () => ({
	panel_values: ["Front", "Back", "Leg"],
	panels: [single("Front", "Top", 0.1), single("Back", "Top", 0.05), single("Leg", "Bottom", 0.08)],
})

test("panels are listed under their set item part", () => {
	const sections = panelsByPart(setMatrix().panels)
	assert.deepEqual(sections.map((section) => [section.part, section.panels.map((panel) => panel.panel_value)]), [
		["Top", ["Front", "Back"]],
		["Bottom", ["Leg"]],
	])
})

test("non set item panels stay in one unlabelled section", () => {
	const sections = panelsByPart([single("Front"), single("Back")])
	assert.deepEqual(sections.map((section) => [section.part, section.panels.length]), [[null, 2]])
})

test("grouping panels of different parts is refused", () => {
	assert.throws(() => groupPanels(setMatrix(), ["Front", "Leg"]), /different parts/)
})

test("grouping and ungrouping within a part keeps the part", () => {
	const grouped = groupPanels(setMatrix(), ["Front", "Back"])
	const group = grouped.matrix.panels.find((panel) => panel.group_id === grouped.groupId)
	assert.equal(group.part, "Top")
	assert.equal(group.rows[0].values.Navy.weight, 0.15)
	const split = ungroupPanel(grouped.matrix, grouped.groupId)
	assert.deepEqual(split.matrix.panels.map((panel) => panel.part), ["Top", "Top", "Bottom"])
})

test("set item piece weight is shown per part", () => {
	const span = { parts: [{ part: "Top", min: 0.12, max: 0.14 }, { part: "Bottom", min: 0.08, max: 0.08 }] }
	assert.equal(weightSpan(span), "Top 0.12–0.14 kg · Bottom 0.08 kg")
	assert.equal(weightSpan({ parts: [{ part: "Top" }] }), "Top —")
})
