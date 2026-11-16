<template>
	<Dialog :visible="visible" modal header="Create Time and Action" :closable="!busy" :style="{ width: preview ? 'min(1200px, calc(100vw - 32px))' : 'min(560px, calc(100vw - 32px))' }" @update:visible="emit('update:visible', $event)" @show="reset">
		<div class="ta-create">
			<p class="ta-create__info"><b>Lot</b> {{ lot }} · <b>Item</b> {{ item || "" }} · <b>Qty</b> {{ qty || 0 }}</p>
			<div class="ta-create__fields">
				<LinkField v-model="master" doctype="SD YRP Action Master" label="Action Master" required :filters="MASTER_FILTERS" :allow-create="false" :show-open-button="false" />
				<DateField v-model="startDate" label="Start Date *" input-id="ta-create-start-date" />
			</div>
			<Message v-if="error" severity="error" :closable="false" role="alert">{{ error }}</Message>
			<section v-if="preview" class="ta-create__preview" aria-label="Time and Action Preview">
				<p class="ta-create__info"><b>Master</b> {{ preview.master }} · <b>Start Date</b> {{ formatDisplayDate(preview.startDate, "") }} · <b>Dispatch Date</b> {{ formatDisplayDate(preview.rows.at(-1)?.date, "") }}</p>
				<div class="erp-table-wrap ta-create__scroll" role="region" tabindex="0" aria-label="Time and Action Preview">
					<table class="erp-data-table ta-create__table">
						<thead><tr><th class="ta-create__sticky">Activity</th><th v-for="row in preview.rows" :key="row.action">{{ row.action }}</th></tr></thead>
						<tbody>
							<tr><th class="ta-create__sticky">Lead Time</th><td v-for="row in preview.rows" :key="row.action">{{ row.lead_time }}</td></tr>
							<tr><th class="ta-create__sticky">Department</th><td v-for="row in preview.rows" :key="row.action">{{ row.department }}</td></tr>
							<tr><th class="ta-create__sticky">Completion Date</th><td v-for="row in preview.rows" :key="row.action">{{ formatDisplayDate(row.date, "") }}</td></tr>
							<tr>
								<th class="ta-create__sticky">Work Station</th>
								<td v-for="row in preview.rows" :key="row.action">
									<LinkField v-if="row.default_work_station" v-model="workStations[row.action]" doctype="YRP Work Station" :filters="{ action: row.action }" :aria-label="`Work Station of ${row.action}`" :allow-create="false" :show-open-button="false" />
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>
		</div>
		<template #footer>
			<Button label="Preview" icon="pi pi-eye" severity="secondary" outlined :loading="previewing" :disabled="busy || !master || !startDate" @click="loadPreview" />
			<Button label="Create" icon="pi pi-check" :loading="busy" :disabled="previewing || !master || !startDate" @click="create" />
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
import { formatDisplayDate } from "../../../utils/dateFormat.js"

/** Desk Create T&A dialog for a Lot: Action Master, Start Date, Preview with editable Work Stations, Create. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	lot: { type: String, required: true },
	item: { type: String, default: "" },
	qty: { type: [Number, String], default: 0 },
})
const emit = defineEmits(["update:visible", "created"])
const MASTER_FILTERS = { disable: 0, docstatus: ["!=", 2] }
const master = ref("")
const startDate = ref("")
const preview = ref(null)
const workStations = ref({})
const error = ref("")
const previewing = ref(false)
const busy = ref(false)

function reset() {
	master.value = ""
	startDate.value = ""
	preview.value = null
	workStations.value = {}
	error.value = ""
}

watch([master, startDate], () => { preview.value = null; workStations.value = {} })

async function loadPreview() {
	previewing.value = true
	error.value = ""
	try {
		const rows = await getSchedulePreview(master.value, startDate.value)
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
		const name = await createTimeAndAction(props.lot, master.value, startDate.value, chosen)
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
.ta-create__table th, .ta-create__table td { min-width: 160px; text-align: center; vertical-align: middle; }
.ta-create__table .ta-create__sticky { position: sticky; left: 0; z-index: 1; min-width: 150px; text-align: left; background: var(--erp-surface); }
</style>
