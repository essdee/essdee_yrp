import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { getAccountMenuItems } from "../src/components/navigation/accountMenu.js"
import {
	addCard,
	addSection,
	createDepartmentDraft,
	createDraft,
	getCatalogueGroups,
	getDraftProblems,
	getPayload,
	moveCard,
	moveCardBy,
	removeCard,
	removeSection,
} from "../src/departments/workspace/layoutBuilder.js"
import { getBuilderRedirect, LAYOUT_BUILDER_PATH } from "../src/departments/workspace/builderAccess.js"
import { WORKSPACE_HOME_PATH } from "../src/router/departmentLock.js"
import { NO_PERMISSION_PATH } from "../src/router/listPermission.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const ADMIN = { user: { name: "Administrator" } }
const MANAGER = { user: { name: "manager@example.com", roles: ["System Manager"] } }
const CLERK = { user: { name: "clerk@example.com", roles: ["Purchase User"] } }
const cards = (draft) => draft.sections.map((section) => section.cards)

test("a draft opens an existing layout or starts with one empty section", () => {
	const fresh = createDraft()
	assert.equal(fresh.originalName, "")
	assert.deepEqual(fresh.sections.map((section) => [section.label, section.cards]), [["Main", []]])

	const existing = createDraft({ name: "Floor Desk", sections: [{ label: "Orders", cards: ["merch:lots"] }] })
	assert.equal(existing.title, "Floor Desk")
	assert.equal(existing.originalName, "Floor Desk")
	assert.deepEqual(cards(existing), [["merch:lots"]])
})

test("sections can be added, renamed and removed", () => {
	const draft = createDraft()
	addSection(draft)
	draft.sections[1].label = "Buying"
	assert.deepEqual(draft.sections.map((section) => section.label), ["Main", "Buying"])
	removeSection(draft, 0)
	assert.deepEqual(draft.sections.map((section) => section.label), ["Buying"])
})

test("a card sits in one place: adding it again moves it", () => {
	const draft = createDraft({ name: "Desk", sections: [{ label: "A", cards: ["merch:lots"] }, { label: "B", cards: [] }] })
	addCard(draft, 0, "planning:lots")
	addCard(draft, 1, "merch:lots", 0)
	assert.deepEqual(cards(draft), [["planning:lots"], ["merch:lots"]])
	addCard(draft, 0, "purchase:lots", 0)
	assert.deepEqual(cards(draft), [["purchase:lots", "planning:lots"], ["merch:lots"]])
})

test("dragging a card reorders it within and across sections", () => {
	const draft = createDraft({ name: "Desk", sections: [{ label: "A", cards: ["a:1", "a:2", "a:3"] }, { label: "B", cards: ["b:1"] }] })
	moveCard(draft, { section: 0, index: 0 }, { section: 0, index: 3 })
	assert.deepEqual(cards(draft), [["a:2", "a:3", "a:1"], ["b:1"]])
	moveCard(draft, { section: 0, index: 1 }, { section: 1, index: 0 })
	assert.deepEqual(cards(draft), [["a:2", "a:1"], ["a:3", "b:1"]])
})

test("up and down buttons move a card one step, crossing into the next section at the edges", () => {
	const draft = createDraft({ name: "Desk", sections: [{ label: "A", cards: ["a:1", "a:2"] }, { label: "B", cards: ["b:1"] }] })
	moveCardBy(draft, 0, 1, -1)
	assert.deepEqual(cards(draft), [["a:2", "a:1"], ["b:1"]])
	moveCardBy(draft, 0, 1, 1)
	assert.deepEqual(cards(draft), [["a:2"], ["a:1", "b:1"]])
	moveCardBy(draft, 1, 0, -1)
	assert.deepEqual(cards(draft), [["a:2", "a:1"], ["b:1"]])
	moveCardBy(draft, 0, 0, -1)
	assert.deepEqual(cards(draft), [["a:2", "a:1"], ["b:1"]])
	removeCard(draft, 1, 0)
	assert.deepEqual(cards(draft), [["a:2", "a:1"], []])
})

