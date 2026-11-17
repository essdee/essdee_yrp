import assert from "node:assert/strict"
import test from "node:test"
import { getDocumentSound, playSound } from "../src/utils/documentSound.js"

const SOUNDS = [
	{ name: "submit", src: "/assets/frappe/sounds/submit.mp3", volume: 0.1 },
	{ name: "cancel", src: "/assets/frappe/sounds/cancel.mp3", volume: 0.1 },
]

function withAudio(boot, run) {
	const previousWindow = globalThis.window, previousAudio = globalThis.Audio, previousFetch = globalThis.fetch
	const played = []
	globalThis.window = { csrf_token: "token", frappe: { boot } }
	globalThis.Audio = class {
		constructor(src) { this.src = src; this.paused = true }
		play() { played.push({ src: this.src, volume: this.volume }); return Promise.resolve() }
	}
	return Promise.resolve(run(played)).finally(() => {
		globalThis.window = previousWindow; globalThis.Audio = previousAudio; globalThis.fetch = previousFetch
	})
}

test("lifecycle calls map to Desk's submit and cancel sounds", () => {
	assert.equal(getDocumentSound("essdee_yrp.api.lifecycle.submit_document", { doctype: "X", name: "1" }), "submit")
	assert.equal(getDocumentSound("essdee_yrp.api.lifecycle.cancel_document", { doctype: "X", name: "1" }), "cancel")
	assert.equal(getDocumentSound("m.change_document_status", { action: "submit" }), "submit")
	assert.equal(getDocumentSound("m.change_document_status", { action: "cancel" }), "cancel")
	assert.equal(getDocumentSound("m.execute_bill_tracking_command", { command: "submit" }), "submit")
	assert.equal(getDocumentSound("m.execute_plan_command", { command: "cancel_linked_document" }), "cancel")
	assert.equal(getDocumentSound("m.save_order", { values: {}, submit: true }), "submit")
	assert.equal(getDocumentSound("m.save_dispatch", { items: [], submit: 1 }), "submit")
	assert.equal(getDocumentSound("x.cancel_laysheet", { doc_name: "L-1" }), "cancel")
	assert.equal(getDocumentSound("x.submit_erp_invoice", { name: "P-1" }), "submit")
})

test("plain saves, amends and lookalike names stay silent", () => {
	assert.equal(getDocumentSound("m.save_order", { values: {}, submit: false }), "")
	assert.equal(getDocumentSound("m.save_dispatch", { items: [], submit: 0 }), "")
	assert.equal(getDocumentSound("m.change_document_status", { action: "amend" }), "")
	assert.equal(getDocumentSound("m.request_bill_cancellation", { name: "B-1" }), "")
	assert.equal(getDocumentSound("m.search_submitted_colour_codes", { query: "" }), "")
	assert.equal(getDocumentSound("m.set_planned_suppliers", { action: "constructor" }), "")
	assert.equal(getDocumentSound("m.save_recut", { values: { submit_recut: true } }), "")
})

test("playSound uses the boot sound list and respects mute_sounds", async () => {
	await withAudio({ sounds: SOUNDS, user: { mute_sounds: 0 } }, (played) => {
		playSound("cancel")
		assert.deepEqual(played, [{ src: "/assets/frappe/sounds/cancel.mp3", volume: 0.1 }])
	})
	await withAudio({ sounds: SOUNDS, user: { mute_sounds: 1 } }, (played) => {
		playSound("submit")
		assert.deepEqual(played, [])
	})
	await withAudio({ user: {} }, (played) => {
		playSound("submit")
		assert.deepEqual(played, [])
	})
})

test("blocked audio never breaks the caller", async () => {
	await withAudio({ sounds: SOUNDS, user: {} }, () => {
		globalThis.Audio = class { constructor() { throw new Error("no audio") } }
		assert.doesNotThrow(() => playSound("submit"))
	})
})

test("callMethod plays the sound only after a successful submit", async () => {
	const { submitDoc, cancelDoc, callMethod } = await import("../src/api/frappe.js")
	await withAudio({ sounds: SOUNDS, user: { mute_sounds: 0 } }, async (played) => {
		let fail = false
		globalThis.fetch = async () => fail
			? { ok: false, status: 417, json: async () => ({ exc_type: "ValidationError", _server_messages: "[]" }) }
			: { ok: true, status: 200, json: async () => ({ message: {} }) }
		await callMethod("m.save_order", { values: {}, submit: false })
		assert.equal(played.length, 0)
		await submitDoc("X", "1")
		assert.equal(played.at(-1).src, "/assets/frappe/sounds/submit.mp3")
		fail = true
		await assert.rejects(cancelDoc("X", "1"))
		assert.equal(played.length, 1)
	})
})
