import { formatQuantity, plural } from "./dashboardFormat.js"

const pcs = (value) => `${formatQuantity(value)} pcs`
const names = (list, detail) => list.map((entry) => `${entry.name} (${detail(entry)})`).join(", ")

/** Hover line naming set lots, which count complete sets. */
function setLine(totals) {
	return totals.setLots ? [`${plural(totals.setLots, "set-item lot")} counted in sets (1 set = 1 piece; parts never added).`] : []
}

/** PPO Qty, Lot Qty and Not Planned tiles over the table's lots; `count` is how many PPOs they cover. */
export function planTiles(totals, count) {
	const ppoLines = [`Each lot carries its share of the PPO, split by the boxes it took; summed over the ${plural(count, "PPO")} in the table.`]
	if (totals.inferred.length) ppoLines.push(`Not by Packing Combo: ${names(totals.inferred, (ppo) => `${formatQuantity(ppo.boxes, ppo.boxes % 1 !== 0)} → ${formatQuantity(ppo.pieces)} pcs, ${ppo.conversion}`)}.`)
	if (totals.withoutPieces.length) ppoLines.push(`Counted 0, no pieces per box on their lots: ${names(totals.withoutPieces, (ppo) => `${formatQuantity(ppo.boxes, ppo.boxes % 1 !== 0)} boxes`)}.`)
	const notPlannedLines = [`Covers only the ${plural(count, "PPO")} listed in the table, each floored at 0.`]
	if (totals.overPlanned.length) notPlannedLines.push(`Lot Qty above PPO Qty: ${names(totals.overPlanned, (ppo) => `+${pcs(ppo.over)}`)}.`)
	return [
		{
			key: "ppoQty", label: "PPO Qty", value: formatQuantity(totals.ppoQty),
			foot: totals.withoutPieces.length ? `pcs · ${plural(totals.withoutPieces.length, "PPO")} with no pcs per box` : `pcs · ${plural(count, "PPO")}`,
			help: { formula: "PPO Qty = PPO boxes × pieces per box", lines: [...ppoLines, ...setLine(totals)] },
		},
		{
			key: "lotQty", label: "Lot Qty", value: formatQuantity(totals.lotQty), foot: `pcs · ${plural(totals.rows.length, "lot")}`,
			help: { formula: "Lot Qty = Σ Lot Qty of the lots in the table", lines: ["Pieces ordered on each lot.", ...setLine(totals)] },
		},
		{
			key: "notPlanned", label: "Not Planned", value: formatQuantity(totals.notPlanned), foot: "pcs · PPO Qty − Lot Qty",
			help: { formula: "Not Planned = PPO Qty − Lot Qty, per PPO", lines: notPlannedLines },
		},
	]
}

/** Cut, Dispatched and Balance tiles; `count` is the number of lots the figures add up. */
export function quantityTiles(totals, count) {
	const dispatched = totals.dispatched + totals.moved
	return [
		{
			key: "cut", label: "Cut", value: formatQuantity(totals.cut), foot: `pcs received from Cutting WOs · ${plural(count, "lot")}`,
			help: { formula: "Cut = Σ Cut Qty of the lots in the table", lines: ["Pieces received from Cutting Work Orders.", ...(totals.setLots ? ["A set counts once all its parts are cut: the fewest of its parts per colour and size."] : [])] },
		},
		{
			key: "dispatched", label: "Dispatched", value: formatQuantity(dispatched), foot: totals.moved ? `pcs · incl. ${pcs(totals.moved)} moved to alternative` : `pcs · ${plural(count, "lot")}`,
			help: { formula: "Dispatched = dispatched + moved to alternative", lines: [`= ${pcs(totals.dispatched)} dispatched + ${pcs(totals.moved)} moved to alternative lots.`, ...setLine(totals)] },
		},
		{
			key: "balance", label: "Balance", value: formatQuantity(totals.balance), foot: "pcs · PPO Qty − Dispatched",
			help: {
				formula: "Balance = PPO Qty − Dispatched",
				lines: [`= ${pcs(totals.ppoQty)} − ${pcs(dispatched)} (moved to alternative counts as dispatched).`, "Same as the sum of the table's Balance column."],
			},
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
		...planTiles(totals, totals.ppoCount),
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
		...planTiles(summary, summary.ppoCount),
		...quantityTiles(summary, summary.rows.length),
	]
}
