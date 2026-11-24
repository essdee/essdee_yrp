import { csvText, plural } from "./dashboardFormat.js"

export const NO_WORK_ORDER = "No Work Order yet"
export const PO_CREATED = "PO Created"
export const LADDER_TONE = {
	[PO_CREATED]: "amber", "Yarn / Fabric Received": "blue",
	"Fabric not received": "amber", "Waiting for cutting": "amber", "In cutting": "amber",
	"Waiting for sewing": "blue", "In sewing": "blue", "Ready for packing": "blue",
	"Packing in progress": "amber", Dispatched: "green",
}
export const SUMMED_FIELDS = ["qty", "cut", "stitch", "packed", "dispatch", "balance"]
export const DASHBOARD_FILTERS = ["ppo", "lot", "item", "product_category", "status"]

const sum = (rows, pick) => rows.reduce((total, row) => total + (Number(pick(row)) || 0), 0)
const isOpen = (row) => row.status !== "Dispatched"
/** Display order: ladder bottom to top by the server's `status_rank`, No Work Order yet last. */
const displayRank = (status, rank) => (status === NO_WORK_ORDER ? Infinity : rank ?? 0)

/** Pill tone; statuses outside the ladder are fabric process names. */
export function statusTone(status) {
	return LADDER_TONE[status] || (status === NO_WORK_ORDER ? "neutral" : "process")
}

/** `{ status, status_rank, pieces }` a lot counts under: its status, plus its PO Created share while still on PO. */
export function rowBuckets(row) {
	const pieces = row.has_work_order ? row.total : row.qty
	const own = { status: row.status, status_rank: row.status_rank, pieces }
	const split = row.purchase_split
	return split ? [split, { ...own, pieces: Math.max((Number(pieces) || 0) - split.pieces, 0) }] : [own]
}

const rowStatuses = (row) => rowBuckets(row).map((bucket) => bucket.status)

/** Distinct statuses of `rows` in display order; a status ranks by its lowest row. */
export function orderStatuses(rows) {
	const ranks = new Map()
	rows.flatMap(rowBuckets).forEach(({ status, status_rank }) => ranks.set(status, Math.min(ranks.get(status) ?? Infinity, status_rank ?? 0)))
	return [...ranks.keys()].sort((a, b) => displayRank(a, ranks.get(a)) - displayRank(b, ranks.get(b)) || a.localeCompare(b))
}

export function emptyDashboardFilters() {
	return { ppo: [], lot: [], item: [], product_category: [], status: [] }
}

export function hasDashboardFilter(filters) {
	return DASHBOARD_FILTERS.some((kind) => filters[kind]?.length)
}

/** Rows matching every filter except `except`, so each filter's options narrow to the others. */
export function filterDashboardRows(rows, filters, except = null) {
	const values = (kind, row) => (kind === "status" ? rowStatuses(row) : [row[kind]])
	const keep = (kind, row) => kind === except || !filters[kind]?.length || values(kind, row).some((value) => filters[kind].includes(value))
	return rows.filter((row) => DASHBOARD_FILTERS.every((kind) => keep(kind, row)))
}

/** `{ value, hint }` options of one filter from the rows matching the other filters. */
export function dashboardOptions(rows, filters, kind, ppos = {}) {
	const matching = filterDashboardRows(rows, filters, kind)
	if (kind === "lot") return matching.map((row) => ({ value: row.lot, hint: row.item || "" }))
	const counts = new Map()
	matching.flatMap((row) => (kind === "status" ? rowStatuses(row) : [row[kind]])).filter(Boolean).forEach((value) => counts.set(value, (counts.get(value) || 0) + 1))
	const statuses = kind === "status" ? orderStatuses(matching) : null
	const entries = [...counts.entries()].sort((a, b) => (statuses ? statuses.indexOf(a[0]) - statuses.indexOf(b[0]) : String(a[0]).localeCompare(String(b[0]), undefined, { numeric: true })))
	if (kind === "ppo") return entries.map(([value, count]) => ({ value, hint: `${ppos[value]?.item_name || ppos[value]?.item || ""} · ${plural(count, "lot")}` }))
	return entries.map(([value, count]) => ({ value, hint: plural(count, "lot") }))
}

