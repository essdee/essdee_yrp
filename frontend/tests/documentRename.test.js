import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const { renameDoc } = await import("../src/api/frappe.js")
const { canRenameDocument, renamedLocation, waitForRename } = await import("../src/utils/documentRename.js")
const { useRenameAction } = await import("../src/composables/useRenameAction.js")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }

test("Rename follows Desk can_rename: write permission, allow_rename, saved, not single", () => {
	const meta = { allow_rename: 1, issingle: 0 }
	const permissions = { write: 1 }
	assert.equal(canRenameDocument({ meta, permissions, name: "ITEM-1" }), true)
	assert.equal(canRenameDocument({ meta: { ...meta, allow_rename: 0 }, permissions, name: "ITEM-1" }), false)
	assert.equal(canRenameDocument({ meta: { ...meta, issingle: 1 }, permissions, name: "ITEM-1" }), false)
	assert.equal(canRenameDocument({ meta, permissions: { write: 0 }, name: "ITEM-1" }), false)
	assert.equal(canRenameDocument({ meta, permissions: null, name: "ITEM-1" }), false)
	assert.equal(canRenameDocument({ meta, permissions, name: "" }), false)
	assert.equal(canRenameDocument({ meta: null, permissions, name: "ITEM-1" }), false)
})

test("renamedLocation swaps the route param holding the old name and keeps the rest", () => {
	const route = { name: "lot-tab", params: { lotId: "LOT A", tab: "ppo" }, query: { from: "list" }, hash: "#x" }
	assert.deepEqual(renamedLocation(route, "LOT A", "LOT B"), { name: "lot-tab", params: { lotId: "LOT B", tab: "ppo" }, query: { from: "list" }, hash: "#x" })
	assert.equal(renamedLocation(route, "OTHER", "LOT B"), null)
	assert.equal(renamedLocation(null, "LOT A", "LOT B"), null)
})

test("renameDoc queues Frappe's update_document_title like Desk", async () => {
	const previousWindow = globalThis.window
	const previousFetch = globalThis.fetch
	const requests = []
	globalThis.window = { csrf_token: "test-csrf" }
	globalThis.fetch = async (url, options) => {
		requests.push({ url, body: JSON.parse(options.body) })
		return { ok: true, status: 200, json: async () => ({ message: "NEW" }) }
	}
	try {
		assert.equal(await renameDoc("Item", "OLD", "NEW", true), "NEW")
	} finally {
		globalThis.window = previousWindow
		globalThis.fetch = previousFetch
	}
	assert.equal(requests[0].url, "/api/method/frappe.model.rename_doc.update_document_title")
	assert.deepEqual(requests[0].body, { doctype: "Item", docname: "OLD", name: "NEW", merge: 1, enqueue: 1 })
})

test("waitForRename polls the queued rename until it is done", async () => {
	const statuses = [{ status: "running" }, { status: "running" }, { status: "done", name: "NEW" }]
	const calls = []
	const name = await waitForRename("Item", "OLD", "NEW", "2026-11-23 10:00:00", {
		fetchStatus: async (...args) => { calls.push(args); return statuses.shift() },
		sleep: async () => {},
	})
	assert.equal(name, "NEW")
	assert.equal(calls.length, 3)
	assert.deepEqual(calls[0], ["Item", "OLD", "NEW", "2026-11-23 10:00:00"])
})

test("waitForRename raises the background job's error", async () => {
	await assert.rejects(
		waitForRename("Item", "OLD", "NEW", "t", { fetchStatus: async () => ({ status: "failed", error: "Name exists" }), sleep: async () => {} }),
		/Name exists/,
	)
})

function renameScope(meta, permissions) {
	const state = Vue.reactive({ doctype: "Item", docname: "ITEM-1" })
	const calls = []
	const scope = Vue.effectScope()
	const result = scope.run(() => useRenameAction(() => [state.doctype, state.docname], {
		fetchMeta: async (doctype) => { calls.push(["meta", doctype]); return [{ name: doctype, ...meta }] },
		fetchPermissions: async (doctype, name) => { calls.push(["perm", doctype, name]); return permissions },
	}))
	return { state, calls, scope, ...result }
}

test("useRenameAction offers a menu-only Rename that opens the dialog when Desk would", async () => {
	const { action, visible, calls, scope } = renameScope({ allow_rename: 1 }, { write: 1 })
	await tick(); await tick()
	assert.deepEqual(calls.map((call) => call[0]).sort(), ["meta", "perm"])
	assert.equal(action.value.key, "rename")
	assert.equal(action.value.label, "Rename")
	assert.equal(action.value.menuOnly, true)
	assert.equal(visible.value, false)
	action.value.command()
	assert.equal(visible.value, true)
	scope.stop()
})

