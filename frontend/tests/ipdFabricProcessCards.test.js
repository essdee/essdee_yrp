import assert from "node:assert/strict"
import test from "node:test"
import { availableProcesses, buildSteps, combinationRows, escapeHtml, inputItemLabel, shapeOf, stepsToRows, summaryOf } from "../src/departments/merch/ipd/cloth/fabricProcessCards.js"
import { blankDraft, draftFromStep, draftProblem, draftToStep, transformShape } from "../src/departments/merch/ipd/cloth/fabricProcessDraft.js"

const YARN = "Yarn 25's OE 100%"
const CLOTH = "25's OE Cloth"
const COLOURS = ["Black", "Navy", "Olive", "Peacock Blue", "Maroon melange", "Andhra Melange"]
const DIAS = [["30 Dia", "32 Dia"], ["24 Dia", "26 Dia"]]

const processes = [
	{ name: "p1", sequence: 10, fabric_process: "Knitting", input_item: YARN, output_item: CLOTH, quantity_ratio: 1 },
	{ name: "p2", sequence: 20, fabric_process: "Dyeing", input_item: CLOTH, output_item: CLOTH, quantity_ratio: 1 },
	{ name: "p3", sequence: 30, fabric_process: "Compacting", input_item: CLOTH, output_item: CLOTH, quantity_ratio: 1 },
]
const row = (sequence, mapping_index, attribute, role, from_value, to_value) => ({ sequence, mapping_index, attribute, role, from_value, to_value })
const knitting = DIAS.flatMap(([dia], index) => [
	row(10, index, "Colour", "Consume", "Greige", null), row(10, index, "Colour", "Introduce", null, "Greige"), row(10, index, "Dia", "Introduce", null, dia),
])
const dyeing = COLOURS.flatMap((colour, colourIndex) => DIAS.flatMap(([dia], diaIndex) => [
	row(20, colourIndex * 2 + diaIndex, "Colour", "Change", "Greige", colour), row(20, colourIndex * 2 + diaIndex, "Dia", "Pin", dia, dia),
]))
const compacting = COLOURS.flatMap((colour, colourIndex) => DIAS.flatMap(([from, to], diaIndex) => [
	row(30, colourIndex * 2 + diaIndex, "Dia", "Change", from, to), row(30, colourIndex * 2 + diaIndex, "Colour", "Pin", colour, colour),
]))
const mappings = [...knitting, ...dyeing, ...compacting]
const steps = buildSteps(processes, mappings)
const plain = (html) => html.replace(/<[^>]+>/g, "").replace(/&#39;/g, "'")
const context = { item: CLOTH, conversionInputs: [{ item: YARN, ratio: 100 }], defaultInput: YARN }

test("badges: item conversion when items differ or Consume/Introduce, attribute swap for one changed attribute", () => {
	assert.deepEqual(steps.map((step) => shapeOf(step).label), ["Item conversion", "Attribute swap", "Attribute swap"])
	assert.equal(shapeOf({ input_item: CLOTH, output_item: CLOTH, mappings: [row(0, 0, "Colour", "Change", "a", "b"), row(0, 0, "Dia", "Change", "1", "2")] }).label, "Combination")
	assert.equal(shapeOf({ input_item: CLOTH, output_item: CLOTH, mappings: [] }).label, "Identity")
})

test("knitting summary merges introduced dias and drops the carried colour", () => {
	assert.equal(plain(summaryOf(steps[0])), "Greige → 30 · 24 Dia")
	assert.equal(inputItemLabel(steps[0], CLOTH, context.conversionInputs), `${YARN} 100%`)
})

test("dyeing summary lists colour swaps with held dia, capped at four", () => {
	assert.equal(plain(summaryOf(steps[1])), "Colour: Greige → Black (held Dia 30 · 24 Dia) ; Colour: Greige → Navy (held Dia 30 · 24 Dia) ; Colour: Greige → Olive (held Dia 30 · 24 Dia) ; Colour: Greige → Peacock Blue (held Dia 30 · 24 Dia) +2 more")
})

test("compacting summary lists dia changes with held colours", () => {
	assert.equal(plain(summaryOf(steps[2])), "Dia: 30 Dia → 32 Dia (held Colour Black · Navy · Olive · Peacock Blue · Maroon melange · Andhra Melange) ; Dia: 24 Dia → 26 Dia (held Colour Black · Navy · Olive · Peacock Blue · Maroon melange · Andhra Melange)")
})

test("combination counts and rows are one per mapping group", () => {
	assert.deepEqual(steps.map((step) => combinationRows(step).length), [2, 12, 12])
	assert.equal(plain(combinationRows(steps[0])[1]), "Greige → Greige · 24 Dia")
	assert.equal(plain(combinationRows(steps[2])[0]), "Dia: 30 Dia → 32 Dia (held Colour Black)")
})

test("summary escapes stored values", () => {
	const step = buildSteps([{ sequence: 10, fabric_process: "X", input_item: "A", output_item: "A" }], [row(10, 0, "Colour", "Change", "<b>", "x")])[0]
	assert.ok(summaryOf(step).includes(escapeHtml("<b>")))
})

test("editing a step round-trips its stored rows unchanged", () => {
	const shapes = [
		transformShape({ shape: "conversion", input_attributes: ["Colour"], output_attributes: ["Colour", "Dia"] }),
		transformShape({ shape: "swap", change_attributes: ["Colour"] }),
		transformShape({ shape: "swap", change_attributes: ["Dia"] }),
	]
	const edited = steps.map((step, index) => ({ ...draftToStep(draftFromStep(step, index, shapes[index], context).draft, context), name: step.name }))
	const rows = stepsToRows(edited)
	assert.deepEqual(rows.processes.map((entry) => [entry.name, entry.sequence, entry.input_item, entry.output_item]), processes.map((entry) => [entry.name, entry.sequence, entry.input_item, entry.output_item]))
	const normalise = (list) => list.map((entry) => [entry.sequence, entry.mapping_index, entry.attribute, entry.role, entry.from_value || "", entry.to_value || ""])
	assert.deepEqual(normalise(rows.mappings), normalise(mappings))
})

test("edit refuses steps the editor cannot represent", () => {
	const result = draftFromStep(steps[1], 1, transformShape({ shape: "swap", change_attributes: ["Dia"] }), context)
	assert.match(result.error, /not configured on its Process master \(Colour\)/)
})

test("add & define builds a change step with a held attribute", () => {
	const draft = blankDraft("Washing", 40, transformShape({ shape: "swap", change_attributes: ["Colour"] }), context)
	assert.equal(draftProblem(draft, context), "Fill from and to for every attribute in at least one transition.")
	Object.assign(draft.groups[0], { Colour: { from: "Black", to: "Navy" }, __pin: "30 Dia" })
	draft.pin_attr = "Dia"
	assert.equal(draftProblem(draft, context), "")
	const step = draftToStep(draft, context)
	assert.deepEqual(step.mappings, [
		{ mapping_index: 0, attribute: "Colour", role: "Change", from_value: "Black", to_value: "Navy" },
		{ mapping_index: 0, attribute: "Dia", role: "Pin", from_value: "30 Dia", to_value: "30 Dia" },
	])
	const rows = stepsToRows([...steps, step])
	assert.deepEqual(rows.processes.at(-1), { sequence: 40, fabric_process: "Washing", input_item: CLOTH, output_item: CLOTH, quantity_ratio: 1 })
	assert.deepEqual(availableProcesses(["Compacting", "Dyeing", "Knitting", "Washing"], steps), ["Washing"])
})

test("conversion chips cross-product into introduced combinations", () => {
	const draft = blankDraft("Knitting", 10, transformShape({ shape: "conversion", output_attributes: ["Dia", "Colour"] }), context)
	draft.introduce[0].chips = ["30 Dia", "24 Dia"]
	draft.introduce[1].input = "Greige"
	const step = draftToStep(draft, context)
	assert.equal(step.input_item, YARN)
	assert.equal(step.mappings.length, 4)
	assert.equal(plain(summaryOf(step)), "Introduces Dia: 30 · 24 Dia; Colour: Greige")
})

test("conversion with a recipe needs the yarn ratio to total 100%", () => {
	const draft = blankDraft("Knitting", 10, transformShape({ shape: "conversion" }), context)
	assert.equal(draftProblem(draft, context), "")
	assert.match(draftProblem(draft, { ...context, conversionInputs: [{ item: YARN, ratio: 60 }] }), /totalling exactly 100%/)
})
