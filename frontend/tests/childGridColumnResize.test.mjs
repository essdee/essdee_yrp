import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { ref } from "vue"

import { useColumnResize } from "../src/components/common/childGrid/useColumnResize.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

function fakeHandle() {
	const listeners = {}
	const classes = new Set()
	return {
		listeners,
		classes,
		ownerDocument: { body: { classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name) } } },
		setPointerCapture() {},
		addEventListener(type, listener) { listeners[type] = listener },
		removeEventListener(type) { delete listeners[type] },
	}
}

function setup({ enabled = true, save = async () => {} } = {}) {
	const frames = []
	globalThis.requestAnimationFrame = (callback) => frames.push(callback)
	globalThis.cancelAnimationFrame = () => { frames.length = 0 }
	const flush = () => frames.splice(0).forEach((callback) => callback())
	const columns = ref([{ key: "item", percent: 40 }, { key: "qty", percent: 20 }, { key: "notes", percent: 40 }, { key: "actions", configurable: false, width: 52 }])
	const toasts = []
	const resize = useColumnResize({
		columns,
		widths: ref([400, 200, 400, 52]),
		minimums: ref([60, 60, 120, 52]),
		save,
		enabled: ref(enabled),
		toast: { add: (message) => toasts.push(message) },
	})
	return { resize, toasts, flush }
}

function pointer(handle, clientX) {
	return { button: 0, clientX, pointerId: 1, currentTarget: handle, preventDefault() {}, stopPropagation() {} }
}

test("every visible column but the last sized one gets a handle, and none without a saved-settings key", () => {
	const { resize } = setup()
	assert.deepEqual([0, 1, 2, 3].map(resize.isResizable), [true, true, false, false])
	assert.deepEqual([0, 1, 2].map(setup({ enabled: false }).resize.isResizable), [false, false, false])
})

test("dragging a border resizes live against the last column and saves percentages once on release", async () => {
	const saves = []
	const { resize, flush } = setup({ save: async (draft) => saves.push(draft) })
	const handle = fakeHandle()
	resize.start(pointer(handle, 100), 0)
	assert.ok(handle.classes.has("is-column-resizing"))
	handle.listeners.pointermove({ clientX: 150 })
	flush()
	assert.deepEqual(resize.liveWidths.value, [450, 200, 350, 52])
	handle.listeners.pointermove({ clientX: 900 })
	flush()
	assert.deepEqual(resize.liveWidths.value, [680, 200, 120, 52])
	assert.equal(saves.length, 0)
	handle.listeners.pointerup()
	await Promise.resolve()
	assert.equal(handle.classes.size, 0)
	assert.deepEqual(saves, [[
		{ key: "item", visible: true, locked: false, percent: 680 },
		{ key: "qty", visible: true, locked: false, percent: 200 },
		{ key: "notes", visible: true, locked: false, percent: 120 },
	]])
	await new Promise((resolve) => setTimeout(resolve))
	assert.equal(resize.liveWidths.value, null)
})

test("a click on a border without movement saves nothing; a failed save reports and restores the layout", async () => {
	const saves = []
	const quiet = setup({ save: async (draft) => saves.push(draft) })
	const handle = fakeHandle()
	quiet.resize.start(pointer(handle, 100), 1)
	handle.listeners.pointerup()
	assert.equal(saves.length, 0)
	assert.equal(quiet.resize.liveWidths.value, null)

	const failing = setup({ save: async () => { throw new Error("Not permitted") } })
	const other = fakeHandle()
	failing.resize.start(pointer(other, 100), 1)
	other.listeners.pointermove({ clientX: 80 })
	other.listeners.pointerup()
	await new Promise((resolve) => setTimeout(resolve))
	assert.equal(failing.toasts[0].detail, "Not permitted")
	assert.equal(failing.resize.liveWidths.value, null)
})

test("both child grids render the resize handle on header borders and read live widths first", () => {
	for (const path of ["components/common/EntryGrid.vue", "components/common/childGrid/ChildGridTable.vue"]) {
		const source = read(path)
		assert.match(source, /class="report-col-resize child-grid-resize"[^>]*@pointerdown="\w+\.start\(\$event, \w+\)"[^>]*@dblclick\.prevent="\w+\.fit\(\$event, \w+\)"/, path)
		assert.match(source, /const columnWidths = computed\(\(\) => \w+\.liveWidths\.value \|\| layoutColumnWidths\.value\)/, path)
	}
	assert.match(read("styles/reportTables.css"), /@media \(max-width: 620px\) \{\s*\.child-grid-resize \{ display: none; \}/)
})

test("the settings dialog only chooses and orders columns", () => {
	const source = read("components/common/childGrid/ChildGridSettings.vue")
	assert.doesNotMatch(source, /InputNumber|Distribute evenly|Total:/)
	assert.match(source, /Reset to Default/)
})

test("data-matrix entry grids get column settings keyed by their parent field, with every column kept visible", () => {
	const expected = {
		"departments/merch/lot/MerchColourwiseEditor.vue": ['settings-doctype="SD YRP Lot"', 'settings-child-doctype="lot_order_details_json"'],
		"departments/merch-purchase/lot/MerchColourwiseEditor.vue": ['settings-doctype="SD YRP Lot"', 'settings-child-doctype="lot_order_details_json"'],
		"departments/merch-pd/lot/MerchColourwiseEditor.vue": ['settings-doctype="SD YRP Lot"', 'settings-child-doctype="lot_order_details_json"'],
		"departments/accounts/lot/MerchColourwiseEditor.vue": ['settings-doctype="SD YRP Lot"', 'settings-child-doctype="lot_order_details_json"'],
		"departments/merch/ipd/sections/IpdPanelWiseGrids.vue": ['settings-child-doctype="panel_wise_consumption_matrix_json"', 'settings-child-doctype="panel_wise_cloth_mapping_json"'],
		"departments/merch/ipd/sections/IpdSetItemSection.vue": ['settings-child-doctype="set_item_detail"'],
		"departments/merch/ipd/sections/IpdPackingSection.vue": ['settings-child-doctype="packing_attribute_details"', 'settings-child-doctype="packing_size_details"', 'settings-child-doctype="packing_assortment_json"'],
		"departments/merch/process-cost/ProcessCostGrid.vue": ['settings-doctype="YRP Process Cost"', 'settings-child-doctype="process_cost_values"'],
	}
	for (const [path, needles] of Object.entries(expected)) {
		const source = read(path)
		for (const needle of needles) assert.ok(source.includes(needle), `${path}: ${needle}`)
		assert.equal((source.match(/<EntryGrid/g) || []).length, (source.match(/lock-columns/g) || []).length, path)
	}
	assert.match(read("components/common/EntryGrid.vue"), /\.\.\.\(props\.lockColumns \? \{ reqd: 1 \} : \{\}\)/)
})