test("useRenameAction hides Rename for non-renamable doctypes and users without write", async () => {
	for (const [meta, permissions] of [[{ allow_rename: 0 }, { write: 1 }], [{ allow_rename: 1 }, { write: 0 }]]) {
		const { action, scope } = renameScope(meta, permissions)
		await tick(); await tick()
		assert.equal(action.value, null)
		scope.stop()
	}
})

async function loadDialog({ rename, route, replaces, toasts, statuses = [] }) {
	return loadComponent(resolve("frontend/src/components/documents/DocumentRenameDialog.vue"), {
		"primevue/dialog": (props, { slots }) => Vue.h("dialog", props, props.visible ? [slots.default?.(), slots.footer?.()] : []),
		"primevue/button": (props) => Vue.h("button", props, props.label),
		"primevue/inputtext": (props) => Vue.h("input", props),
		"primevue/checkbox": (props) => Vue.h("checkbox", props),
		"primevue/message": (props, { slots }) => Vue.h("message", props, slots.default?.()),
		"primevue/usetoast": { useToast: () => ({ add: (toast) => toasts.push(toast) }) },
		"vue-router": { useRoute: () => route, useRouter: () => ({ replace: async (target) => replaces.push(target) }) },
		"../../api/frappe.js": { renameDoc: rename, getRenameStatus: async () => statuses.shift() || { status: "running", checked_at: "t0" } },
		"../../utils/documentRename.js": { ...(await import("../src/utils/documentRename.js")), RENAME_POLL_MS: 0 },
		"../../router/webDocumentRoutes.js": { webDocumentRoute: (doctype, name) => `/doc/${doctype}/${name}` },
	})
}

test("DocumentRenameDialog renames and opens the renamed document's page", async () => {
	const calls = [], replaces = [], toasts = []
	const route = { name: "item", params: { itemId: "ITEM-1" }, query: {}, hash: "" }
	const props = Vue.reactive({ doctype: "Item", docname: "ITEM-1", visible: true, "onUpdate:visible": (value) => { props.visible = value } })
	const root = mountComponent(await loadDialog({ rename: async (...args) => { calls.push(args); return "ITEM-2" }, route, replaces, toasts }), props)
	await tick()
	const text = findNodes(root, (node) => node.text).map((node) => node.text).join(" ")
	assert.match(text, /ITEM-1/)
	const input = findNodes(root, (node) => node.type === "input")[0]
	assert.equal(input.props.modelValue, "ITEM-1")
	input.props["onUpdate:modelValue"]("ITEM-2")
	findNodes(root, (node) => node.type === "checkbox")[0].props["onUpdate:modelValue"](true)
	await tick()
	findNodes(root, (node) => node.type === "button" && node.props.label === "Rename")[0].props.onClick()
	await tick(); await tick()
	assert.deepEqual(calls, [["Item", "ITEM-1", "ITEM-2", true]])
	assert.deepEqual(replaces, [{ name: "item", params: { itemId: "ITEM-2" }, query: {}, hash: "" }])
	assert.equal(props.visible, false)
	assert.match(toasts[0].summary, /ITEM-1.*ITEM-2/)
})

test("DocumentRenameDialog shows Renaming… and locks the dialog until the queued rename finishes", async () => {
	const replaces = [], toasts = []
	let finish
	const route = { name: "item", params: { itemId: "ITEM-1" }, query: {}, hash: "" }
	const props = Vue.reactive({ doctype: "Item", docname: "ITEM-1", visible: true, "onUpdate:visible": (value) => { props.visible = value } })
	const rename = () => new Promise((done) => { finish = done })
	const statuses = [{ status: "running", checked_at: "t0" }, { status: "done", name: "ITEM-2" }]
	const root = mountComponent(await loadDialog({ rename, route, replaces, toasts, statuses }), props)
	await tick()
	findNodes(root, (node) => node.type === "input")[0].props["onUpdate:modelValue"]("ITEM-2")
	await tick()
	findNodes(root, (node) => node.type === "button" && node.props.label === "Rename")[0].props.onClick()
	await tick(); await tick()
	const text = () => findNodes(root, (node) => node.text).map((node) => node.text).join(" ")
	assert.match(text(), /Renaming…/)
	const buttons = findNodes(root, (node) => node.type === "button")
	assert.ok(buttons.every((button) => button.props.disabled || button.props.loading), "buttons locked while renaming")
	assert.equal(findNodes(root, (node) => node.type === "dialog")[0].props.closable, false)
	finish("ITEM-1")
	for (let index = 0; index < 6; index++) await tick()
	assert.deepEqual(replaces, [{ name: "item", params: { itemId: "ITEM-2" }, query: {}, hash: "" }])
	assert.equal(props.visible, false)
	assert.doesNotMatch(text(), /Renaming…/)
})

