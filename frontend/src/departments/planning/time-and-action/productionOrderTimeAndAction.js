/** Production Order T&A: a Frozen one has been converted to Lot T&As and is read-only. */
export function isFrozen(context) {
	return context?.status === "Frozen"
}

export function lotOptionLabel(lot) {
	return [lot.name, lot.item, `Qty ${Number(lot.qty) || 0}`].filter(Boolean).join(" · ")
}

export function convertConfirmMessage(timeAndAction, lots) {
	const count = lots.length
	return `Create ${count} Lot ${count === 1 ? "T&A" : "T&As"} (${lots.join(", ")}) as copies of ${timeAndAction}: rows, dependencies, work stations, dates, actual dates and reasons. ${timeAndAction} is then frozen and each Lot continues on its own.`
}

/** Toggle `lot` in the selected list, keeping the eligible-lot order. */
export function toggleLot(selected, lot, eligible) {
	const next = new Set(selected)
	if (next.has(lot)) next.delete(lot)
	else next.add(lot)
	return eligible.map((row) => row.name).filter((name) => next.has(name))
}

/** The Production Order header's "Create T&A" action, offered only while the order can get a T&A. */
export function createTimeAndActionActions(context, { busy, onCreate }) {
	if (!context?.can_create) return []
	return [{ key: "create_time_and_action", label: "Create T&A", icon: "pi pi-calendar-plus", disabled: Boolean(busy), command: onCreate }]
}
