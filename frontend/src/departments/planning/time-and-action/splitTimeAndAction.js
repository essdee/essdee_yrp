/** Split T&A: copy an In Progress Lot T&A to other Lots; the source continues. */
export function splitConfirmMessage(timeAndAction, lots) {
	const count = lots.length
	return `Create ${count} Lot ${count === 1 ? "T&A" : "T&As"} (${lots.join(", ")}) as copies of ${timeAndAction}: rows, dependencies, work stations, dates, actual dates and reasons. ${timeAndAction} continues and each Lot is updated on its own.`
}

/** Search results with the selected lots kept first, so their chips stay labelled. */
export function mergeLotOptions(previous, found, selected) {
	const kept = selected.map((name) => previous.find((lot) => lot.name === name) || { name })
	return [...kept, ...found.filter((lot) => !selected.includes(lot.name))]
}
