<template>
	<component :is="block ? 'div' : 'span'" ref="trigger" class="ta-qty-trigger" :class="{ 'ta-qty-trigger--block': block }" tabindex="0" aria-haspopup="dialog" :aria-label="`${action}: ${process} quantities by colour and size`" @mouseenter="open" @mouseleave="scheduleHide" @focus="open" @blur="scheduleHide"><slot /></component>
	<Popover ref="popover" class="ta-qty-popover">
		<div class="ta-qty" role="dialog" :aria-label="`${action} quantities`" @mouseenter="cancelHide" @mouseleave="scheduleHide">
			<header class="ta-qty__head"><strong>{{ action }}</strong><span>{{ process }}<template v-if="entry.result?.lot"> · Lot {{ entry.result.lot }}</template></span></header>
			<p v-if="entry.loading" class="ta-qty__note" aria-live="polite"><i class="pi pi-spin pi-spinner" aria-hidden="true" /> Loading…</p>
			<p v-else-if="entry.error" class="ta-qty__note ta-qty__note--error" role="alert">{{ entry.error }}</p>
			<template v-else-if="result">
				<p v-if="!result.lot" class="ta-qty__note">Colour and size quantities are shown on Lot T&amp;As only.</p>
				<p v-else-if="!result.rows.length" class="ta-qty__note">No cut quantity or Work Order for {{ process }} yet.</p>
				<template v-else>
					<div class="pf-stats ta-qty__stats">
						<div class="pf-stat"><span>Cut</span><b>{{ formatNumber(result.totals.cut) }}</b></div>
						<div v-if="!result.is_cutting" class="pf-stat" :class="tone(statusTone(result.totals.delivered, result.totals.cut))"><span>Delivered</span><b>{{ formatNumber(result.totals.delivered) }}</b><i>{{ percentOfCut(result.totals.delivered_percent) }}</i></div>
						<div class="pf-stat" :class="tone(statusTone(result.totals.received, result.totals.cut))"><span>Received</span><b>{{ formatNumber(result.totals.received) }}</b><i>{{ percentOfCut(result.totals.received_percent) }}</i></div>
					</div>
					<LotToneLegend />
					<LotSizeTable :table="table" :sizes="sizes" :title="result.is_cutting ? 'Cut / received by size' : 'Cut / delivered / received by size'" />
				</template>
			</template>
		</div>
	</Popover>
</template>

<script>
import { reactive } from "vue"

const cache = new Map()
let hideOpen = null

/** One entry per T&A action, shared by the table and the stepper. */
function getEntry(timeAndAction, action) {
	const key = `${timeAndAction}\u0000${action}`
	if (!cache.has(key)) cache.set(key, reactive({ result: null, loading: false, error: "" }))
	return cache.get(key)
}
</script>

<script setup>
import Popover from "primevue/popover"
import { computed, onBeforeUnmount, ref } from "vue"

import { getActionProcessQuantities } from "../../../api/timeAndAction.js"
import { formatNumber, sizeTable, statusTone } from "../../../utils/lotProcessFlow.js"
import LotSizeTable from "../lot/flow/LotSizeTable.vue"
import LotToneLegend from "../lot/flow/LotToneLegend.vue"
import { QUANTITY_LABELS, percentOfCut, quantityGrid, quantityLines, usedSizes } from "./actionQuantities.js"
import "../../../styles/lotProcessFlow.css"

/** Hover or focus pop-up of a process action: the Lot page's colour × size table of cut, delivered and received; loaded once per action. */
const props = defineProps({
	timeAndAction: { type: String, required: true },
	action: { type: String, required: true },
	process: { type: String, required: true },
	block: { type: Boolean, default: false },
})
const trigger = ref(null)
const popover = ref(null)
const entry = computed(() => getEntry(props.timeAndAction, props.action))
const result = computed(() => entry.value.result)
let hideTimer = null

const sizes = computed(() => usedSizes(result.value?.sizes, result.value?.rows))
const table = computed(() => sizeTable(quantityGrid(result.value?.rows), sizes.value, quantityLines(result.value?.is_cutting), QUANTITY_LABELS))
const tone = (value) => (value ? `pf-tone-${value}` : "")

function open() {
	cancelHide()
	if (hideOpen && hideOpen !== hide) hideOpen()
	hideOpen = hide
	popover.value?.show({ currentTarget: trigger.value }, trigger.value)
	if (!entry.value.result && !entry.value.loading) load(entry.value)
}

async function load(item) {
	item.loading = true
	item.error = ""
	try {
		item.result = await getActionProcessQuantities(props.timeAndAction, props.action)
	} catch (reason) {
		item.error = reason?.message || "Unable to load the quantities."
	} finally {
		item.loading = false
	}
}

function hide() {
	popover.value?.hide()
}

function scheduleHide() {
	cancelHide()
	hideTimer = setTimeout(hide, 150)
}

function cancelHide() {
	clearTimeout(hideTimer)
}

onBeforeUnmount(cancelHide)
</script>

<style scoped>
.ta-qty-trigger { text-decoration: underline dotted color-mix(in srgb, currentColor 60%, transparent); text-decoration-thickness: 1.5px; text-underline-offset: 3px; cursor: help; border-radius: 3px; }
.ta-qty-trigger--block { display: grid; gap: 3px; min-width: 0; text-decoration: none; cursor: help; }
.ta-qty-trigger:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
</style>

<style>
.ta-qty-popover { max-width: min(94vw, 1000px); }
.ta-qty { display: grid; gap: 10px; min-width: 260px; max-height: 70vh; overflow: auto; color: var(--erp-text); }
.ta-qty__head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
.ta-qty__head span { color: var(--erp-text-muted); font-size: 12px; }
.ta-qty__note { margin: 0; color: var(--erp-text-muted); font-size: 13px; }
.ta-qty__note--error { color: var(--erp-danger); }
.ta-qty .ta-qty__stats { margin-bottom: 0; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
@media (max-width: 640px) {
	.ta-qty-popover { position: fixed !important; inset: auto 8px calc(8px + env(safe-area-inset-bottom)) 8px !important; max-width: none; margin: 0 !important; }
	.ta-qty-popover::before, .ta-qty-popover::after { display: none; }
	.ta-qty { min-width: 0; max-height: 65vh; overflow-x: hidden; }
	.ta-qty > * { min-width: 0; }
	.ta-qty .ta-qty__stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>
