<template>
	<section class="ppo-lot-tab" :aria-label="`Lot ${lot}`">
		<header class="ppo-lot-tab__header">
			<div class="ppo-lot-tab__title"><h2>Lot · {{ lot }}</h2><DocumentStatusBadge v-if="context.name" :label="context.status || 'Open'" /></div>
			<RouterLink class="ppo-lot-tab__open" :to="{ name: PLANNING_ROUTES.lot, params: { lotId: lot } }">
				<i class="pi pi-external-link" aria-hidden="true" /> Open Planning Lot
			</RouterLink>
		</header>
		<div v-if="loading" class="ppo-lot-tab__state" role="status">Loading Lot {{ lot }}…</div>
		<Message v-else-if="error" severity="warn" :closable="false">{{ error }}</Message>
		<LotProcessFlow v-else-if="context.name" :lot="context.name" :item="context.item || ''" :fabrics="context.fabrics || []" />
	</section>
</template>

<script setup>
import Message from "primevue/message"
import { onBeforeUnmount, ref, watch } from "vue"

import { getLotFlowContext } from "../../api/planning.js"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import LotProcessFlow from "../planning/lot/flow/LotProcessFlow.vue"
import { PLANNING_ROUTES } from "../planning/planningViews.js"
import { lotTabErrorMessage } from "./productionOrderLotTabs.js"

/** Planning Lot process flow for one Lot linked to a Production Order. */
const props = defineProps({ lot: { type: String, required: true } })
const context = ref({})
const loading = ref(false)
const error = ref("")
let loadSequence = 0
onBeforeUnmount(() => { loadSequence += 1 })

async function load() {
	const sequence = ++loadSequence
	const requested = props.lot
	loading.value = true
	error.value = ""
	context.value = {}
	try {
		const payload = await getLotFlowContext(requested) || {}
		if (sequence === loadSequence) context.value = payload
	} catch (reason) {
		if (sequence === loadSequence) error.value = lotTabErrorMessage(reason, requested)
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}
watch(() => props.lot, load, { immediate: true })
</script>

<style scoped>
.ppo-lot-tab { display: grid; min-width: 0; gap: 12px; }
.ppo-lot-tab__header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
.ppo-lot-tab__title { display: flex; min-width: 0; align-items: center; gap: 10px; }
.ppo-lot-tab__title h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-md); font-weight: 600; overflow-wrap: anywhere; }
.ppo-lot-tab__open { display: inline-flex; align-items: center; gap: 6px; color: var(--erp-accent); font-size: var(--erp-font-size-table); font-weight: 600; text-decoration: none; }
.ppo-lot-tab__open:hover { text-decoration: underline; }
.ppo-lot-tab__open:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
.ppo-lot-tab__state { padding: 16px 13px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
</style>