test("problems block saving and the payload carries the original name for edits", () => {
	const draft = createDraft()
	assert.deepEqual(getDraftProblems(draft, ["Premium White"]), ["Enter a layout title.", "Section Main has no cards."])
	draft.title = "Premium White"
	addCard(draft, 0, "merch:lots")
	assert.deepEqual(getDraftProblems(draft, ["Premium White"]), ["Premium White is a built-in layout name."])
	draft.title = "  Floor Desk "
	draft.sections[0].label = " "
	assert.deepEqual(getDraftProblems(draft, []), ["Every section needs a name."])
	draft.sections[0].label = "Orders"
	assert.deepEqual(getDraftProblems(draft, []), [])
	assert.deepEqual(getPayload(draft), { title: "Floor Desk", sections: JSON.stringify([{ label: "Orders", cards: ["merch:lots"] }]), original_name: "" })
	assert.equal(getPayload(createDraft({ name: "Old", sections: [] })).original_name, "Old")
})

test("a built-in department layout opens with its current cards in one section and saves as an override", () => {
	const fabric = { name: "Fabric Store", experience_key: "fabric-store", workspaces: ["work_orders", "reports", "purchase_orders"], sections: null }
	const draft = createDepartmentDraft(fabric)
	assert.equal(draft.department, "fabric-store")
	assert.equal(draft.title, "Fabric Store")
	assert.deepEqual(draft.sections.map((section) => [section.label, section.cards]), [["Fabric Store", ["fabric-store:work_orders", "fabric-store:purchase_orders", "fabric-store:reports"]]])
	addSection(draft)
	draft.sections[1].label = "Borrowed"
	addCard(draft, 1, "merch:lots")
	assert.deepEqual(getDraftProblems(draft, ["Fabric Store"]), [])
	assert.deepEqual(getPayload(draft), { layout: "Fabric Store", sections: JSON.stringify([
		{ label: "Fabric Store", cards: ["fabric-store:work_orders", "fabric-store:purchase_orders", "fabric-store:reports"] },
		{ label: "Borrowed", cards: ["merch:lots"] },
	]) })
	const saved = createDepartmentDraft({ ...fabric, sections: [{ label: "Mine", cards: ["merch:lots"] }] })
	assert.deepEqual(saved.sections.map((section) => [section.label, section.cards]), [["Mine", ["merch:lots"]]])
	assert.equal(saved.hasOverride, true)
	assert.equal(draft.hasOverride, false)
})

test("the catalogue is grouped by department, searchable and marks placed cards", () => {
	const groups = getCatalogueGroups("lot merch", new Set(["merch:lots"]))
	const merch = groups.find((group) => group.department.key === "merch")
	assert.ok(merch)
	assert.deepEqual(merch.entries.map((entry) => [entry.id, entry.placed]), [["merch:lots", true]])
	assert.ok(getCatalogueGroups("").length >= 16)
	assert.deepEqual(getCatalogueGroups("no such card anywhere"), [])
})

test("only System Managers open the builder and see it in the account menu", () => {
	assert.equal(getBuilderRedirect(ADMIN), undefined)
	assert.equal(getBuilderRedirect(MANAGER), undefined)
	assert.deepEqual(getBuilderRedirect(CLERK), { path: NO_PERMISSION_PATH, query: { doctype: "Layout Builder" }, replace: true })
	const actions = { changePassword() {}, logOutAllDevices() {}, openLayoutBuilder() {} }
	assert.ok(getAccountMenuItems(actions, MANAGER).some((item) => item.label === "Layout Builder"))
	assert.ok(!getAccountMenuItems(actions, CLERK).some((item) => item.label === "Layout Builder"))
	const router = source("../src/router/index.js")
	assert.match(router, /path: "\/layout-builder",[\s\S]*?beforeEnter: \(\) => getBuilderRedirect\(\)/)
	assert.match(router, /path: "\/workspace",[\s\S]*?beforeEnter: \(\) => getWorkspaceHomeRedirect\(\)/)
	assert.equal(WORKSPACE_HOME_PATH, "/workspace")
	assert.equal(LAYOUT_BUILDER_PATH, "/layout-builder")
})

const FABRIC_STORE = { name: "Fabric Store", experience_key: "fabric-store", workspaces: ["work_orders", "reports"], sections: null }

