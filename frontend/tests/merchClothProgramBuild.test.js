import assert from "node:assert/strict"
import test from "node:test"
import { buildBlockMessage, buildSelection, clothSelection, contextExcessPercentage } from "../src/departments/merch/lot/clothProgram.js"

const ready = {
	cloth_item: "Cotton Rib",
	item_yarns: [{ yarn_item: "Yarn 30s", ratio: 100 }],
	cloth_per_kg_yarn: 1,
	knitting_process: "Knitting",
	required_colours: [],
	dyed_yarn_colours: [],
	profile: {},
}

test("a cloth without a yarn recipe explains why Build is blocked", () => {
	const message = buildBlockMessage([ready, { ...ready, cloth_item: "Sareena Fabric", item_yarns: [] }], 0)
	assert.match(message, /^Fix Sareena Fabric before building: Configure unique Yarn Items/)
})

test("a negative excess blocks Build with its own message", () => {
	assert.equal(buildBlockMessage([ready], -1), "Cloth Excess Percentage cannot be negative.")
})

test("complete cloths allow Build", () => {
	assert.equal(buildBlockMessage([ready], 5), "")
})

test("the stored excess from context prefills Build Cloth Program", () => {
	assert.equal(contextExcessPercentage({ excess_percentage: 7.5 }, 0), 7.5)
	assert.equal(contextExcessPercentage({ excess_percentage: 0 }, 5), 0)
	assert.equal(contextExcessPercentage({}, 5), 5)
	assert.equal(contextExcessPercentage(null), 0)
})

test("Build payload offers only dyed or non-dyed yarn per colour", () => {
	const cloth = {
		...ready,
		required_colours: ["Red", "Anthra Melange"],
		required_routes: [
			{ colour: "Red", dia: "30" },
			{ colour: "Anthra Melange", dia: "30" },
		],
		dyed_yarn_colours: ["Red"],
		same_finished_colours: ["Anthra Melange"],
	}
	const payload = buildSelection(clothSelection(cloth, { knitting_output_colour: "Greige" }))
	assert.equal("same_finished_colours" in payload, false)
	assert.deepEqual(
		payload.fabric_routes.map((row) => [row.finished_colour, row.knitting_output_colour, row.use_dyed_yarn]),
		[
			["Red", "Red", 1],
			["Anthra Melange", "Greige", 0],
		],
	)
})
