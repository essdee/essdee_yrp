import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

const read = (path) => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("every page back button uses the shared accent BackLink", () => {
	const backLink = read("components/navigation/BackLink.vue")
	assert.match(backLink, /class="back-link-button"/)
	assert.doesNotMatch(backLink, /<span|text:/)
	assert.match(backLink, /<i class="pi pi-arrow-left" aria-hidden="true" \/>/)
	assert.match(backLink, /:aria-label="`Back to \$\{label\}`"/)
	assert.match(backLink, /width: 38px;\s*height: 38px;/)
	assert.match(backLink, /color: var\(--erp-accent-ink\);/)
	assert.match(backLink, /v-if="!isLockedExit\(to\)"/)
	assert.match(backLink, /background: var\(--erp-accent-soft\);/)
	assert.match(backLink, /border: 1px solid var\(--erp-accent-border\);/)
	assert.match(backLink, /width: 44px; height: 44px;/)
	assert.match(read("components/navigation/InlinePageNavigation.vue"), /<BackLink :to="resolvedBackTo" :label="backLabel"/)
	assert.match(read("components/DepartmentPage.vue"), /<BackLink :to="backTo" :label="backLabel" \/>/)
})

test("list, launcher, report and dashboard headers hide Back because the module sidebar navigates", () => {
	const navigation = read("components/navigation/InlinePageNavigation.vue")
	assert.match(navigation, /<nav v-if="inline && showBack"/)
	assert.match(navigation, /showBack: \{ type: Boolean, default: true \}/)
	assert.match(read("components/common/ListView.vue"), /<InlinePageNavigation v-if="navigationEnabled" :show-back="false" \/>/)
	for (const path of [
		"components/common/WorkspaceLauncher.vue",
		"components/reports/ReportShell.vue",
		"departments/planning/dashboard/DashboardView.vue",
		"departments/planning/dashboard/PpoTrackingView.vue",
	]) assert.match(read(path), /<InlinePageNavigation :show-back="false" \/>/, path)
	assert.doesNotMatch(read("departments/sewing/SewingWorkspaceShell.vue"), /BackLink/)
	assert.doesNotMatch(read("departments/sewing/SewingLauncher.vue"), /BackLink|#navigation/)
	assert.equal(fs.existsSync(new URL("../src/departments/sewing/SewingBackLink.vue", import.meta.url)), false)
})

test("document view and edit headers keep Back", () => {
	for (const path of [
		"components/common/FormView.vue",
		"departments/fabric-store/FabricDocumentWorkspace.vue",
		"departments/fabric-store/PurchaseOrderEditor.vue",
		"departments/CuttingOrder.vue",
		"departments/purchase/ItemPage.vue",
	]) assert.doesNotMatch(read(path), /:show-back="false"/, path)
})

test("prev/next arrows keep the neutral style so Back stands apart", () => {
	const steps = read("components/navigation/DocumentStepButtons.vue")
	assert.match(steps, /color: var\(--erp-text-muted\);/)
	assert.doesNotMatch(steps, /accent-soft/)
})
