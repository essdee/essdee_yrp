import { documentWorkspaces } from "./fabric-store/storeWorkspaces.js"

/** Launcher cards of the departments whose landing page has no views module of its own. */
export const CUTTING_WORKSPACES = [
	{ key: "cutting-plans", label: "Cutting Plans", description: "Plans, markers, lay sheets and production movements.", icon: "pi pi-th-large", to: "/cutting/plans" },
	{ key: "cutting-orders", label: "Cutting Orders", description: "Plan and complete cutting orders with their production details.", icon: "pi pi-file-edit", to: "/cutting/orders" },
	{ key: "bulk-lay-sheets", label: "Bulk LaySheets", description: "Manage multi-lot lay sheets, bundles and dispatch workflows.", icon: "pi pi-clone", to: "/cutting/bulk-lay-sheets" },
	{ key: "lay-sheet-planner", label: "LaySheet Planner", description: "Optimize size quantities into efficient marker and lay plans.", icon: "pi pi-sitemap", to: "/cutting/lay-sheet-planner" },
	{ key: "stock-transfers", label: "Stock Transfers", description: "Stock Update, Stock Reconciliation, Stock Entry and Lot Transfer.", icon: "pi pi-arrow-right-arrow-left", to: "/cutting/stock-transfers" },
	{ key: "reports", label: "Reports", description: "Production, cut sheet, cutting detail and stock reports.", icon: "pi pi-chart-bar", to: "/cutting/reports" },
]

export const CUT_PANEL_STORE_WORKSPACES = [
	{ key: "delivery_challans", label: "Delivery Challans", description: "Review deliveries linked to Cut Panel Movements.", icon: "pi pi-truck", to: "/cut-panel-store/delivery-challans" },
	{ key: "goods_received_notes", label: "Goods Received Notes", description: "Review receipts linked to Cut Panel Movements.", icon: "pi pi-inbox", to: "/cut-panel-store/goods-received-notes" },
	{ key: "movements", label: "Cut Panel Movement", description: "Move bundles and create linked stock documents in one workspace.", icon: "pi pi-arrow-right-arrow-left", to: "/cut-panel-store/movements" },
	{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", to: "/cut-panel-store/work-orders" },
	{ key: "cut_bundle_edits", label: "Cut Bundle Edit", description: "Correct bundle composition using authoritative stock data.", icon: "pi pi-pencil", to: "/cut-panel-store/cut-bundle-edits" },
	{ key: "box_stickers", label: "Box Sticker Print", description: "Prepare, preview and print size-based box labels.", icon: "pi pi-tags", to: "/cut-panel-store/box-sticker-prints" },
	{ key: "excel_stickers", label: "Excel Sticker Print", description: "Upload sticker rows, preview labels and print through QZ.", icon: "pi pi-file-excel", to: "/cut-panel-store/excel-sticker-prints" },
	{ key: "reports", label: "Reports", description: "Review stock and cut bundle balances.", icon: "pi pi-chart-bar", to: "/cut-panel-store/reports" },
]

export const FINISHING_WORKSPACES = [
	{ key: "plans", label: "Finishing Plan", description: "Inward, packing, dispatch, OCR and audit for each lot.", icon: "pi pi-box", to: "/finishing/plans" },
	{ key: "sewing_plans", label: "Sewing Plan", description: "Review plans and production for a Sewing Unit.", icon: "pi pi-sitemap", to: "/finishing/sewing-plans" },
	{ key: "reports", label: "Reports", description: "Packing, dispatch, ironing, rejection, rework and stock reports.", icon: "pi pi-chart-bar", to: "/finishing/reports" },
	{ key: "rework_details", label: "Rework Details", description: "Clear rework pieces into Accepted or Rejected stock per GRN.", icon: "pi pi-replay", to: "/finishing/rework-details" },
	{ key: "dispatches", label: "Finishing Plan Dispatch", description: "Dispatch packed boxes from several Finishing Plans together.", icon: "pi pi-truck", to: "/finishing/dispatches" },
	{ key: "work_orders", label: "Work Orders", description: "Work Orders: make DCs and receive GRNs.", icon: "pi pi-briefcase", to: "/finishing/work-orders" },
	...documentWorkspaces("/finishing"),
]

export const HR_WORKSPACES = [
	{ key: "bill_tracking", label: "Bill Tracking", description: "Track vendor bills from receipt to invoice.", icon: "pi pi-inbox", to: "/hr/bill-tracking" },
	{ key: "reports", label: "Reports", description: "Attendance strength.", icon: "pi pi-chart-bar", to: "/hr/reports" },
]

export const SEWING_WORKSPACES = [
	{ key: "plans", label: "Sewing Plan", description: "Review plans and production for a Sewing Unit.", icon: "pi pi-sitemap", to: "/sewing/plans" },
	{ key: "finishing_plans", label: "Finishing Plan", description: "Inward, packing, dispatch, OCR and audit for each lot.", icon: "pi pi-box", to: "/sewing/finishing-plans" },
	{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", to: "/sewing/work-orders" },
	...documentWorkspaces("/sewing"),
	{ key: "stock_transfers", label: "Stock Transfers", description: "Stock Update, Stock Reconciliation, Stock Entry and Lot Transfer.", icon: "pi pi-arrow-right-arrow-left", to: "/sewing/stock-transfers" },
	{ key: "reports", label: "Reports", description: "Review production reports for a Sewing Unit.", icon: "pi pi-chart-bar", to: "/sewing/reports" },
	{ key: "attendance", label: "Attendance Report", description: "Review worker strength across all Sewing Units.", icon: "pi pi-users", to: "/sewing/attendance" },
]

export const SALES_WORKSPACES = [
	{ key: "production_orders", label: "Production Orders", description: "Plan quantities, prices, delivery dates and approvals in one compact workflow.", icon: "pi pi-file-edit", to: "/sales/production-orders" },
	{ key: "item_prices", label: "Sales Item Price", description: "Update MRP, Distributor and Retail rates per piece for each Item size.", icon: "pi pi-tag", to: "/sales/item-prices" },
	{ key: "reports", label: "Reports", description: "Review Production Orders by delivery period, status, category and size.", icon: "pi pi-chart-bar", to: "/sales/reports" },
]
