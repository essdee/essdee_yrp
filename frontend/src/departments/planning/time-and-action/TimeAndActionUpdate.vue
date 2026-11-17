<template>
	<DepartmentPage title="Time and Action Update" back-to="/planning" back-label="Planning" flat full-width inline-navigation>
		<section class="ta-update erp-workspace" aria-label="Time and Action Update">
			<TimeAndActionQueue v-model:lot="filters.lot" v-model:item="filters.item" :rows="rows" :selected="selected" :loading="loading" :load-error="loadError" @select="select" @retry="load" />
			<TimeAndActionEditor v-if="selected" :key="selected" :name="selected" @dirty="dirty = $event" @saved="load" @completed="completed" />
			<div v-else-if="!loading" class="erp-empty-state ta-update__empty">
				<div><i class="pi pi-calendar-clock" /><strong>Select a Time and Action</strong><span>Pick one from the queue to update its actual dates.</span></div>
			</div>
		</section>
		<DocumentConfirmationDialog v-model:visible="discardVisible" :title="`Discard changes to ${selected}?`" :message="discardMessage" confirm-label="Discard changes" cancel-label="Keep editing" @confirm="confirmDiscard" />
	</DepartmentPage>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getOpenTimeAndActions } from "../../../api/timeAndAction.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import TimeAndActionEditor from "./TimeAndActionEditor.vue"
import TimeAndActionQueue from "./TimeAndActionQueue.vue"

/** Split master-detail: the open T&A queue on the left, the selected T&A (`?ta=`) in the cockpit on the right. */
const route = useRoute()
const router = useRouter()
const filters = reactive({ lot: route.query.lot || "", item: route.query.item || "" })
const rows = ref([])
const loading = ref(false)
const loadError = ref("")
const selected = ref(route.query.ta || "")
const dirty = ref(0)
const discardVisible = ref(false)
const pendingTarget = ref("")
let sequence = 0

const discardMessage = computed(() => {
	const count = dirty.value
	return `${selected.value} has ${count} unsaved ${count === 1 ? "change" : "changes"}. Opening ${pendingTarget.value} discards ${count === 1 ? "it" : "them"}.`
})

async function load() {
	const current = ++sequence
	loading.value = true
	loadError.value = ""
	try {
		const payload = await getOpenTimeAndActions(filters)
		if (current !== sequence) return
		rows.value = payload || []
		if (!selected.value && rows.value.length) open(rows.value[0].name)
	} catch (reason) {
		if (current === sequence) loadError.value = reason?.message || "Unable to load open Time and Actions."
	} finally {
		if (current === sequence) loading.value = false
	}
}

function open(name) {
	selected.value = name
	dirty.value = 0
	router.replace({ query: { ...route.query, ta: name || undefined } })
}

function select(name) {
	if (name === selected.value) return
	if (dirty.value) {
		pendingTarget.value = name
		discardVisible.value = true
		return
	}
	open(name)
}

function confirmDiscard() {
	discardVisible.value = false
	open(pendingTarget.value)
}

function completed() {
	open("")
	load()
}

watch(() => [filters.lot, filters.item], () => {
	selected.value = ""
	dirty.value = 0
	router.replace({ query: { lot: filters.lot || undefined, item: filters.item || undefined } })
	load()
})
load()
</script>

<style scoped>
.ta-update { display: grid; grid-template-columns: minmax(260px, 300px) minmax(0, 1fr); align-items: start; width: 100%; min-width: 0; gap: var(--erp-space-4); padding: var(--erp-space-2) 0 var(--erp-space-5); }
.ta-update > .ta-queue { position: sticky; top: var(--erp-space-3); }
.ta-update__empty { min-height: 320px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-lg); }
@media (max-width: 1023px) {
	.ta-update { grid-template-columns: minmax(0, 1fr); }
	.ta-update > .ta-queue { position: static; }
}
</style>
