import { nextTick, provide, reactive, ref } from "vue"

const GAP = 8

/** Shared hover-card state for the Valuation tab: `show(target, content)` positions it beside the target. */
export function provideValuationHover() {
	const content = ref(null)
	const card = ref(null)
	const position = reactive({ top: 0, left: 0 })

	async function show(target, next) {
		content.value = next
		await nextTick()
		const anchor = target.getBoundingClientRect()
		const width = card.value?.offsetWidth || 320
		const height = card.value?.offsetHeight || 160
		const below = anchor.bottom + GAP + height <= window.innerHeight
		position.top = Math.max(GAP, below ? anchor.bottom + GAP : anchor.top - GAP - height)
		position.left = Math.min(Math.max(GAP, anchor.left), window.innerWidth - width - GAP)
	}

	function hide() {
		content.value = null
	}

	const hover = { content, card, position, show, hide }
	provide("valuationHover", hover)
	return hover
}

/** Event handlers that open `build()`'s content on hover or keyboard focus. */
export function hoverHandlers(hover, build) {
	const open = (event) => hover.show(event.currentTarget, build())
	return { mouseenter: open, focus: open, mouseleave: hover.hide, blur: hover.hide }
}
