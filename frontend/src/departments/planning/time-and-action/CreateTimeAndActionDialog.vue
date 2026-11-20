<template>
	<Dialog :visible="visible" modal header="Create Time and Action" :closable="!busy" :breakpoints="{ '640px': '95vw' }" :style="{ width: 'min(980px, calc(100vw - 32px))' }" @update:visible="emit('update:visible', $event)" @show="reset">
		<div class="ta-create">
			<p class="ta-create__info"><b>{{ againstLabel(against) }}</b> {{ againstId }} · <b>Item</b> {{ item || "" }} · <b>Qty</b> {{ qty || 0 }}</p>
			<div class="ta-create__fields">
				<LinkField v-model="master" doctype="SD YRP Action Master" label="Action Master" required :filters="MASTER_FILTERS" :allow-create="false" :show-open-button="false" />
				<DateField v-model="startDate" label="Start Date *" input-id="ta-create-start-date" />
			</div>
			<Message v-if="error" severity="error" :closable="false" role="alert">{{ error }}</Message>
			<section v-if="preview" class="ta-create__preview" aria-label="Time and Action Preview">
				<p class="ta-create__info"><b>Master</b> {{ preview.master }} · <b>Start Date</b> {{ formatDisplayDate(preview.startDate, "") }} · <b>Dispatch Date</b> {{ formatDisplayDate(preview.rows.at(-1)?.date, "") }}</p>
				<div class="erp-table-wrap ta-create__scroll" role="region" tabindex="0" aria-label="Time and Action Preview">
					<table class="erp-data-table">
						<thead><tr><th class="erp-number">#</th><th>Action</th><th>Department</th><th class="erp-number">Lead Time</th><th>Completion Date</th><th class="ta-create__station">Work Station</th><th class="ta-create__suppliers">Planned Suppliers</th></tr></thead>
						<tbody>
							<tr v-for="(row, index) in preview.rows" :key="row.action">
								<td class="erp-number ta-create__index">{{ index + 1 }}</td>
								<td class="ta-create__action">{{ row.action }}</td>
								<td>{{ row.department }}</td>
								<td class="erp-number">{{ row.lead_time }}</td>
								<td>{{ formatDisplayDate(row.date, "") }}</td>
								<td>
									<LinkField v-if="row.default_work_station" v-model="workStations[row.action]" doctype="YRP Work Station" :filters="{ action: row.action }" :aria-label="`Work Station of ${row.action}`" :allow-create="false" :show-open-button="false" />
									<span v-else class="ta-create__subtle">—</span>
								</td>
								<td>
									<LinkMultiSelectField v-model="plannedSuppliers[row.action]" doctype="Supplier" :aria-label="`Planned Suppliers of ${row.action}`" placeholder="None" :max-selected-labels="2" display="chip" />
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>
			<p v-else-if="previewing" class="ta-create__info ta-create__subtle">Loading the schedule…</p>
			<p v-else class="ta-create__info ta-create__subtle">Pick an Action Master and a Start Date to preview the schedule.</p>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" outlined :disabled="busy" @click="emit('update:visible', false)" />
			<Button label="Create" icon="pi pi-check" :loading="busy" :disabled="previewing || !preview" @click="create" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import { ref, watch } from "vue"

import { createTimeAndAction, getSchedulePreview } from "../../../api/timeAndAction.js"
import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import LinkMultiSelectField from "../../../components/common/LinkMultiSelectField.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { withoutEmptySuppliers } from "./supplierChips.js"
import { againstLabel } from "./timeAndAction.js"

/** Create T&A for a Lot or Production Order: Action Master and Start Date preview the schedule, Work Stations and Planned Suppliers stay editable, then Create. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	against: { type: String, default: "SD YRP Lot" },
	againstId: { type: String, required: true },
	item: { type: String, default: "" },
	qty: { type: [Number, String], default: 0 },
})
const emit = defineEmits(["update:visible", "created"])
const MASTER_FILTERS = { disable: 0, docstatus: 1 }
const master = ref("")
const startDate = ref("")
const preview = ref(null)
const workStations = ref({})
const plannedSuppliers = ref({})
const error = ref("")
const previewing = ref(false)
const busy = ref(false)

function reset() {
	master.value = ""
	startDate.value = ""
	preview.value = null
	workStations.value = {}
	plannedSuppliers.value = {}
	error.value = ""
}

watch([master, startDate], () => {
	preview.value = null
	workStations.value = {}
	if (master.value && startDate.value) loadPreview()
})

async function loadPreview() {
	const requested = `${master.value}|${startDate.value}`
	previewing.value = true
	error.value = ""
	try {
		const rows = await getSchedulePreview(master.value, startDate.value)
		if (requested !== `${master.value}|${startDate.value}`) return
		const chosen = workStations.value
		preview.value = { master: master.value, startDate: startDate.value, rows: rows.map((row) => ({ ...row, default_work_station: row.work_station })) }
		workStations.value = Object.fromEntries(rows.filter((row) => row.work_station).map((row) => [row.action, chosen[row.action] || row.work_station]))
	} catch (reason) {
		error.value = reason?.message || "Unable to preview this Action Master."
	} finally {
		previewing.value = false
	}
}

async function create() {
	busy.value = true
	error.value = ""
	try {
		const chosen = Object.fromEntries(Object.entries(workStations.value).filter(([, value]) => value))
		const name = await createTimeAndAction(props.against, props.againstId, master.value, startDate.value, chosen, withoutEmptySuppliers(plannedSuppliers.value, preview.value.rows.map((row) => row.action)))
		emit("created", name)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason?.message || "Unable to create the Time and Action."
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.ta-create { display: grid; min-width: 0; gap: var(--erp-space-3); }
.ta-create__info { margin: 0; }
.ta-create__fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--erp-space-3); }
.ta-create__preview { display: grid; min-width: 0; gap: var(--erp-space-2); }
.ta-create__scroll { max-height: 55vh; overflow: auto; }
.ta-create__scroll td { padding-top: 7px; padding-bottom: 7px; }
.ta-create__action { font-weight: 600; color: var(--erp-text) !important; }
.ta-create__index, .ta-create__subtle { color: var(--erp-text-subtle) !important; }
.ta-create__station { width: 220px; }
.ta-create__suppliers { width: 260px; }
@media (max-width: 640px) {
	.ta-create__fields { grid-template-columns: minmax(0, 1fr); }
	.ta-create__station { width: 160px; }
	.ta-create__suppliers { width: 200px; }
}
</style>
