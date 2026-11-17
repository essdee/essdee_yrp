import { useToast } from "primevue/usetoast"
import { computed, ref, toValue } from "vue"

import { trackPointer } from "../../reports/columnLayoutController.js"
import { isConfigurable, lastSizedIndex, resizedWidths, widthDraft } from "./childGridColumns.js"

const INPUT_PADDING = 40
const TEXT_PADDING = 12

/**
 * Header-border resize for a child grid, after the report column handles: widths follow the pointer live,
 * the last sized column gives or takes the difference, and the layout saves as percentages on release.
 */
export function useColumnResize({ columns, widths, minimums, save, enabled, toast = useToast() }) {
	const liveWidths = ref(null)
	const lastIndex = computed(() => lastSizedIndex(toValue(columns)))

	function isResizable(index) {
		return Boolean(toValue(enabled)) && index < lastIndex.value && isConfigurable(toValue(columns)[index])
	}

	function resizeTo(startWidths, index, width) {
		return resizedWidths(startWidths, { index, last: lastIndex.value, width, minimums: toValue(minimums) })
	}

	function start(event, index) {
		if (event.button !== 0 || !isResizable(index)) return
		event.preventDefault()
		event.stopPropagation()
		const startWidths = [...toValue(widths)]
		const startX = event.clientX
		let width = startWidths[index]
		let frame = 0
		const apply = () => { frame = 0; liveWidths.value = resizeTo(startWidths, index, width) }
		const onMove = (moveEvent) => {
			width = startWidths[index] + moveEvent.clientX - startX
			frame ||= requestAnimationFrame(apply)
		}
		trackPointer(event, event.currentTarget, "is-column-resizing", onMove, () => {
			if (frame) cancelAnimationFrame(frame)
			commit(resizeTo(startWidths, index, width), startWidths)
		})
	}

	/** Double-click: the column takes the width of its widest header or cell text. */
	function fit(event, index) {
		if (!isResizable(index)) return
		const header = event.currentTarget.closest("th")
		const startWidths = [...toValue(widths)]
		commit(resizeTo(startWidths, index, columnContentWidth(header, toValue(columns)[index].label)), startWidths)
	}

	async function commit(next, previous) {
		if (next.every((width, index) => width === previous[index])) {
			liveWidths.value = null
			return
		}
		liveWidths.value = next
		try {
			await save(widthDraft(toValue(columns), next))
		} catch (reason) {
			toast.add({ severity: "error", summary: "Column width not saved", detail: reason.message, life: 5000 })
		} finally {
			liveWidths.value = null
		}
	}

	return { liveWidths, isResizable, start, fit }
}

function columnContentWidth(header, label) {
	const table = header.closest("table")
	const context = document.createElement("canvas").getContext("2d")
	const headerStyle = getComputedStyle(header)
	const headerText = headerStyle.textTransform === "uppercase" ? String(label ?? "").toUpperCase() : String(label ?? "")
	let widest = textWidth(context, headerStyle, headerText) + horizontalPadding(headerStyle) + TEXT_PADDING
	for (const row of table.rows) {
		const cell = row.cells[header.cellIndex]
		if (!cell || cell === header || cell.colSpan > 1) continue
		widest = Math.max(widest, cellContentWidth(context, cell))
	}
	return Math.ceil(widest)
}

function cellContentWidth(context, cell) {
	const style = getComputedStyle(cell)
	const inputs = [...cell.querySelectorAll("input:not([type=checkbox]), textarea")]
	const texts = inputs.length ? inputs.map((input) => input.value || input.placeholder || "") : [cell.textContent.trim()]
	const padding = horizontalPadding(style) + (inputs.length ? INPUT_PADDING : TEXT_PADDING)
	return Math.max(...texts.map((text) => textWidth(context, inputs[0] ? getComputedStyle(inputs[0]) : style, text))) + padding
}

function textWidth(context, style, text) {
	context.font = style.font || `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
	return context.measureText(text).width
}

function horizontalPadding(style) {
	return (Number.parseFloat(style.paddingLeft) || 0) + (Number.parseFloat(style.paddingRight) || 0)
}