/** Cut, Dispatched, Moved and Balance summed over `rows`; Balance is split into lots with and without Cut. */
export function quantityTotals(rows, cutField = "cut") {
	const cutLots = rows.filter((row) => Number(row[cutField]) > 0)
	const uncut = rows.filter((row) => !(Number(row[cutField]) > 0))
	return {
		cut: sum(rows, (row) => row[cutField]),
		dispatched: sum(rows, (row) => row.dispatch),
		moved: sum(rows, (row) => row.to_alternative),
		balance: sum(rows, (row) => row.balance),
		cutLots: cutLots.length,
		cutDispatched: sum(cutLots, (row) => row.dispatch),
		cutMoved: sum(cutLots, (row) => row.to_alternative),
		uncutLots: uncut.length,
		uncutDispatched: sum(uncut, (row) => Number(row.dispatch || 0) + Number(row.to_alternative || 0)),
	}
}

/** PPO pieces once per PPO in `names`; PPOs with no single pieces per box are listed, not counted. */
export function ppoQuantityTotals(names, ppos = {}) {
	const known = names.map((name) => ({ name, ...(ppos[name] || {}) }))
	const missing = known.filter((ppo) => !ppo.pieces)
	return {
		ppoPieces: sum(known, (ppo) => ppo.pieces),
		withoutPieces: missing.map((ppo) => ({ name: ppo.name, boxes: Number(ppo.boxes) || 0 })),
	}
}

/** Tile figures over exactly the rows the table shows (the rows matching the filters). */
export function dashboardTotals(data, filters) {
	const rows = filterDashboardRows(data.lots || [], filters)
	const lots = rows.filter((row) => row.has_work_order)
	const open = lots.filter(isOpen)
	const ppoNames = [...new Set(rows.map((row) => row.ppo))]
	return {
		rows, lots, open, ppoNames,
		allPpoCount: Object.keys(data.ppos || {}).length,
		ppoCount: ppoNames.length,
		ppoWithWorkOrders: new Set(lots.map((row) => row.ppo)).size,
		...ppoQuantityTotals(ppoNames, data.ppos),
		lotQty: sum(rows, (row) => row.qty),
		...quantityTotals(rows),
		late: open.filter((row) => row.delivery && row.delivery < data.as_of),
		notStarted: rows.filter((row) => !row.has_work_order),
	}
}

/** One card per status present: lot count and Σ total pcs (Lot pcs for lots with no Work Order); a lot still on PO adds its PO Created share. */
export function statusCards(rows) {
	const buckets = rows.flatMap(rowBuckets)
	return orderStatuses(rows).map((status) => {
		const matching = buckets.filter((bucket) => bucket.status === status)
		return { status, isNoWorkOrder: status === NO_WORK_ORDER, count: matching.length, pieces: sum(matching, (bucket) => bucket.pieces) }
	})
}

export function ppoQuantityValue(ppo = {}) {
	return ppo.pieces ?? ppo.boxes ?? 0
}

function furthestBehind(lots) {
	const open = lots.filter(isOpen)
	if (!open.length) return lots[0]
	return open.reduce((behind, row) => ((row.status_rank ?? 0) < (behind.status_rank ?? 0) ? row : behind))
}

