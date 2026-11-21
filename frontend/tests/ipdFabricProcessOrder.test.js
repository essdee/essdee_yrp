import assert from "node:assert/strict"
import test from "node:test"
import { canMoveProcess, moveProcess, removeProcess } from "../src/departments/merch/ipd/cloth/clothGrids.js"

const processes = [
	{ name: "p1", sequence: 10, fabric_process: "Knitting", input_item: "Yarn", output_item: "Cloth" },
	{ name: "p2", sequence: 20, fabric_process: "Dyeing", input_item: "Cloth", output_item: "Cloth" },
	{ name: "p3", sequence: 30, fabric_process: "Compacting", input_item: "Cloth", output_item: "Cloth" },
]
const mappings = [
	{ sequence: 20, mapping_index: 0, attribute: "Colour", role: "Change", from_value: "Grey", to_value: "Red" },
	{ sequence: 30, mapping_index: 0, attribute: "Dia", role: "Change", from_value: "30", to_value: "32" },
]

test("moving a process resequences by tens and carries its mappings", () => {
	const next = moveProcess(processes, mappings, 2, -1)
	assert.deepEqual(next.processes.map((row) => [row.fabric_process, row.sequence]), [["Knitting", 10], ["Compacting", 20], ["Dyeing", 30]])
	assert.deepEqual(next.mappings.map((row) => [row.attribute, row.sequence]), [["Dia", 20], ["Colour", 30]])
})

test("blocks moves past the ends and moves that break the item chain", () => {
	assert.equal(canMoveProcess(processes, 0, -1), false)
	assert.equal(canMoveProcess(processes, 2, 1), false)
	assert.equal(canMoveProcess(processes, 1, -1), false)
	assert.equal(canMoveProcess(processes, 1, 1), true)
	assert.equal(moveProcess(processes, mappings, 1, -1).processes, processes)
})

test("moves follow sequence order, not stored row order", () => {
	const next = moveProcess([processes[2], processes[0], processes[1]], [], 1, 1)
	assert.deepEqual(next.processes.map((row) => row.fabric_process), ["Knitting", "Compacting", "Dyeing"])
})

test("removing a process drops its mappings and resequences the rest", () => {
	const next = removeProcess(processes, mappings, "p2")
	assert.deepEqual(next.processes.map((row) => [row.fabric_process, row.sequence]), [["Knitting", 10], ["Compacting", 20]])
	assert.deepEqual(next.mappings.map((row) => [row.attribute, row.sequence]), [["Dia", 20]])
})
