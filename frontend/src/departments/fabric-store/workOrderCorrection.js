/** Work Order Correction popup: Item picker config and row checks. */
export function correctionItemEditor() {
	return { dimensions: [], item_filters: { disabled: 0, variant_of: ["is", "not set"] } }
}

export function hasCorrectionRows(groups) {
	return (groups || []).some((group) => (group.items || []).some((row) => Object.values(row.values || {}).some((value) => Number(value?.qty) > 0)))
}
