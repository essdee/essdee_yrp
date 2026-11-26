import { onBeforeUnmount, ref, toValue, watch } from "vue"

import { enqueueLotValuation, getLotValuation } from "../../../../api/merch.js"
import { isRunning } from "./lotValuation.js"

const POLL_MS = 2000

/** Cached valuation of a Lot: reads the last result, computes only on `calculate()`, polls while the job runs. */
export function useLotValuation(lot) {
	const state = ref(null)
	const loading = ref(false)
	const error = ref("")
	let timer = null
	let sequence = 0

	function stopPolling() {
		clearTimeout(timer)
		timer = null
	}

	async function track(request, promise) {
		try {
			const result = await promise
			if (request !== sequence) return
			state.value = result
			error.value = ""
			if (isRunning(result.status)) timer = setTimeout(() => poll(request), POLL_MS)
		} catch (reason) {
			if (request === sequence) error.value = reason?.message || "Unable to load the valuation."
		} finally {
			if (request === sequence) loading.value = false
		}
	}

	function poll(request) {
		if (request === sequence) track(request, getLotValuation(toValue(lot)))
	}

	function load() {
		stopPolling()
		const request = ++sequence
		loading.value = true
		state.value = null
		error.value = ""
		return track(request, getLotValuation(toValue(lot)))
	}

	function calculate() {
		stopPolling()
		const request = ++sequence
		error.value = ""
		state.value = { ...(state.value || {}), status: "Queued" }
		return track(request, enqueueLotValuation(toValue(lot)))
	}

	watch(() => toValue(lot), load, { immediate: true })
	onBeforeUnmount(() => {
		++sequence
		stopPolling()
	})

	return { state, loading, error, calculate, reload: load }
}
