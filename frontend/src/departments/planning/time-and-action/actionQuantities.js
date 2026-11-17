/** Hover pop-up of a process action: colour × size cut / delivered / received, shaped for the Lot page's `sizeTable()`. */
export const QUANTITY_LABELS = { planned: "Cut" }

/** Cutting has no delivered pieces (fabric goes out), so it shows cut and received only. */
export function quantityLines(isCutting) {
	return isCutting ? ["planned", "received", "difference"] : ["planned", "delivered", "received", "difference"]
}

/** One grid row per colour and set part; cut is the planned line. */
export function quantityGrid(rows = []) {
	const groups = new Map()
	for (const row of rows) {
		const key = `${row.colour}\u0000${row.part}`
		if (!groups.has(key)) groups.set(key, { colour: row.colour, part: row.part, planned: {}, delivered: {}, received: {} })
		const group = groups.get(key)
		group.planned[row.size] = (group.planned[row.size] || 0) + Number(row.cut || 0)
		group.delivered[row.size] = (group.delivered[row.size] || 0) + Number(row.delivered || 0)
		group.received[row.size] = (group.received[row.size] || 0) + Number(row.received || 0)
	}
	return [...groups.values()]
}

/** IPD sizes that have a row, in IPD order, so the pop-up stays narrow. */
export function usedSizes(sizes = [], rows = []) {
	const used = new Set(rows.map((row) => row.size))
	return sizes.filter((size) => used.has(size))
}

export function percentOfCut(value) {
	return value === null || value === undefined ? "" : `${value}% of cut`
}
