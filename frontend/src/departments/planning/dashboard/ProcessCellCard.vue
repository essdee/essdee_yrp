<template>
	<Popover ref="popover" class="pd-cell-popover" :dismissable="false">
		<div v-if="row" ref="card" class="pd-cell-card" role="dialog" :aria-label="`${row.lot} ${process} Work Orders`" @mouseenter="cancelHide" @mouseleave="scheduleHide">
			<header class="pd-cell-card__head">
				<strong>{{ row.lot }} · {{ process }}</strong>
				<span v-if="cell" class="pd-status" :class="`pd-status--${CELL_TONES[cell.status] || 'neutral'}`">{{ cell.status }}</span>
			</header>
			<p v-if="note" class="pd-cell-card__note">{{ note }}</p>
			<template v-for="step in cell?.steps || []" :key="step.name">
				<p v-if="step.name !== process" class="pd-cell-card__note">Through {{ step.name }} Work Orders</p>
				<ProcessWorkOrders :step="step" :work-orders="step.work_orders" compact />
				<AlternativeTransfers :transfers="step.alternatives || []" />
			</template>
			<footer class="pd-cell-card__foot">
				<span class="pd-cell-card__note">{{ cell?.steps?.length ? "Click the cell for the size-wise detail." : "" }}</span>
				<LotFlowReports v-if="reportContext && reports.length" :reports="reports" :context="reportContext" />
			</footer>
		</div>
	</Popover>
</template>

<script setup>
import Popover from "primevue/popover"
import { computed, nextTick, onBeforeUnmount, ref } from "vue"

import AlternativeTransfers from "./AlternativeTransfers.vue"
import ProcessWorkOrders from "./ProcessWorkOrders.vue"
import LotFlowReports from "../lot/flow/LotFlowReports.vue"
import { CELL_TONES, cellNote, cellReportContext } from "./processStatusRows.js"

/** One shared hover card for Process Status cells: the cell's Work Orders with delivered, received and pending, and its Lot page reports. */
const props = defineProps({ reports: { type: Array, default: () => [] } })
const popover = ref(null)
const card = ref(null)
const row = ref(null)
const process = ref("")
const cell = computed(() => row.value?.cells[process.value])
const note = computed(() => (row.value ? cellNote(cell.value) : ""))
const reportContext = computed(() => (row.value ? cellReportContext(row.value, process.value, cell.value) : null))
let showTimer = null
let hideTimer = null

function cancelHide() {
	clearTimeout(hideTimer)
}

function scheduleHide() {
	clearTimeout(showTimer)
	cancelHide()
	hideTimer = setTimeout(hideUnlessReportsOpen, 150)
}

/** The Reports list lives in its own overlay; the card waits for it to close so the list is not torn down. */
function hideUnlessReportsOpen() {
	if (card.value?.querySelector(".pf-toggle[aria-expanded='true']")) {
		hideTimer = setTimeout(hideUnlessReportsOpen, 150)
		return
	}
	popover.value?.hide()
}

function hide() {
	clearTimeout(showTimer)
	cancelHide()
	popover.value?.hide()
}

/** Open the card at `target` after a short hover, re-anchoring when it is already open on another cell. */
function show(target, lotRow, processName) {
	cancelHide()
	clearTimeout(showTimer)
	showTimer = setTimeout(async () => {
		const isMoving = row.value && (row.value.lot !== lotRow.lot || process.value !== processName)
		row.value = lotRow
		process.value = processName
		if (isMoving) {
			popover.value?.hide()
			await nextTick()
		}
		popover.value?.show({ currentTarget: target }, target)
	}, 200)
}

onBeforeUnmount(() => {
	clearTimeout(showTimer)
	cancelHide()
})

defineExpose({ show, scheduleHide, hide })
</script>

<style>
.pd-cell-popover { max-width: min(94vw, 760px); }
.pd-cell-card { display: grid; gap: 8px; min-width: 260px; max-height: 60vh; overflow: auto; color: var(--erp-text); }
.pd-cell-card__head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.pd-cell-card__note { margin: 0; color: var(--erp-text-muted); font-size: 12px; }
.pd-cell-card .pf-table { font-size: 12px; }
.pd-cell-card .pf-table th, .pd-cell-card .pf-table td { padding: 5px 8px; }
.pd-cell-card .pf-table td:nth-child(2) { max-width: 170px; white-space: normal; }
.pd-cell-card__foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
</style>
