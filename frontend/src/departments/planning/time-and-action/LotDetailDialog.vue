<template>
	<Dialog :visible="visible" modal dismissable-mask :draggable="false" :header="`Lot Detail · ${againstId}`" class="erp-dialog--xl ta-lot-detail" @update:visible="emit('update:visible', $event)" @show="load">
		<Skeleton v-if="loading" height="220px" />
		<Message v-else-if="error" severity="error" :closable="false" role="alert">{{ error }}</Message>
		<template v-else-if="data">
			<p v-if="!data.lots.length" class="ta-lot-detail__empty" data-lot-detail-empty>{{ emptyText }}</p>
			<Tabs v-else v-model:value="activeLot" scrollable class="erp-tabs">
				<TabList v-if="data.lots.length > 1">
					<Tab v-for="row in data.lots" :key="row.lot" :value="row.lot">{{ row.lot }}</Tab>
				</TabList>
				<TabPanels>
					<TabPanel v-for="row in data.lots" :key="row.lot" :value="row.lot">
						<div class="ta-lot-detail__lot" :data-lot-detail="row.lot">
							<router-link class="pd-link" :to="departmentLotLocation(route.path, row.lot)">{{ row.lot }}</router-link>
							<LotStatusPill :status="row.status" />
							<span>{{ row.item }} · PPO {{ row.ppo }} · Delivery {{ formatDisplayDate(row.delivery, "—") }} · Dispatched {{ formatQuantity(row.dispatch) }} pcs</span>
						</div>
						<TrackingLotDetail :row="row" :reports="reports" />
					</TabPanel>
				</TabPanels>
			</Tabs>
			<p v-if="notStarted.length" class="ta-lot-detail__note" data-lot-detail-not-started>No Work Order yet: {{ notStarted.join(", ") }}</p>
		</template>
	</Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, ref } from "vue"
import { useRoute } from "vue-router"

import { getPlanningCapabilities, getPpoTracking } from "../../../api/planning.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import LotStatusPill from "../dashboard/LotStatusPill.vue"
import TrackingLotDetail from "../dashboard/TrackingLotDetail.vue"
import { formatQuantity } from "../dashboard/dashboardFormat.js"
import { visibleProductionReports } from "../planningViews.js"
import { departmentLotLocation, getLotDetailScope } from "./timeAndAction.js"
import "../../../styles/lotProcessFlow.css"
import "../dashboard/planningDashboard.css"

/** PPO Tracking lot detail of a T&A's Lot, or of every Lot of its Production Order, one tab per lot. */
const props = defineProps({
	visible: Boolean,
	against: { type: String, required: true },
	againstId: { type: String, required: true },
})
const emit = defineEmits(["update:visible"])
const route = useRoute()
const data = ref(null)
const reports = ref([])
const activeLot = ref("")
const loading = ref(false)
const error = ref("")
let sequence = 0

const scope = computed(() => getLotDetailScope(props.against, props.againstId))
const notStarted = computed(() => Object.values(data.value?.ppos || {})
	.flatMap((ppo) => ppo.lots || [])
	.filter((row) => !row.has_work_order && (!scope.value.lots.length || scope.value.lots.includes(row.lot)))
	.map((row) => row.lot))
const emptyText = computed(() => (notStarted.value.length ? "No lot has a Work Order yet, so there is no production to show." : "No lots found."))

async function load() {
	const request = ++sequence
	loading.value = true
	error.value = ""
	try {
		const [result, capabilities] = await Promise.all([getPpoTracking(scope.value.ppos, scope.value.lots), reports.value.length ? null : getPlanningCapabilities().catch(() => null)])
		if (request !== sequence) return
		data.value = result
		activeLot.value = result.lots.some((row) => row.lot === activeLot.value) ? activeLot.value : result.lots[0]?.lot || ""
		if (capabilities) reports.value = visibleProductionReports(capabilities.sections?.reports?.production || {})
	} catch (reason) {
		if (request === sequence) error.value = reason?.message || "Unable to load the lot detail."
	} finally {
		if (request === sequence) loading.value = false
	}
}
</script>

<style>
.ta-lot-detail .pd-drill { margin-left: 0; padding: 8px 0 0; border-left: 0; }
.ta-lot-detail__lot { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding-top: 12px; color: var(--erp-text-muted); font-size: 13px; }
.ta-lot-detail__lot .pd-link { font-weight: 700; }
.ta-lot-detail__empty, .ta-lot-detail__note { margin: 12px 0 0; color: var(--erp-text-muted); font-size: 13px; }
@media (max-width: 767px) {
	.ta-lot-detail.p-dialog { width: 100vw; max-width: 100vw; max-height: 100dvh; margin: 0; border-radius: 0; }
}
</style>