async function mountBuilder() {
	const { Vue, findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
	const stub = (type) => (props, { slots }) => Vue.h(type, props, slots?.default?.())
	const server = { saved: [], overrides: [], resets: [], layouts: [], departmentLayouts: [FABRIC_STORE] }
	const confirmations = []
	const component = loadComponent(new URL("../src/departments/workspace/LayoutBuilder.vue", import.meta.url).pathname, {
		"primevue/button": stub("button"),
		"primevue/inputtext": stub("input-text"),
		"primevue/message": stub("message"),
		"primevue/select": stub("select"),
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
		"../../api/workspaceLayout.js": {
			getBuilderData: async () => ({ layouts: server.layouts, department_layouts: server.departmentLayouts, reserved_names: ["Premium White", "Fabric Store"] }),
			saveLayout: async (payload) => {
				server.saved.push(payload)
				server.layouts = [{ name: payload.title, sections: JSON.parse(payload.sections) }]
				return { name: payload.title }
			},
			saveDepartmentOverride: async (payload) => {
				server.overrides.push(payload)
				server.departmentLayouts = [{ ...FABRIC_STORE, sections: JSON.parse(payload.sections) }]
				return { name: payload.layout }
			},
			resetDepartmentOverride: async (layout) => {
				server.resets.push(layout)
				server.departmentLayouts = [FABRIC_STORE]
			},
			deleteLayout: async () => {},
		},
		"../../components/DepartmentPage.vue": stub("department-page"),
		"../../components/common/WorkspaceLauncher.vue": stub("workspace-launcher"),
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => (options) => confirmations.push(options) },
		"../cardCatalogue.js": await import("../src/departments/cardCatalogue.js"),
		"./workspaceSections.js": await import("../src/departments/workspace/workspaceSections.js"),
		"./layoutBuilder.js": await import("../src/departments/workspace/layoutBuilder.js"),
	})
	const root = mountComponent(component, {})
	const tick = async () => { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() }
	const button = (label) => findNodes(root, (node) => node.type === "button").find((node) => node.props.label === label || node.props["aria-label"] === label)
	const find = (type) => findNodes(root, (node) => node.type === type)
	await tick()
	return { server, confirmations, tick, button, find }
}

test("the builder page adds catalogue cards, saves the draft and reopens the saved layout", async () => {
	const { server, tick, button, find } = await mountBuilder()

	button("Add Lot · Merch").props.onClick()
	button("Add Lot · Planning").props.onClick()
	await tick()
	assert.equal(button("Save").props.disabled, true)
	find("input-text").find((node) => node.props.placeholder === "e.g. Merch Desk").props["onUpdate:modelValue"]("Floor Desk")
	await tick()
	assert.equal(button("Save").props.disabled, false)
	assert.equal(button("Add Lot · Merch").props.disabled, true)

	button("Preview").props.onClick()
	await tick()
	assert.deepEqual(find("workspace-launcher")[0].props.sections[0].items.map((item) => [item.key, item.label]), [["merch:lots", "Lot"], ["planning:lots", "Lot"]])
	button("Edit").props.onClick()
	await tick()

	button("Move Lot · Planning up").props.onClick()
	await button("Save").props.onClick()
	await tick()
	assert.deepEqual(server.saved, [{ title: "Floor Desk", sections: JSON.stringify([{ label: "Main", cards: ["planning:lots", "merch:lots"] }]), original_name: "" }])
	assert.ok(button("Delete"))
	assert.equal(find("select")[0].props.modelValue, "Floor Desk")
})

test("a built-in layout opens with its current cards, saves as an override and resets to default", async () => {
	const { server, confirmations, tick, button, find } = await mountBuilder()
	assert.deepEqual(find("select")[0].props.options.map((option) => option.label), ["Fabric Store (built-in)"])

	find("select")[0].props.onChange({ value: "Fabric Store" })
	await tick()
	assert.equal(find("input-text").find((node) => node.props.placeholder === "e.g. Merch Desk").props.disabled, true)
	assert.equal(button("Delete"), undefined)
	assert.equal(button("Reset to default"), undefined)
	button("Add section").props.onClick()
	button("Add Lot · Merch").props.onClick()
	await tick()
	await button("Save").props.onClick()
	await tick()
	assert.deepEqual(server.overrides, [{ layout: "Fabric Store", sections: JSON.stringify([
		{ label: "Fabric Store", cards: ["fabric-store:work_orders", "fabric-store:reports"] },
		{ label: "New section", cards: ["merch:lots"] },
	]) }])

	button("Reset to default").props.onClick()
	await confirmations.at(-1).accept()
	await tick()
	assert.deepEqual(server.resets, ["Fabric Store"])
	assert.equal(button("Reset to default"), undefined)
})
