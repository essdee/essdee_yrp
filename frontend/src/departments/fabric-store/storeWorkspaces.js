export const FABRIC_STORE_WORKSPACE_KEYS = ["work_orders", "delivery_challans", "goods_received_notes", "purchase_orders", "stock_transfers", "item_conversions", "reports"]
export const ACCESSORY_STORE_WORKSPACE_KEYS = ["work_orders", "delivery_challans", "goods_received_notes", "purchase_orders", "stock_transfers", "item_conversions", "excel_stickers", "reports"]

/** Delivery Challan and GRN launcher cards for a department with Work Orders under `basePath`. */
export function documentWorkspaces(basePath) {
	return [
		{ key: "delivery_challans", label: "Delivery Challans", description: "Review Delivery Challans made against Work Orders.", icon: "pi pi-truck", to: `${basePath}/delivery-challans` },
		{ key: "goods_received_notes", label: "Goods Received Notes", description: "Review Goods Received Notes received against Work Orders.", icon: "pi pi-inbox", to: `${basePath}/goods-received-notes` },
	]
}

/** Launcher cards shared by the store departments under `basePath`. */
export function storeWorkspaces(basePath, reportKeys = ["stock_balance"]) {
	return [
		{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", to: `${basePath}/work-orders` },
		...documentWorkspaces(basePath),
		{ key: "purchase_orders", label: "Purchase Orders", description: "Review purchase quantities and create Goods Received Notes.", icon: "pi pi-shopping-cart", to: `${basePath}/purchase-orders` },
		{ key: "stock_transfers", label: "Stock Transfers", description: "Create and review store stock movements and reconciliations.", icon: "pi pi-arrow-right-arrow-left", to: `${basePath}/stock-transfers` },
		{ key: "item_conversions", label: "Item Conversions", description: "Convert one item into another at a location, keeping its value.", icon: "pi pi-sync", to: `${basePath}/item-conversions` },
		{ key: "box_stickers", label: "Box Sticker Print", description: "Prepare, preview and print size-based box labels.", icon: "pi pi-tags", to: `${basePath}/box-sticker-prints` },
		{ key: "excel_stickers", label: "Excel Sticker Print", description: "Upload sticker rows, preview labels and print through QZ.", icon: "pi pi-file-excel", to: `${basePath}/excel-sticker-prints` },
		{
			key: "reports",
			label: "Reports",
			description: reportKeys.includes("purchase_order_itemwise")
				? "Review stock, Purchase Order items and Lot cut quantities."
				: "Generate the current stock balance for store locations.",
			icon: "pi pi-chart-bar",
			to: `${basePath}/reports`,
		},
	]
}

/** Sticker sections a store department takes from the Cut Panel Store capabilities. */
export const CUT_PANEL_STICKER_KEYS = ["box_stickers", "excel_stickers"]

/** One store department's sections: Fabric Store, then `extraSections`, then the Cut Panel sticker sections it lists. */
export function storeSections(workspaceKeys, fabricSections = {}, cutPanelSections = {}, extraSections = {}) {
	const sections = { ...fabricSections, ...extraSections }
	for (const key of CUT_PANEL_STICKER_KEYS) {
		if (workspaceKeys.includes(key) && cutPanelSections[key]) sections[key] = cutPanelSections[key]
	}
	return sections
}

/** Store launcher cards shown for `sections`; Reports needs one readable report of `reportKeys`. */
export function visibleStoreWorkspaces(sections, { basePath, workspaceKeys, reportKeys = ["stock_balance"], extraWorkspaces = [] }) {
	const keys = new Set([...extraWorkspaces.map((workspace) => workspace.key), ...workspaceKeys])
	return [...extraWorkspaces, ...storeWorkspaces(basePath, reportKeys)].filter((workspace) => (
		keys.has(workspace.key)
			&& sections[workspace.key]
			&& (workspace.key !== "reports" || reportKeys.some((key) => sections.reports?.reports?.[key]?.can_read))
	))
}
