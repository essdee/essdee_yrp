import { ref, toValue, watch } from "vue"

import { getProductionOrderTimeAndAction } from "../../../api/timeAndAction.js"

/** Loads a Production Order's T&A context (Create T&A, report, Convert) while `enabled` is true. */
export function useProductionOrderTimeAndAction(productionOrder, enabled) {
	const context = ref(null)
	const loading = ref(false)
	const error = ref("")
	let sequence = 0

	async function load() {
		const name = toValue(productionOrder)
		const current = ++sequence
		if (!toValue(enabled) || !name) return
		loading.value = true
		error.value = ""
		try {
			const payload = await getProductionOrderTimeAndAction(name)
			if (current === sequence) context.value = payload
		} catch (reason) {
			if (current === sequence) error.value = reason?.message || "Unable to load the Time and Action."
		} finally {
			if (current === sequence) loading.value = false
		}
	}

	watch(() => [toValue(productionOrder), toValue(enabled)], () => {
		context.value = null
		error.value = ""
		load()
	}, { immediate: true })

	return { context, loading, error, load }
}
