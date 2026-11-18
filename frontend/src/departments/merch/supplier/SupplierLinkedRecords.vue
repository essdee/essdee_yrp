<template>
	<section class="supplier-linked" aria-label="Address & Contact">
		<div v-for="(config, doctype) in LINKED_RECORDS" :key="doctype" class="supplier-linked__group">
			<header class="supplier-linked__header">
				<h3>{{ config.label }}</h3>
				<Button v-if="canCreateDoctype(doctype)" :label="`New ${config.singular}`" icon="pi pi-plus" size="small" severity="secondary" outlined @click="open(doctype)" />
			</header>
			<div v-if="loading" class="supplier-linked__grid"><Skeleton v-for="index in 2" :key="index" height="6rem" /></div>
			<Message v-else-if="errors[doctype]" severity="warn" :closable="false">{{ errors[doctype] }}</Message>
			<p v-else-if="!records[doctype]?.length" class="supplier-linked__empty">No {{ config.label.toLowerCase() }} linked.</p>
			<div v-else class="supplier-linked__grid">
				<button v-for="row in records[doctype]" :key="row.name" type="button" class="supplier-linked__card" @click="open(doctype, row.name)">
					<span class="supplier-linked__title">{{ config.title(row) }}</span>
					<span v-if="config.badges(row).length" class="supplier-linked__badges">
						<Tag v-for="badge in config.badges(row)" :key="badge" :value="badge" severity="secondary" />
					</span>
					<span v-for="line in config.lines(row)" :key="line" class="supplier-linked__line">{{ line }}</span>
				</button>
			</div>
		</div>
		<Dialog :visible="Boolean(dialog)" modal :header="dialogTitle" class="erp-dialog--lg" @update:visible="close">
			<FormView v-if="dialog" :key="`${dialog.doctype}:${dialog.name}`" :doctype="dialog.doctype" :name="dialog.name" :title="dialogTitle"
				:initial-values="dialog.name ? {} : newLinkedRecordValues(supplier)" :readonly="dialogReadonly" show-cancel compact uniform-grid
				@saved="saved" @cancel="close" />
		</Dialog>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tag from "primevue/tag"
import { computed, ref, watch } from "vue"

import { getList } from "../../../api/frappe.js"
import FormView from "../../../components/common/FormView.vue"
import { useDocumentPermissions } from "../../../composables/useDocumentPermissions.js"
import { canCreateDoctype } from "../../../utils/linkTarget.js"
import { LINKED_RECORDS, linkedRecordFilters, newLinkedRecordValues } from "./supplierViews.js"

/** Addresses and Contacts linked to the Supplier, like the Desk Address & Contact tab; each opens in the shared form. */
const props = defineProps({ supplier: { type: String, required: true } })
const records = ref({})
const errors = ref({})
const loading = ref(true)
const dialog = ref(null)
const permissions = useDocumentPermissions(() => [dialog.value?.doctype || "", dialog.value?.name || "", 0])
const dialogReadonly = computed(() => dialog.value?.name ? !permissions.value?.write : !canCreateDoctype(dialog.value?.doctype))
const dialogTitle = computed(() => dialog.value ? `${dialog.value.name ? "" : "New "}${LINKED_RECORDS[dialog.value.doctype].singular}` : "")
let sequence = 0

async function load() {
	const requested = ++sequence
	const loaded = await Promise.all(Object.entries(LINKED_RECORDS).map(async ([doctype, config]) => {
		try {
			return [doctype, await getList(doctype, { fields: config.fields, filters: linkedRecordFilters(props.supplier), orderBy: config.orderBy, pageLength: 100 }), ""]
		} catch (reason) {
			return [doctype, [], reason?.message || `Unable to load ${config.label}.`]
		}
	}))
	if (requested !== sequence) return
	records.value = Object.fromEntries(loaded.map(([doctype, rows]) => [doctype, rows]))
	errors.value = Object.fromEntries(loaded.map(([doctype, , error]) => [doctype, error]))
	loading.value = false
}

function open(doctype, name = "") {
	dialog.value = { doctype, name }
}

function close(visible = false) {
	if (!visible) dialog.value = null
}

function saved(doc) {
	if (!dialog.value?.name && doc?.name) dialog.value = null
	load()
}

watch(() => props.supplier, () => { loading.value = true; load() }, { immediate: true })
</script>

<style scoped>
.supplier-linked {
	display: grid; gap: var(--erp-space-5, 20px); padding: 16px;
	background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius);
}
.supplier-linked__group { display: grid; gap: var(--erp-space-3, 12px); }
.supplier-linked__header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3, 12px); }
.supplier-linked__header h3 { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-table); font-weight: var(--erp-font-weight-semibold); }
.supplier-linked__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--erp-space-3, 12px); }
.supplier-linked__card {
	display: grid; align-content: start; gap: 4px; padding: 12px 14px; text-align: left; font: inherit; color: var(--erp-text);
	background: var(--erp-surface-subtle, var(--erp-surface)); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); cursor: pointer;
}
.supplier-linked__card:hover, .supplier-linked__card:focus-visible { border-color: var(--erp-border-strong); outline: none; box-shadow: var(--erp-shadow-xs); }
.supplier-linked__title { font-weight: var(--erp-font-weight-semibold); overflow-wrap: anywhere; }
.supplier-linked__badges { display: flex; flex-wrap: wrap; gap: 4px; }
.supplier-linked__line { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); overflow-wrap: anywhere; }
.supplier-linked__empty { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
</style>
