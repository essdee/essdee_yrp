import { csvText, plural } from "./dashboardFormat.js"

export const NO_WORK_ORDER = "No Work Order yet"
export const PO_CREATED = "PO Created"
export const LOT_NOT_LINKED = "Lot not linked"
export const LOTS_CLOSED = "Lots closed, PPO open"
/** Statuses of an Open PPO shown without a lot row, with their status card caption. */
export const PPO_ONLY_CAPTIONS = { [LOT_NOT_LINKED]: "open PPOs with no lot", [LOTS_CLOSED]: "open PPOs whose lots are all closed" }
export const LADDER_TONE = {
	[LOT_NOT_LINKED]: "red", [LOTS_CLOSED]: "red", [PO_CREATED]: "amber", "Yarn / Fabric Received": "blue",
	"Fabric not received": "amber", "Waiting for cutting": "amber", "In cutting": "amber",
	"Waiting for sewing": "blue", "In sewing": "blue", "Ready for packing": "blue",
	"Packing in progress": "amber", Dispatched: "green",
}
export const SUMMED_FIELDS = ["ppo_qty", "qty", "cut", "stitch", "packed", "dispatch", "balance"]
export const DASHBOARD_FILTERS = ["ppo", "lot", "item", "product_category", "status"]

const sum = (rows, pick) => rows.reduce((total, row) => total + (Number(pick(row)) || 0), 0)
const isOpen = (row) => row.status !== "Dispatched"
/** Display order: ladder bottom to top by the server's `status_rank`, No Work Order yet last. */
const displayRank = (status, rank) => (status === NO_WORK_ORDER ? Infinity : rank ?? 0)

/** Pill tone; statuses outside the ladder are fabric process names. */
export function statusTone(status) {
	return LADDER_TONE[status] || (status === NO_WORK_ORDER ? "neutral" : "process")
}

/** `{ status, status_rank, pieces }` a lot counts under (Cut pieces, else Lot Qty): its status, plus its PO Created share while still on PO. */
export function rowBuckets(row) {
	const pieces = Number(row.cut) || Number(row.qty) || 0
	const own = { status: row.status, status_rank: row.status_rank, pieces }
	const split = row.purchase_split
	return split ? [split, { ...own, pieces: Math.max((Number(pieces) || 0) - split.pieces, 0) }] : [own]
}

/** A PPO row without a lot (ungrouped, or a PPO group with no lot rows). */
export const isPpoOnlyRow = (row) => row.status in PPO_ONLY_CAPTIONS && !(row.isGroup ? row.lotCount : row.lot)

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
	if (kind === "lot") return matching.filter((row) => row.lot).map((row) => ({ value: row.lot, hint: row.item || "" }))
	const counts = new Map()
	matching.flatMap((row) => (kind === "status" ? rowStatuses(row) : [row[kind]])).filter(Boolean).forEach((value) => counts.set(value, (counts.get(value) || 0) + 1))
	const statuses = kind === "status" ? orderStatuses(matching) : null
	const entries = [...counts.entries()].sort((a, b) => (statuses ? statuses.indexOf(a[0]) - statuses.indexOf(b[0]) : String(a[0]).localeCompare(String(b[0]), undefined, { numeric: true })))
	if (kind === "ppo") return entries.map(([value]) => ({ value, hint: `${ppos[value]?.item_name || ppos[value]?.item || ""} · ${ppoLotHint(matching, value)}` }))
	return entries.map(([value, count]) => ({ value, hint: plural(count, value in PPO_ONLY_CAPTIONS ? "PPO" : "lot") }))
}

function ppoLotHint(rows, ppo) {
	const count = rows.filter((row) => row.ppo === ppo && row.lot).length
	return count ? plural(count, "lot") : rows.find((row) => row.ppo === ppo)?.status
}