/** One row per PPO from the filtered lots: quantities summed, PPO Qty once, status = furthest-behind open lot. */
export function groupDashboardRows(rows) {
	const groups = new Map()
	rows.forEach((row) => groups.set(row.ppo, [...(groups.get(row.ppo) || []), row]))
	return [...groups.entries()].map(([ppo, lots]) => {
		const items = [...new Set(lots.map((row) => row.item))]
		const categories = [...new Set(lots.map((row) => row.product_category).filter(Boolean))]
		const mix = {}
		lots.flatMap(rowStatuses).forEach((name) => { mix[name] = (mix[name] || 0) + 1 })
		const { status, status_rank } = furthestBehind(lots)
		const sums = Object.fromEntries([...SUMMED_FIELDS, "to_alternative"].map((field) => [field, sum(lots, (row) => row[field])]))
		return {
			ppo, isGroup: true, lots, items, mix, status, status_rank, ...sums,
			lot: lots.map((row) => row.lot).join(", "),
			lotCount: lots.length,
			item: items.length === 1 ? items[0] : `${items.length} items`,
			product_category: categories.length > 1 ? `${categories.length} categories` : categories[0] || null,
			otherStatuses: Object.keys(mix).length - 1,
			has_work_order: status !== NO_WORK_ORDER,
			breakdown: orderStatuses(lots).map((name) => `${name}: ${mix[name]}`).join("\n"),
		}
	})
}

const SORT_VALUES = {
	ppo: (row) => row.ppo,
	lot: (row) => row.lotCount ?? row.lot,
	item: (row) => row.item,
	product_category: (row) => row.product_category,
	status: (row) => displayRank(row.status, row.status_rank),
	ppoQty: (row, ppos) => ppoQuantityValue(ppos[row.ppo]),
	qty: (row) => row.qty,
	cut: (row) => row.cut,
	stitch: (row) => row.stitch,
	packed: (row) => row.packed,
	dispatch: (row) => row.dispatch,
	balance: (row) => row.balance,
}

function compareValues(first, second) {
	if (typeof first === "number" && typeof second === "number") return first - second
	return String(first ?? "").localeCompare(String(second ?? ""), undefined, { numeric: true })
}

/** Sort by one column (`direction` 1 or -1), then PPO, then Lot. */
export function sortDashboardRows(rows, sort, ppos = {}) {
	const value = SORT_VALUES[sort.key] || SORT_VALUES.ppo
	return [...rows].sort((a, b) => compareValues(value(a, ppos), value(b, ppos)) * sort.direction
		|| compareValues(a.ppo, b.ppo) || compareValues(a.lot, b.lot))
}

export function dashboardCsv(rows, grouped, ppos = {}) {
	const header = ["#", "PPO", grouped ? "Lots" : "Lot", "Item", "Product Category", "Status", "PPO Qty", "PPO Qty unit", "Lot Qty", "Cut Qty", "Stitching Qty", "Packed Qty", "Dispatched Qty", "Moved to alternative", "Balance"]
	const lines = rows.map((row, index) => [
		index + 1, row.ppo, row.lot, row.item, row.product_category || "", row.status, ppoQuantityValue(ppos[row.ppo]), ppos[row.ppo]?.pieces ? "pcs" : "box",
		row.qty, row.cut, row.stitch, row.packed, row.dispatch, row.to_alternative || 0, row.balance,
	])
	return csvText([header, ...lines])
}

const lotNames = (rows) => rows.map((row) => row.lot)

/** PPO Tracking filters a Dashboard tile opens with. */
export function tileDrill(key, totals) {
	const drills = {
		ppos: { ppo: totals.ppoNames },
		lots: { lot: lotNames(totals.open) },
		ppoQty: { ppo: totals.ppoNames },
		cut: { lot: lotNames(totals.lots.filter((row) => row.cut)), dispatched: true },
		dispatched: { lot: lotNames(totals.lots.filter((row) => row.dispatch)), dispatched: true },
		balance: { lot: lotNames(totals.lots.filter((row) => row.balance)), dispatched: true },
		late: { lot: lotNames(totals.late) },
	}
	const drill = drills[key] || {}
	return { ppo: drill.ppo || [], lot: drill.lot || [], dispatched: Boolean(drill.dispatched) }
}

/** PPO Tracking filters of a PPO link (`withLot` false) or Lot link in the table. */
export function rowDrill(row, withLot) {
	return { ppo: [row.ppo], lot: withLot ? [row.lot] : [], dispatched: row.status === "Dispatched" }
}
