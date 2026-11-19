import { workspaceReportTarget } from "../../components/common/workspaceSearch.js"
import { isOutsideLayout, isWorkspaceInLayout, lockedDepartment } from "../../router/departmentLock.js"
import { canOpenList } from "../../router/listPermission.js"
import { accountsLauncherItems, accountsReportTabs } from "../accounts/accountsViews.js"
import { cutPanelReportTabs, cuttingReportTabs, finishingReportTabs, hrReportTabs, merchReportTabs, qualityReportTabs, salesReportTabs, sewingReportTabs, storeReportTabs } from "../departmentReports.js"
import { ACCESSORY_STORE_WORKSPACE_KEYS, FABRIC_STORE_WORKSPACE_KEYS, storeSections, visibleStoreWorkspaces } from "../fabric-store/storeWorkspaces.js"
import { CUT_PANEL_STORE_WORKSPACES, CUTTING_WORKSPACES, FINISHING_WORKSPACES, HR_WORKSPACES, SALES_WORKSPACES, SEWING_WORKSPACES } from "../launcherCards.js"
import { merchPdLauncherItems } from "../merch-pd/merchPdViews.js"
import { merchPurchaseLauncherItems } from "../merch-purchase/merchPurchaseViews.js"
import { merchLauncherItems } from "../merch/merchViews.js"
import { pdLauncherItems } from "../pd/pdViews.js"
import { visiblePlanningWorkspaces } from "../planning/planningViews.js"
import { loadPlanningReports } from "../planning/reports/planningReportLoader.js"
import { PURCHASE_REPORT_KEYS, PURCHASE_STORE_WORKSPACE_KEYS, purchaseLauncherItems } from "../purchase/purchaseViews.js"
import { qualityLauncherItems } from "../quality/qualityWorkspaces.js"
import { departments } from "../registry.js"

const readable = (cards, sections) => cards.filter((card) => sections?.[card.key]?.can_read)

function storeDepartment(basePath, workspaceKeys, reportKeys, withPurchase = false) {
	return (all) => {
		const extraWorkspaces = withPurchase ? purchaseLauncherItems() : []
		const sections = storeSections(workspaceKeys, all.fabric_store?.sections, all.cut_panel_store?.sections, withPurchase ? all.purchase?.sections : {})
		return {
			cards: visibleStoreWorkspaces(sections, { basePath, workspaceKeys, reportKeys, extraWorkspaces }),
			reports: storeReportTabs(all.fabric_store?.sections?.reports?.reports, basePath.slice(1), reportKeys),
		}
	}
}

function merchDepartment(items, source, reportDepartment) {
	return (all) => ({ cards: readable(items(), all[source]?.sections), reports: merchReportTabs(reportDepartment, all[source]?.reports) })
}

async function planningDepartment(all) {
	const sections = all.planning?.sections || {}
	const loaders = { cutting: async () => all.cutting_reports, sewing: async () => all.sewing, finishing: async () => all.finishing }
	return {
		cards: visiblePlanningWorkspaces(sections),
		reports: sections.reports?.can_read ? await loadPlanningReports(sections.reports, loaders) : [],
	}
}

/** Per department: the launcher cards and reports its landing page shows for the `get_department_capabilities` payload. */
export const DEPARTMENT_CARD_SOURCES = {
	cutting: (all) => ({ cards: readable(CUTTING_WORKSPACES, all.cutting), reports: all.cutting?.reports?.can_read ? cuttingReportTabs(all.cutting_reports) : [] }),
	"fabric-store": storeDepartment("/fabric-store", FABRIC_STORE_WORKSPACE_KEYS, ["stock_balance"]),
	"cut-panel-store": (all) => ({ cards: readable(CUT_PANEL_STORE_WORKSPACES, all.cut_panel_store?.sections), reports: cutPanelReportTabs(all.cut_panel_store?.sections?.reports?.reports) }),
	"accessory-store": storeDepartment("/accessory-store", ACCESSORY_STORE_WORKSPACE_KEYS, ["stock_balance"]),
	sewing: (all) => ({ cards: readable(SEWING_WORKSPACES, all.sewing?.sections), reports: sewingReportTabs(all.sewing?.reports), reportQueryKey: "tab" }),
	finishing: (all) => ({ cards: readable(FINISHING_WORKSPACES, all.finishing?.sections), reports: finishingReportTabs(all.finishing?.sections?.reports?.reports) }),
	quality: (all) => ({ cards: readable(qualityLauncherItems(), all.quality?.sections), reports: qualityReportTabs(all.quality?.reports) }),
	merch: merchDepartment(merchLauncherItems, "merch", "merch"),
	purchase: storeDepartment("/purchase", PURCHASE_STORE_WORKSPACE_KEYS, PURCHASE_REPORT_KEYS, true),
	"merch-purchase": merchDepartment(merchPurchaseLauncherItems, "merch_purchase", "merch-purchase"),
	"merch-pd": merchDepartment(merchPdLauncherItems, "merch_pd", "merch"),
	sales: (all) => ({ cards: readable(SALES_WORKSPACES, all.sales?.sections), reports: salesReportTabs(all.sales) }),
	planning: planningDepartment,
	pd: (all) => ({ cards: readable(pdLauncherItems(), all.pd?.sections), reports: [] }),
	accounts: (all) => ({ cards: readable(accountsLauncherItems(), all.accounts?.sections), reports: accountsReportTabs(all.accounts?.reports) }),
	hr: (all) => ({ cards: readable(HR_WORKSPACES, all.hr?.sections), reports: hrReportTabs(all.hr?.reports) }),
}

async function departmentEntries(department, all, { boot, lock }) {
	const source = await DEPARTMENT_CARD_SOURCES[department.key](all)
	const cards = source.cards.filter((card) => isWorkspaceInLayout(card, lock) && canOpenList(card.to, boot))
	const reportsCard = cards.find((card) => card.key === "reports")
	const reports = reportsCard ? source.reports.map((report) => ({
		...report,
		to: workspaceReportTarget(reportsCard.to, report.value, source.reportQueryKey),
	})) : []
	return [
		...cards.map((card) => ({ kind: "card", department, item: card })),
		...reports.map((report) => ({ kind: "report", department, item: report })),
	]
}

/** Every card and report the user can open, across the departments in their UI layout (`lock`), in registry order. */
export async function getDepartmentEntries(all = {}, { boot = undefined, lock = lockedDepartment } = {}) {
	const visible = departments.filter((department) => !isOutsideLayout(department.path, lock))
	return (await Promise.all(visible.map((department) => departmentEntries(department, all, { boot, lock })))).flat()
}
