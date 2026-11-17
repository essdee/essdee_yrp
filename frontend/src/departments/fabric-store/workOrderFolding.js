/** Folding Lot Work Orders: manual rows, no Item or Production Detail selection. */
export const FOLDING_ROW_EDITOR = Object.freeze({ dimensions: [], item_filters: { disabled: 0, variant_of: ["is", "not set"] } })

const FOLDING_DERIVED_FIELDS = new Set(["item", "production_detail"])

export function workOrderRequiredFields(fieldnames, isFolding) {
	return isFolding ? fieldnames.filter((fieldname) => !FOLDING_DERIVED_FIELDS.has(fieldname)) : fieldnames
}

export function isFoldingContext(context) {
	return Boolean(Number(context?.is_folding_lot || 0))
}
