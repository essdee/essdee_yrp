import { formatQuantity, plural } from "./dashboardFormat.js"

const pcs = (value) => `${formatQuantity(value)} pcs`

/** PPO Qty tile: pieces once per PPO; PPOs with no single pieces per box are named, not counted. */
export function ppoQuantityTile(totals) {
	const missing = totals.withoutPieces
	const lines = [
		`Counted once per PPO over the ${plural(totals.ppoCount, "PPO")} in the table, for the whole PPO (all its lots).`,
		`Lot Qty of the lots in the table: ${pcs(totals.lotQty)}.`,
	]
	if (missing.length) {
		const names = missing.map((ppo) => `${ppo.name} (${formatQuantity(ppo.boxes, ppo.boxes % 1 !== 0)} boxes)`).join(", ")
		lines.push(`Not counted, no single pieces per box on their lots: ${names}.`)
	}
	return {
		key: "ppoQty", label: "PPO Qty", value: formatQuantity(totals.ppoPieces),
		foot: missing.length ? `pcs · ${plural(missing.length, "PPO")} not counted (no pcs per box)` : `pcs · ${plural(totals.ppoCount, "PPO")}`,
		help: { formula: "PPO Qty = PPO boxes × pieces per box of its lots", lines },
	}
}

/** Cut, Dispatched and Balance tiles; `count` is the number of lots the figures add up. */
export function quantityTiles(totals, count) {
	const balanceLines = [
		`= ${pcs(totals.cut)} − ${pcs(totals.cutDispatched)} − ${pcs(totals.cutMoved)} over the ${plural(totals.cutLots, "lot")} with Cut.`,
	]
	if (totals.uncutLots) {
		balanceLines.push(`${plural(totals.uncutLots, "lot")} with no Cut yet count 0${totals.uncutDispatched ? `; their ${pcs(totals.uncutDispatched)} dispatched or moved is not subtracted` : ""}.`)
	}
	balanceLines.push("Same as the sum of the table's Balance column.")
	return [
		{
			key: "cut", label: "Cut", value: formatQuantity(totals.cut), foot: `pcs received from Cutting WOs · ${plural(count, "lot")}`,
			help: { formula: "Cut = Σ Cut Qty of the lots in the table", lines: [`Pieces received from Cutting Work Orders in these ${plural(count, "lot")}; ${totals.cutLots} have Cut.`] },
		},
		{
			key: "dispatched", label: "Dispatched", value: formatQuantity(totals.dispatched), foot: `pcs · ${plural(count, "lot")}, dispatched lots included`,
			help: { formula: "Dispatched = Σ Dispatched Qty of the lots in the table", lines: [`Moved to alternative lots is separate: ${pcs(totals.moved)}.`] },
		},
		{
			key: "balance", label: "Balance", value: formatQuantity(totals.balance), foot: "pcs · Cut − Dispatched − Moved to alternative",
			help: { formula: "Balance = Cut − Dispatched − Moved to alternative, per lot", lines: balanceLines },
		},
	]
}

/** Dashboard tiles, every figure over the table's rows. */
export function dashboardTiles(totals) {
	const others = totals.allPpoCount - totals.ppoCount
	const dispatchedLots = totals.lots.length - totals.open.length
	return [
		{
			key: "ppos", label: "Open PPOs", value: formatQuantity(totals.ppoCount), foot: `${formatQuantity(totals.ppoWithWorkOrders)} with Work Orders`,
			help: { formula: "Open PPOs with a lot in the table", lines: others > 0 ? [`${plural(others, "other open PPO")} ${others === 1 ? "has" : "have"} no lot in this view.`] : [] },
		},
		{
			key: "lots", label: "Open lots", value: formatQuantity(totals.open.length), foot: `${formatQuantity(dispatchedLots)} dispatched · ${formatQuantity(totals.notStarted.length)} no WO yet`,
			help: { formula: "Open lots = lots with Work Orders, not Dispatched", lines: [`${formatQuantity(totals.open.length)} open + ${formatQuantity(dispatchedLots)} dispatched + ${formatQuantity(totals.notStarted.length)} with no Work Order = ${plural(totals.rows.length, "lot")} in the table.`] },
		},
		ppoQuantityTile(totals),
		...quantityTiles(totals, totals.rows.length),
		{
			key: "late", label: "Late lots", value: formatQuantity(totals.late.length), foot: "open lots past delivery", alert: totals.late.length > 0,
			help: { formula: "Late = open lots whose PPO delivery date has passed", lines: [] },
		},
	]
}

/** PPO Tracking tiles over the lots the table shows (Process filter and Show dispatched applied). */
export function trackingTiles(summary) {
	const lotFoot = [`${summary.openLots} open`, summary.dispatchedLots ? `${summary.dispatchedLots} dispatched` : "", summary.notStartedLots ? `${summary.notStartedLots} no WO` : ""].filter(Boolean).join(" · ")
	return [
		{
			key: "ppos", label: "PPOs", value: formatQuantity(summary.ppoCount), foot: "with a lot in the table",
			help: { formula: "PPOs with a lot in the table", lines: summary.hiddenDispatched ? [`${plural(summary.hiddenDispatched, "dispatched lot")} hidden; turn on Show dispatched to count them.`] : [] },
		},
		{
			key: "lots", label: "Lots", value: formatQuantity(summary.rows.length), foot: lotFoot,
			help: { formula: "Lots in the table", lines: ["Lots with no Work Order and no yarn / fabric PO are not listed."] },
		},
		ppoQuantityTile(summary),
		...quantityTiles(summary, summary.rows.length),
	]
}
