/** Update Action dialog rules; the server (`steps.update_actions`) enforces the same ones. */

export function getLastDatedIndex(rows) {
	return rows.findLastIndex((row) => row.actual_date)
}

/** Insert slots: only after the last completed action; the top only when nothing is dated. */
export function getInsertSlots(rows) {
	const lastDated = getLastDatedIndex(rows)
	const slots = lastDated < 0 ? [{ value: null, label: "At the top" }] : []
	rows.forEach((row, index) => {
		if (index < lastDated) return
		slots.push({ value: row.action, label: `After ${row.action}${index === rows.length - 1 ? " (last)" : ""}` })
	})
	return slots
}

export function getRemovableActions(rows) {
	return rows.filter((row) => !row.actual_date).map((row) => row.action)
}

function getSlotIndex(rows, afterAction) {
	return afterAction ? rows.findIndex((row) => row.action === afterAction) + 1 : 0
}

/** A new action may depend on any action above its slot, completed ones included. */
export function getDependsOnOptions(rows, afterAction) {
	return rows.slice(0, getSlotIndex(rows, afterAction)).map((row) => row.action)
}

/** "Must finish before" lists only undated actions below the slot. */
export function getRequiredByOptions(rows, afterAction) {
	return rows.slice(getSlotIndex(rows, afterAction)).filter((row) => !row.actual_date).map((row) => row.action)
}

export function describeAdd(item) {
	const days = Number(item.lead_time) || 0
	let text = `Add ${item.action} (${days} ${days === 1 ? "day" : "days"})`
	if (item.depends_on?.length) text += ` after ${item.depends_on.join(", ")}`
	if (item.required_by?.length) text += `; before ${item.required_by.join(", ")}`
	return text
}

export function describeActionChanges(adds, removes, edits = []) {
	return [...removes.map((action) => `Remove ${action}`), ...adds.map(describeAdd), ...edits.map(describeEdit)]
}

export function describeEdit(edit) {
	return `Change ${edit.action} dependencies → ${edit.depends_on.join(", ") || "none"}`
}

/** Current depends-on list of a serialized row (`depends_on` maps action → actual date). */
export function getDependsOn(row) {
	return Object.keys(row?.depends_on || {})
}

/** An undated action may depend on any action above it. */
export function getEditDependsOnOptions(rows, action) {
	return rows.slice(0, Math.max(rows.findIndex((row) => row.action === action), 0)).map((row) => row.action)
}

/** Upsert the edit for `action`; drop it when it matches the saved list in `originalRows`. */
export function setDependencyEdit(edits, originalRows, action, dependsOn) {
	const others = edits.filter((edit) => edit.action !== action)
	const original = getDependsOn(originalRows.find((row) => row.action === action))
	const isUnchanged = original.length === dependsOn.length && original.every((name) => dependsOn.includes(name))
	return isUnchanged ? others : [...others, { action, depends_on: [...dependsOn] }]
}

/** A removed action leaves the batch's dependency edits, both as the edited action and as a dependency. */
export function pruneEditsForRemove(edits, action) {
	return edits
		.filter((edit) => edit.action !== action)
		.map((edit) => ({ ...edit, depends_on: edit.depends_on.filter((name) => name !== action) }))
}
