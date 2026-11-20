import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { merchLotActions, merchLotCommandSuccess } from "../src/departments/merch/lot/merchLotViews.js"
import { unlinkPpoAction } from "../src/departments/planning/lot/lotViews.js"

const capability = { visible: true, allowed: true, label: "Unlink PPO", reason: "" }

test("Merch Lot shows Unlink PPO only when the server exposes it", () => {
	const selected = []
	const actions = merchLotActions({ capabilities: { unlink_ppo: capability } }, (key) => selected.push(key))
	assert.deepEqual(actions.map((action) => [action.key, action.label, action.icon]), [["unlink_ppo", "Unlink PPO", "pi pi-times-circle"]])
	actions[0].command()
	assert.deepEqual(selected, ["unlink_ppo"])
	assert.deepEqual(merchLotActions({ capabilities: { unlink_ppo: { ...capability, visible: false } } }, () => {}), [])
	assert.equal(merchLotCommandSuccess("unlink_ppo", "LOT-1").summary, "PPO unlinked")
})

test("Lot actions hide Unlink PPO when the server blocks it", () => {
	const blocked = { ...capability, allowed: false, reason: "YRP Work Order WO-1 exists for this Lot." }
	assert.deepEqual(merchLotActions({ capabilities: { unlink_ppo: blocked } }, () => {}), [])
	assert.deepEqual(unlinkPpoAction({ unlink_ppo: blocked }, () => {}), [])
})

test("Planning Lot Unlink PPO action follows the server capability", () => {
	let opened = 0
	const [action] = unlinkPpoAction({ unlink_ppo: capability }, () => opened++)
	assert.equal(action.label, "Unlink PPO")
	assert.equal(action.disabled, false)
	action.command()
	assert.equal(opened, 1)
	assert.equal(unlinkPpoAction({ unlink_ppo: capability }, () => {}, "unlink_ppo")[0].disabled, true)
	assert.deepEqual(unlinkPpoAction({ unlink_ppo: { visible: false } }, () => {}), [])
	assert.deepEqual(unlinkPpoAction({}, () => {}), [])
})

test("Planning Lot page confirms before calling the unlink endpoint", () => {
	const page = readFileSync(new URL("../src/departments/planning/lot/LotPage.vue", import.meta.url), "utf8")
	assert.match(page, /<DocumentConfirmationDialog[\s\S]*v-model:visible="unlinkVisible"[\s\S]*@confirm="unlinkPpo"/)
	assert.match(page, /await unlinkLotProductionOrder\(props\.lotId, workspace\.value\.modified\)/)
})
