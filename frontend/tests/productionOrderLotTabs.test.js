import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { lotFromTabKey, lotTabErrorMessage, lotTabKey } from "../src/departments/sales/productionOrderLotTabs.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const view = source("../src/departments/sales/ProductionOrder.vue")
const lotTab = source("../src/departments/sales/ProductionOrderLotTab.vue")

test("lot tab keys round-trip and never collide with fixed PPO tabs", () => {
	assert.equal(lotTabKey("LOT-0001"), "lot:LOT-0001")
	assert.equal(lotFromTabKey(lotTabKey("LOT-0001")), "LOT-0001")
	for (const key of ["details", "transfers", "time_and_action", "", undefined]) assert.equal(lotFromTabKey(key), "")
})

test("lot tab errors explain permission and missing lots", () => {
	assert.equal(lotTabErrorMessage({ exc_type: "PermissionError", message: "x" }, "L1"), "You do not have permission to view Lot L1.")
	assert.equal(lotTabErrorMessage({ status: 403 }, "L1"), "You do not have permission to view Lot L1.")
	assert.equal(lotTabErrorMessage({ exc_type: "DoesNotExistError" }, "L1"), "Lot L1 no longer exists.")
	assert.equal(lotTabErrorMessage({ message: "Boom" }, "L1"), "Boom")
	assert.equal(lotTabErrorMessage(null, "L1"), "Unable to load Lot L1.")
})

test("PPO view adds one tab per linked lot, labelled with the lot name", () => {
	assert.match(view, /const linkedLots = computed\(\(\) => workspace\.value\.linked_lots \|\| \[\]\)/)
	assert.match(view, /<Tab v-for="lot in linkedLots" :key="lot" :value="lotTabKey\(lot\)">\{\{ lot \}\}<\/Tab>/)
	assert.match(view, /<TabPanel v-for="lot in linkedLots" :key="lot" :value="lotTabKey\(lot\)">/)
})

test("lot tab content mounts only after its tab is first opened", () => {
	assert.match(view, /<ProductionOrderLotTab v-if="openedLotTabs\.has\(lot\)" :lot="lot" \/>/)
	assert.match(view, /watch\(activeTab, \(tab\) => \{\s*const lot = lotFromTabKey\(tab\)/)
	assert.match(view, /if \(lotFromTabKey\(activeTab\.value\) && !lots\.includes\(lotFromTabKey\(activeTab\.value\)\)\) activeTab\.value = "details"/)
})

test("lot tab shows only the Planning process flow, from its lean context, and links to the full page", () => {
	assert.match(lotTab, /import \{ getLotFlowContext \} from "\.\.\/\.\.\/api\/planning\.js"/)
	assert.match(lotTab, /import LotProcessFlow from "\.\.\/planning\/lot\/flow\/LotProcessFlow\.vue"/)
	assert.match(lotTab, /<LotProcessFlow v-else-if="context\.name" :lot="context\.name" :item="context\.item \|\| ''" :fabrics="context\.fabrics \|\| \[\]" \/>/)
	assert.doesNotMatch(lotTab, /LotViewMain|getLotWorkspace/)
	assert.match(lotTab, /<h2>Lot · \{\{ lot \}\}<\/h2><DocumentStatusBadge/)
	assert.match(lotTab, /:to="\{ name: PLANNING_ROUTES\.lot, params: \{ lotId: lot \} \}"/)
	assert.match(lotTab, /error\.value = lotTabErrorMessage\(reason, requested\)/)
	assert.match(source("../src/api/planning.js"), /export function getLotFlowContext\(lot\) \{\s*return callRead\(`\$\{LOT_METHOD\}\.get_lot_flow_context`, \{ lot \}\)/)
})
