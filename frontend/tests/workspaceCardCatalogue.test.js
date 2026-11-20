import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { CARD_CATALOGUE, getCatalogueCard } from "../src/departments/cardCatalogue.js"
import { CUTTING_WORKSPACES } from "../src/departments/launcherCards.js"
import { PLANNING_WORKSPACES } from "../src/departments/planning/planningViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"

const serverCardIds = JSON.parse(readFileSync(new URL("../../essdee_yrp/web_workspace_cards.json", import.meta.url), "utf8"))

test("every department contributes its launcher cards under '<department>:<card>' ids", () => {
	const ids = CARD_CATALOGUE.map((entry) => entry.id)
	assert.equal(new Set(ids).size, ids.length)
	for (const entry of CARD_CATALOGUE) {
		assert.equal(entry.id, `${entry.department.key}:${entry.card.key}`)
		assert.ok(departments.includes(entry.department), entry.id)
	}
	for (const department of departments) {
		assert.ok(CARD_CATALOGUE.some((entry) => entry.department === department), department.key)
	}
})

test("catalogue entries reference the department card definitions instead of copying them", () => {
	assert.equal(getCatalogueCard("cutting:reports").card, CUTTING_WORKSPACES.find((card) => card.key === "reports"))
	assert.equal(getCatalogueCard("planning:lots").card, PLANNING_WORKSPACES.find((card) => card.key === "lots"))
	assert.equal(getCatalogueCard("merch:lots").label, "Lot · Merch")
	assert.equal(getCatalogueCard("merch:lots").card.to, "/merch/lots")
	assert.equal(getCatalogueCard("purchase:lots").card.to, "/purchase/lots")
	assert.equal(getCatalogueCard("purchase:goods_received_notes").card.to, "/purchase/goods-received-notes")
	assert.equal(getCatalogueCard("fabric-store:box_stickers"), undefined)
	assert.equal(getCatalogueCard("unknown:lots"), undefined)
})

test("the server's list of valid card ids matches the catalogue", () => {
	assert.deepEqual([...serverCardIds].sort(), CARD_CATALOGUE.map((entry) => entry.id).sort())
})

test("each card opens a page its department's workspace owns, so a layout lock can allow it", () => {
	for (const entry of CARD_CATALOGUE) {
		assert.ok(getWorkspacePaths(entry.department)[entry.card.key]?.includes(entry.card.to), `${entry.id} -> ${entry.card.to}`)
	}
})
