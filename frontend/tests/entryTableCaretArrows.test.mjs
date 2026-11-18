import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { registerHooks } from "node:module"
import test from "node:test"

const vueUrl = import.meta.resolve("vue")
registerHooks({ resolve: (specifier, context, next) => specifier === "vue" ? { url: vueUrl, shortCircuit: true } : next(specifier, context) })

const { vEntryTable } = await import("../src/components/common/childGrid/entryTable.js")

function numberInput(value) {
	const control = {
		tagName: "INPUT", type: "number", value, selectionStart: null, selectionEnd: null, validity: { badInput: false },
		classList: { contains: () => false }, getAttribute: () => null, matches: () => true,
		getClientRects: () => [{}], contains: (target) => target === control, focus() { focused = control }, select() {},
		closest: (selector) => selector === "tbody tr" || selector === "tr" ? row : selector === "td, th" ? { cellIndex: cells.indexOf(control) } : null,
	}
	return control
}
let focused = null
const row = { cells: [], contains: (target) => cells.includes(target), querySelectorAll: () => cells }
let cells = []

function mountGrid(values) {
	cells = values.map(numberInput)
	row.cells = cells
	focused = null
	const listeners = {}
	const table = { tagName: "TABLE", tBodies: [{ rows: [row] }], addEventListener: (type, listener) => { listeners[type] = listener }, removeEventListener() {} }
	globalThis.requestAnimationFrame = () => {}
	vEntryTable.mounted(table, { value: { fixed: false } })
	const press = (key, target) => {
		const event = { key, target, currentTarget: table, prevented: false, preventDefault() { this.prevented = true }, stopPropagation() {} }
		listeners.keydown(event)
		return event
	}
	const pointer = (target) => listeners.pointerdown?.({ target })
	return { press, pointer }
}

test("Left and Right move the caret inside a typed number cell instead of jumping cells", () => {
	const { press, pointer } = mountGrid(["1235", "7", "8"])
	pointer(cells[1])
	for (const key of ["ArrowLeft", "ArrowRight"]) {
		const event = press(key, cells[1])
		assert.equal(event.prevented, false, key)
		assert.equal(focused, null, key)
	}
})

test("typing into a cell reached by the keyboard keeps Left and Right inside its text", () => {
	const { press } = mountGrid(["", "2", "3"])
	press("ArrowRight", cells[0])
	assert.equal(focused, cells[1])
	press("5", cells[1])
	cells[1].value = "25"
	focused = null
	assert.equal(press("ArrowLeft", cells[1]).prevented, false)
	assert.equal(focused, null)
})

test("a cell just reached by the keyboard, or an empty one, still moves on with Left and Right", () => {
	const { press } = mountGrid(["", "", "3"])
	press("ArrowRight", cells[0])
	assert.equal(focused, cells[1])
	cells[1].value = "9"
	press("ArrowRight", cells[1])
	assert.equal(focused, cells[2], "untyped cell reached by Right moves on")
	const empty = mountGrid(["1", "", "3"])
	empty.pointer(cells[1])
	empty.press("ArrowLeft", cells[1])
	assert.equal(focused, cells[0], "empty cell moves on")
})

test("Up and Down still move between rows from a typed number cell", () => {
	const { press, pointer } = mountGrid(["1235"])
	pointer(cells[0])
	assert.equal(press("ArrowDown", cells[0]).prevented, true)
})

test("EntryGrid edits leave the cell on Left or Right only from the caret's edge", () => {
	const source = readFileSync(new URL("../src/components/common/EntryGrid.vue", import.meta.url), "utf8")
	assert.match(source, /editing\.value === "replace" && ARROWS\[event\.key\] && !event\.altKey && isCaretAtEdge\(event\.target, event\.key\)/)
})
