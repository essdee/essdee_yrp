<template>
	<div class="lvt">
		<section class="lvt-panel lvt-bar" aria-label="Valuation status">
			<div class="lvt-bar__text">
				<strong>Valuation rate build-up</strong>
				<span v-if="running" class="lvt-muted" role="status"><i class="pi pi-spin pi-spinner" /> Calculating… this walks every receipt, transfer and adjustment behind the lot.</span>
				<span v-else-if="computedAt" class="lvt-muted">Last calculated {{ computedAt }}<template v-if="state?.duration"> · took {{ state.duration }} s</template></span>
				<span v-else-if="!loading" class="lvt-muted">Not calculated yet. Nothing is computed until you click Calculate.</span>
			</div>
			<Button
				:label="result ? 'Recalculate' : 'Calculate'"
				:icon="running ? 'pi pi-spin pi-spinner' : 'pi pi-calculator'"
				:disabled="running || loading"
				:severity="result ? 'secondary' : undefined"
				@click="calculate"
			/>
		</section>
		<p v-if="loading" class="lot-edit-hint" role="status">Loading last result…</p>
		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<Message v-if="state?.status === 'Failed'" severity="error" :closable="false">
			The last calculation failed{{ result ? "; showing the previous result" : "" }}. {{ lastErrorLine }}
		</Message>
		<div v-if="running && !result" class="lvt-panel lvt-skeleton" aria-hidden="true"><span /><span /><span /></div>
		<template v-if="result">
			<Message v-if="pendingCount" severity="warn" :closable="false">
				{{ pendingCount }} receipt{{ pendingCount === 1 ? " has" : "s have" }} a pending valuation adjustment; values will change when it is applied.
			</Message>
			<Message v-if="!result.root_is_packing" severity="secondary" :closable="false">
				No packing receipts yet: the valuation starts at the {{ result.root_stage }} receipts.
			</Message>
			<ValuationSummary :summary="result.summary" :root-label="`${result.root_stage} receipts`" :boxes="boxes" />
			<Message v-if="!hasRateSections(result)" severity="warn" :closable="false">
				This result was calculated before the per-process rate build-up existed. Click Recalculate to see it.
			</Message>
			<template v-else>
				<p class="lvt-panel lvt-read">
					<span><b>How to read:</b> for every process, each item's <b>Rate in</b> (the rate it arrived with, per kg / panel / piece of that item) <b>+ Process cost + Accessories + PI adjustment + WO close = Rate out</b>, and that Rate out is the Rate in of the next process.</span>
					{{ howToRead(result) }}
				</p>
				<Message v-if="result.rate_sections.has_unattributed" severity="warn" :closable="false">
					Part of this value cannot be traced to a purchase or process (lineage missing, pending or unexplained); it is shown in the + Unattributed column.
				</Message>
				<template v-for="(section, index) in result.rate_sections.sections" :key="section.id">
					<div v-if="index" class="lvt-arrow" aria-hidden="true">↓</div>
					<ValuationSection :section="section" :index="index + 1" :columns="columns" />
				</template>
				<section class="lvt-panel lvt-recon" aria-label="Reconciliation">
					<span>{{ rootSection.title }} total <b>{{ formatMoney(check.total) }}</b></span>
					<span>Stock ledger value of the {{ result.root_stage }} receipts ({{ rootGrns }}) <b>{{ formatMoney(check.ledger) }}</b></span>
					<span :class="check.ok ? 'lvt-ok' : 'lvt-bad'">Difference {{ formatMoney(Math.abs(check.difference)) }}</span>
					<span v-if="!isZero(check.unattributed)" class="lvt-bad">Unattributed {{ formatMoney(check.unattributed) }}</span>
					<span v-if="!isZero(check.unexplained)" class="lvt-bad">Unexplained {{ formatMoney(check.unexplained) }}</span>
				</section>
			</template>
		</template>
		<ValuationHoverCard />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { computed } from "vue"

import { addColumns, computedAtLabel, formatMoney, hasRateSections, howToRead, isRunning, isZero, packedBoxes, rateReconciliation, shortDoc } from "./lotValuation.js"
import { provideValuationHover } from "./valuationHover.js"
import { useLotValuation } from "./useLotValuation.js"
import ValuationHoverCard from "./ValuationHoverCard.vue"
import ValuationSection from "./ValuationSection.vue"
import ValuationSummary from "./ValuationSummary.vue"
import "./valuation.css"

const props = defineProps({ lot: { type: String, required: true } })

provideValuationHover()
const { state, loading, error, calculate } = useLotValuation(() => props.lot)
const result = computed(() => state.value?.result || null)
const running = computed(() => isRunning(state.value?.status))
const computedAt = computed(() => computedAtLabel(state.value))
const lastErrorLine = computed(() => (state.value?.error || "").trim().split("\n").pop())
const pendingCount = computed(() => result.value?.summary?.checks?.pending_adjustments || 0)
const boxes = computed(() => (hasRateSections(result.value) ? packedBoxes(result.value.rate_sections) : null))
const columns = computed(() => addColumns(result.value?.rate_sections))
const rootSection = computed(() => result.value.rate_sections.sections.at(-1))
const check = computed(() => rateReconciliation(result.value))
const rootGrns = computed(() => {
	const grns = (result.value?.roots || []).map((root) => shortDoc(root.grn))
	return grns.length > 3 ? `${grns.slice(0, 3).join(", ")} +${grns.length - 3} more` : grns.join(", ")
})
</script>
