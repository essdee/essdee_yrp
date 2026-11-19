/** Split T&A: copy an In Progress Lot T&A to other Lots; the source continues. */
export function getDatedActions(rows) {
	return rows.filter((row) => row.actual_date)
}

/** Tick or untick one action's actual date; dated dependents follow an untick, dated dependencies follow a tick. */
export function setActualCopied(rows, copied, action, checked) {
	const dated = getDatedActions(rows)
	const dependsOn = Object.fromEntries(dated.map((row) => [row.action, Object.keys(row.depends_on || {})]))
	const linked = (name) => checked ? dependsOn[name] : Object.keys(dependsOn).filter((other) => dependsOn[other].includes(name))
	const changed = new Set()
	const queue = [action]
	while (queue.length) {
		const name = queue.shift()
		if (changed.has(name) || !(name in dependsOn)) continue
		changed.add(name)
		queue.push(...linked(name))
	}
	const next = new Set(copied)
	changed.forEach((name) => (checked ? next.add(name) : next.delete(name)))
	const actions = Object.keys(dependsOn)
	const also = actions.filter((name) => name !== action && changed.has(name) && copied.includes(name) !== checked)
	return { copied: actions.filter((name) => next.has(name)), also }
}

/** Short note on the actions a tick or untick changed too. */
export function splitCopyNote(action, checked, also) {
	const names = also.join(", ")
	return checked ? `Also ticked ${names}: ${action} depends on ${also.length === 1 ? "it" : "them"}.` : `Also unticked ${names}: ${also.length === 1 ? "it depends" : "they depend"} on ${action}.`
}

/** Search results with the selected lots kept first, so their chips stay labelled. */
export function mergeLotOptions(previous, found, selected) {
	const kept = selected.map((name) => previous.find((lot) => lot.name === name) || { name })
	return [...kept, ...found.filter((lot) => !selected.includes(lot.name))]
}
