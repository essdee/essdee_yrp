/** Work Order Correction popup: Item picker config and row checks. */
export function correctionItemEditor(allowedItems = []) {
	const item_filters = { disabled: 0, variant_of: ["is", "not set"] }
	if (allowedItems.length) item_filters.name = ["in", [...allowedItems]]
	return { dimensions: [], item_filters }
}

export function hasCorrectionRows(groups) {
	return (groups || []).some((group) => (group.items || []).some((row) => Object.values(row.values || {}).some((value) => Number(value?.qty) > 0)))
}