/** {PPO: {ppoQty, lotQty}} of `rows`, each PPO's share summed over its lots in `rows`. */
function byPpo(rows) {
	const groups = new Map()
	rows.forEach((row) => {
		const group = groups.get(row.ppo) || { ppoQty: 0, lotQty: 0 }
		group.ppoQty += Number(row.ppo_qty) || 0
		group.lotQty += Number(row.qty) || 0
		groups.set(row.ppo, group)
	})
	return groups
}

/** Card figures summed over `rows`; Not Planned is PPO Qty − Lot Qty per PPO, floored at 0, with the PPOs over plan listed. */
export function quantityTotals(rows, cutField = "cut") {
	const groups = [...byPpo(rows).entries()]
	return {
		ppoQty: sum(rows, (row) => row.ppo_qty),
		lotQty: sum(rows, (row) => row.qty),
		notPlanned: groups.reduce((total, [, group]) => total + Math.max(group.ppoQty - group.lotQty, 0), 0),
		overPlanned: groups.filter(([, group]) => group.lotQty - group.ppoQty >= 1).map(([name, group]) => ({ name, over: group.lotQty - group.ppoQty })),
		cut: sum(rows, (row) => row[cutField]),
		dispatched: sum(rows, (row) => row.dispatch),
		moved: sum(rows, (row) => row.to_alternative),
		balance: sum(rows, (row) => row.balance),
		setLots: rows.filter((row) => row.is_set).length,
	}
}

/** PPOs among `names` the cards cannot convert to pieces, and those converted other than by their Packing Combo. */
export function ppoConversions(names, ppos = {}) {
	const known = names.map((name) => ({ name, ...(ppos[name] || {}) }))
	return {
		withoutPieces: known.filter((ppo) => ppo.pieces == null).map((ppo) => ({ name: ppo.name, boxes: Number(ppo.boxes) || 0 })),
		inferred: known.filter((ppo) => ppo.pieces != null && ppo.conversion && ppo.conversion !== "packing combo")
			.map((ppo) => ({ name: ppo.name, boxes: Number(ppo.boxes) || 0, pieces: ppo.pieces, conversion: ppo.conversion })),
	}
}

/** Tile figures over the lot rows the table shows; `tableRows` adds the lot-less PPO rows. */
export function dashboardTotals(data, filters) {
	const tableRows = filterDashboardRows(data.lots || [], filters)
	const rows = tableRows.filter((row) => row.lot)
	const lots = rows.filter((row) => row.has_work_order)
	const open = lots.filter(isOpen)
	const ppoNames = [...new Set(rows.map((row) => row.ppo))]
	return {
		tableRows, rows, lots, open, ppoNames,
		allPpoCount: Object.keys(data.ppos || {}).length,
		ppoCount: ppoNames.length,
		ppoWithWorkOrders: new Set(lots.map((row) => row.ppo)).size,
		...ppoConversions(ppoNames, data.ppos),
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
		return { status, isNoWorkOrder: status === NO_WORK_ORDER, ppoCaption: PPO_ONLY_CAPTIONS[status], count: matching.length, pieces: sum(matching, (bucket) => bucket.pieces) }
	})
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
			is_set: lots.some((row) => row.is_set),
			lot: lots.map((row) => row.lot).filter(Boolean).join(", "),
			closed_lots: lots.map((row) => row.closed_lots).filter(Boolean).join(", ") || null,
			lotCount: lots.filter((row) => row.lot).length,
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
	ppo_qty: (row) => row.ppo_qty,
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
	const header = ["#", "PPO", grouped ? "Lots" : "Lot", "Item", "Product Category", "Status", "PPO Qty", "Lot Qty", "Cut Qty", "Stitching Qty", "Packed Qty", "Dispatched Qty", "Moved to alternative", "Balance"]
	const lines = rows.map((row, index) => [
		index + 1, row.ppo, row.lot || row.closed_lots || "", row.item, row.product_category || "", row.status, row.ppo_qty,
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
		lotQty: { ppo: totals.ppoNames },
		notPlanned: { ppo: totals.ppoNames },
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
