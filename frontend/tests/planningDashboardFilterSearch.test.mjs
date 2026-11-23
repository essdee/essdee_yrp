import test from "node:test"
import assert from "node:assert/strict"

import { enterValues, searchOptions } from "../src/departments/planning/dashboard/filterSearch.js"

const options = [{ value: "MMA Vest", hint: "3 PPOs" }, { value: "Thermal", hint: "9 PPOs" }, { value: "Vest", hint: "3 PPOs" }]

test("search matches value or hint and keeps picks outside the options", () => {
	assert.deepEqual(searchOptions(options, "ther", []).map((option) => option.value), ["Thermal"])
	assert.deepEqual(searchOptions(options, "vest", []).map((option) => option.value), ["Vest", "MMA Vest"])
	assert.deepEqual(searchOptions(options, "", ["Old"]).map((option) => option.value), ["MMA Vest", "Thermal", "Vest", "Old"])
	assert.deepEqual(searchOptions(options, "a, b", []).length, 3)
})

test("Enter adds the first suggestion, an exact match, or every pasted match", () => {
	assert.deepEqual(enterValues(options, "Ther", []), ["Thermal"])
	assert.deepEqual(enterValues(options, "vest", []), ["Vest"])
	assert.deepEqual(enterValues(options, "Thermal; vest", ["MMA Vest"]), ["MMA Vest", "Thermal", "Vest"])
	assert.deepEqual(enterValues(options, "zzz", ["Vest"]), null)
	assert.deepEqual(enterValues(options, "  ", []), null)
})
