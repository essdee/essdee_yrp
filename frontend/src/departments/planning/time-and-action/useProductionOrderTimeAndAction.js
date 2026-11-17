import { ref, toValue, watch } from "vue"

import { getLotTimeAndAction, getProductionOrderTimeAndAction } from "../../../api/timeAndAction.js"

/** Loads a T&A context (Create T&A facts, the T&A name) with `fetch(name)` while `enabled` is true. */
export function useTimeAndActionContext(fetch, name, enabled = true) {
	const context = ref(null)
	const loading = ref(false)
	const error = ref("")
	let sequence = 0

	async function load() {
		const requested = toValue(name)
		const current = ++sequence
		if (!toValue(enabled) || !requested) return
		loading.value = true
		error.value = ""
		try {
			const payload = await fetch(requested)
			if (current === sequence) context.value = payload
		} catch (reason) {
			if (current === sequence) error.value = reason?.message || "Unable to load the Time and Action."
		} finally {
			if (current === sequence) loading.value = false
		}
	}

	watch(() => [toValue(name), toValue(enabled)], () => {
		context.value = null
		error.value = ""
		load()
	}, { immediate: true })

	return { context, loading, error, load }
}

export function useProductionOrderTimeAndAction(productionOrder, enabled) {
	return useTimeAndActionContext(getProductionOrderTimeAndAction, productionOrder, enabled)
}

export function useLotTimeAndAction(lot) {
	return useTimeAndActionContext(getLotTimeAndAction, lot)
}
