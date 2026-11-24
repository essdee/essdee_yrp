import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

export const ROW_CHUNK = 60

/** The first `count` rows and whether more are waiting. */
export function windowRows(rows, count) {
	return { rows: rows.slice(0, count), hasMore: rows.length > count }
}

/** Renders `rows` in chunks: the next chunk loads when the sentinel row nears the bottom of its scroll container. */
export function useRowWindow(rows, chunk = ROW_CHUNK) {
	const count = ref(chunk)
	const sentinel = ref(null)
	const shown = computed(() => windowRows(rows.value, count.value))
	let observer = null
	let root = null

	function loadMore(entries) {
		if (!entries.some((entry) => entry.isIntersecting)) return
		count.value += chunk
		const element = sentinel.value
		observer.unobserve(element)
		nextTick(() => sentinel.value && observer?.observe(sentinel.value))
	}

	watch(rows, () => {
		count.value = chunk
		root?.scrollTo?.({ top: 0 })
	})
	watch(sentinel, (element) => {
		observer?.disconnect()
		observer = null
		if (!element || typeof IntersectionObserver === "undefined") return
		root = element.closest(".pd-table-wrap")
		observer = new IntersectionObserver(loadMore, { root, rootMargin: "600px 0px" })
		observer.observe(element)
	})
	onBeforeUnmount(() => observer?.disconnect())
	return { shown, sentinel }
}