test("DocumentRenameDialog shows the server error and stays open", async () => {
	const replaces = [], toasts = []
	const route = { name: "item", params: { itemId: "ITEM-1" }, query: {}, hash: "" }
	const props = Vue.reactive({ doctype: "Item", docname: "ITEM-1", visible: true, "onUpdate:visible": (value) => { props.visible = value } })
	const rename = async () => { throw new Error("Another Item with name ITEM-2 exists, select another name") }
	const root = mountComponent(await loadDialog({ rename, route, replaces, toasts }), props)
	await tick()
	findNodes(root, (node) => node.type === "input")[0].props["onUpdate:modelValue"]("ITEM-2")
	await tick()
	findNodes(root, (node) => node.type === "button" && node.props.label === "Rename")[0].props.onClick()
	await tick(); await tick()
	const message = findNodes(root, (node) => node.type === "message")[0]
	assert.ok(message, "error message rendered")
	assert.match(findNodes(message, (node) => node.text).map((node) => node.text).join(" "), /Another Item with name ITEM-2 exists/)
	assert.equal(props.visible, true)
	assert.deepEqual(replaces, [])
})

test("DocumentRenameDialog blocks an unchanged or empty name", async () => {
	const calls = []
	const route = { name: "item", params: { itemId: "ITEM-1" }, query: {}, hash: "" }
	const root = mountComponent(await loadDialog({ rename: async (...args) => { calls.push(args) }, route, replaces: [], toasts: [] }), { doctype: "Item", docname: "ITEM-1", visible: true })
	await tick()
	const button = findNodes(root, (node) => node.type === "button" && node.props.label === "Rename")[0]
	assert.equal(button.props.disabled, true)
})

test("DocumentActionStrip adds Rename to the More menu when the document can be renamed", async () => {
	const visible = Vue.ref(false)
	const renamable = Vue.ref(true)
	const sources = []
	const strip = loadComponent(resolve("frontend/src/components/documents/DocumentActionStrip.vue"), {
		"primevue/button": (props) => Vue.h("button", props, props.label),
		"primevue/menu": { props: ["model"], setup: (props, { expose }) => { expose({ toggle() {} }); return () => Vue.h("menu", { model: props.model }) } },
		"./LinkedDocumentsDialog.vue": () => null,
		"./DocumentRenameDialog.vue": (props) => Vue.h("rename-dialog", props),
		"../../composables/useRenameAction.js": {
			useRenameAction: (source) => {
				sources.push(source)
				const action = Vue.computed(() => renamable.value ? { key: "rename", label: "Rename", menuOnly: true, command: () => { visible.value = true } } : null)
				return { action, visible }
			},
		},
	})
	const root = mountComponent(strip, { actions: [{ key: "edit", label: "Edit", primary: true, command() {} }], doctype: "Item", docname: "ITEM-1" })
	assert.deepEqual(sources[0](), ["Item", "ITEM-1"])
	findNodes(root, (node) => node.type === "button" && node.props.label === "More")[0].props.onClick({})
	await tick()
	const item = findNodes(root, (node) => node.type === "menu")[0].props.model.find((entry) => entry.label === "Rename")
	assert.ok(item, "More menu lists Rename")
	const dialog = findNodes(root, (node) => node.type === "rename-dialog")[0]
	assert.deepEqual([dialog.props.doctype, dialog.props.docname, dialog.props.visible], ["Item", "ITEM-1", false])
	item.command()
	await tick()
	assert.equal(findNodes(root, (node) => node.type === "rename-dialog")[0].props.visible, true)
	renamable.value = false
	await tick()
	findNodes(root, (node) => node.type === "button" && node.props.label === "More")[0].props.onClick({})
	await tick()
	assert.equal(findNodes(root, (node) => node.type === "menu")[0].props.model.some((entry) => entry.label === "Rename"), false)
	assert.equal(findNodes(root, (node) => node.type === "rename-dialog").length, 0)
})
