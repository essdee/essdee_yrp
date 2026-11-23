import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { extractServerMessage } from "../src/api/errorMessages.js"
import { messageSegments } from "../src/api/messageLinks.js"

const frappeMessages = (...entries) => JSON.stringify(entries.map((entry) => JSON.stringify(entry)))

const slug = (doctype) => doctype.toLowerCase().replaceAll(" ", "-")
// Frappe's msgprint sanitiser keeps only href and adds rel, as the server sends it.
const shortage = (doctype, name, label = `${doctype} ${name}`) =>
	`Insufficient stock for 1 item:<ul><li>Fabric (Lot L1) at S-0163: balance 1.0, requested 5.0, short 4.0<br>Last reduced by <a href="/app/${slug(doctype)}/${encodeURIComponent(name)}" rel="noopener noreferrer">${label}</a> on 20-11-2026 09:05 (qty -4.0)</li></ul>`

function withPath(pathname, run) {
	const previous = globalThis.location
	globalThis.location = { pathname }
	try { return run() } finally { globalThis.location = previous }
}

test("a server message link keeps its label as plain text", () => {
	const text = extractServerMessage({ _server_messages: frappeMessages({ message: shortage("YRP Stock Entry", "SE-1") }) })
	assert.equal(text, "Insufficient stock for 1 item:\n• Fabric (Lot L1) at S-0163: balance 1.0, requested 5.0, short 4.0\nLast reduced by YRP Stock Entry SE-1 on 20-11-2026 09:05 (qty -4.0)")
})

test("the linked document opens on its /web page", () => {
	const text = extractServerMessage({ _server_messages: frappeMessages({ message: shortage("YRP Delivery Challan", "DC-7") }) })
	const segments = withPath("/web/fabric-store/delivery-challans/new", () => messageSegments(text))
	const link = segments.find((segment) => segment.href)
	assert.deepEqual(link, { text: "YRP Delivery Challan DC-7", href: "/web/fabric-store/delivery-challans/DC-7" })
	assert.equal(segments.map((segment) => segment.text).join(""), text)
})

test("a document without a /web page falls back to Desk", () => {
	const text = extractServerMessage({ _server_messages: frappeMessages({ message: shortage("YRP Stock Entry", "SE 2/3") }) })
	const link = withPath("/web/fabric-store", () => messageSegments(text)).find((segment) => segment.href)
	assert.deepEqual(link, { text: "YRP Stock Entry SE 2/3", href: "/app/yrp-stock-entry/SE%202%2F3" })
})

test("escaped names stay text and unknown text gets no link", () => {
	const text = extractServerMessage({ _server_messages: frappeMessages({ message: shortage("YRP Stock Entry", "SE<b>", "YRP Stock Entry SE&lt;b&gt;") }) })
	const link = withPath("/web", () => messageSegments(text)).find((segment) => segment.href)
	assert.deepEqual(link, { text: "YRP Stock Entry SE<b>", href: "/app/yrp-stock-entry/SE%3Cb%3E" })
	assert.deepEqual(messageSegments("Nothing to link here"), [{ text: "Nothing to link here" }])
})

test("an anchor whose label does not match its Desk route is never linked", () => {
	const mismatched = `<a href="/app/yrp-stock-entry/X-1">javascript:alert(1) X-1</a> and <a href="/app/yrp-stock-entry/X-2">Other Doc X-2</a>`
	const text = extractServerMessage({ _server_messages: frappeMessages({ message: mismatched }) })
	assert.equal(withPath("/web", () => messageSegments(text)).some((segment) => segment.href), false)
})

test("the document error dialog renders message links as anchors in a new tab", () => {
	const dialog = fs.readFileSync(new URL("../src/components/documents/DocumentErrorDialog.vue", import.meta.url), "utf8")
	assert.match(dialog, /messageSegments\(/)
	assert.match(dialog, /<a v-if="segment\.href" :href="segment\.href" target="_blank" rel="noopener"/)
	assert.doesNotMatch(dialog, /v-html/)
})
