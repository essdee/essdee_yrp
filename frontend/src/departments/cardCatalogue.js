import { accountsLauncherItems } from "./accounts/accountsViews.js"
import { ACCESSORY_STORE_WORKSPACE_KEYS, FABRIC_STORE_WORKSPACE_KEYS, storeWorkspaces } from "./fabric-store/storeWorkspaces.js"
import { CUT_PANEL_STORE_WORKSPACES, CUTTING_WORKSPACES, FINISHING_WORKSPACES, HR_WORKSPACES, SALES_WORKSPACES, SEWING_WORKSPACES } from "./launcherCards.js"
import { merchPdLauncherItems } from "./merch-pd/merchPdViews.js"
import { merchPurchaseLauncherItems } from "./merch-purchase/merchPurchaseViews.js"
import { merchLauncherItems } from "./merch/merchViews.js"
import { pdLauncherItems } from "./pd/pdViews.js"
import { PLANNING_WORKSPACES } from "./planning/planningViews.js"
import { PURCHASE_REPORT_KEYS, PURCHASE_STORE_WORKSPACE_KEYS, purchaseLauncherItems } from "./purchase/purchaseViews.js"
import { qualityLauncherItems } from "./quality/qualityWorkspaces.js"
import { departments } from "./registry.js"

const storeCards = (basePath, keys, reportKeys) => storeWorkspaces(basePath, reportKeys).filter((card) => keys.includes(card.key))

/** Every launcher card each department's landing page can show, before permissions. */
const DEPARTMENT_CARDS = {
	cutting: CUTTING_WORKSPACES,
	"fabric-store": storeCards("/fabric-store", FABRIC_STORE_WORKSPACE_KEYS),
	"cut-panel-store": CUT_PANEL_STORE_WORKSPACES,
	"accessory-store": storeCards("/accessory-store", ACCESSORY_STORE_WORKSPACE_KEYS),
	sewing: SEWING_WORKSPACES,
	finishing: FINISHING_WORKSPACES,
	quality: qualityLauncherItems(),
	merch: merchLauncherItems(),
	purchase: [...purchaseLauncherItems(), ...storeCards("/purchase", PURCHASE_STORE_WORKSPACE_KEYS, PURCHASE_REPORT_KEYS)],
	"merch-purchase": merchPurchaseLauncherItems(),
	"merch-pd": merchPdLauncherItems(),
	sales: SALES_WORKSPACES,
	planning: PLANNING_WORKSPACES,
	pd: pdLauncherItems(),
	accounts: accountsLauncherItems(),
	hr: HR_WORKSPACES,
}

/** Cards a workspace layout may place, as `{ id: "<department>:<card key>", label, department, card }` in registry order. */
export const CARD_CATALOGUE = departments.flatMap((department) => {
	const cards = DEPARTMENT_CARDS[department.key] || []
	return cards
		.filter((card, index) => cards.findIndex((other) => other.key === card.key) === index)
		.map((card) => ({ id: `${department.key}:${card.key}`, label: `${card.label} · ${department.label}`, department, card }))
})

const CATALOGUE_BY_ID = new Map(CARD_CATALOGUE.map((entry) => [entry.id, entry]))

export function getCatalogueCard(id) {
	return CATALOGUE_BY_ID.get(id)
}
