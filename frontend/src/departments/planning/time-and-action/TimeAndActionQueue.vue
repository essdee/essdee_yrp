<template>
	<aside class="ta-queue" aria-label="Open T&A Queue">
		<header class="ta-queue__head">
			<h2>Open T&A Queue</h2>
			<span class="ta-queue__count">{{ countLabel }}</span>
		</header>
		<div class="ta-queue__filters">
			<LinkField v-model="lot" doctype="SD YRP Lot" label="Lot" :show-open-button="false" show-clear />
			<LinkField v-model="item" doctype="Item" label="Item" :show-open-button="false" show-clear />
		</div>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="emit('retry')" />
		<div v-else-if="rows.length" class="ta-queue__list" role="listbox" aria-label="Open Time and Actions">
			<button v-for="row in rows" :key="row.name" type="button" role="option" class="ta-card" :class="{ 'is-selected': row.name === selected }" :aria-selected="row.name === selected" @click="emit('select', row.name)">
				<span class="ta-card__top">
					<strong class="ta-card__against">{{ againstShortLabel(row.against) }} {{ row.against_id }}</strong>
					<span class="ta-card__delay" :class="`ta-card__delay--${getRunningDelay(row.delay).tone === 'late' ? 'late' : 'ok'}`">{{ getRunningDelay(row.delay).text }}</span>
				</span>
				<span class="ta-card__item">{{ row.item }}</span>
				<span class="ta-card__meta">
					<span class="ta-card__name">{{ row.name }}</span>
					<b>{{ row.dated }} of {{ row.total }} dated</b>
				</span>
			</button>
		</div>
		<div v-else-if="!loading" class="ta-queue__empty"><i class="pi pi-calendar-clock" aria-hidden="true" />No open Time and Action matches the Lot and Item filters.</div>
	</aside>
</template>

<script setup>
import { computed } from "vue"

import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import { againstShortLabel, getRunningDelay } from "./timeAndAction.js"

/** Master list of the Update page: Lot and Item filters and one card per open T&A. */
const props = defineProps({
	rows: { type: Array, required: true },
	selected: { type: String, default: "" },
	loading: { type: Boolean, default: false },
	loadError: { type: String, default: "" },
})
const emit = defineEmits(["select", "retry"])
const lot = defineModel("lot", { type: String, default: "" })
const item = defineModel("item", { type: String, default: "" })

const countLabel = computed(() => (props.loading && !props.rows.length ? "Loading…" : `${props.rows.length} open`))
</script>

<style scoped>
.ta-queue { display: grid; align-content: start; min-width: 0; gap: var(--erp-space-3); padding: 14px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-lg); }
.ta-queue__head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.ta-queue__head h2 { margin: 0; font-size: var(--erp-font-size-body); font-weight: 700; }
.ta-queue__count { padding: 2px 9px; color: var(--erp-surface); font-size: var(--erp-font-size-caption); font-weight: 700; background: var(--erp-text); border-radius: 999px; }
.ta-queue__filters { display: grid; gap: var(--erp-space-2); }
.ta-queue__list { display: grid; gap: 8px; overflow-y: auto; max-height: calc(100vh - 290px); margin: 0 -4px; padding: 0 4px 2px; }
.ta-queue__empty { display: flex; gap: 8px; color: var(--erp-text-muted); font-size: 13px; }
.ta-card { display: grid; gap: 4px; width: 100%; padding: 11px 12px; color: var(--erp-text); font: inherit; text-align: left; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); cursor: pointer; }
.ta-card:hover { background: var(--erp-surface-soft); border-color: var(--erp-border-strong); }
.ta-card:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 1px; }
.ta-card.is-selected { background: var(--erp-accent-soft); border-color: var(--erp-accent); box-shadow: inset 3px 0 0 var(--erp-accent); }
.ta-card__top, .ta-card__meta { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.ta-card__top strong { min-width: 0; font-size: 14px; overflow-wrap: anywhere; }
.ta-card__delay { padding: 1px 8px; font-size: var(--erp-font-size-min); font-weight: 700; white-space: nowrap; border-radius: 999px; }
.ta-card__delay--late { color: var(--erp-danger); background: var(--erp-danger-soft); }
.ta-card__delay--ok { color: var(--erp-success-text); background: var(--erp-success-soft); }
.ta-card__item { overflow: hidden; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: 600; white-space: nowrap; text-overflow: ellipsis; }
.ta-card__meta { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.ta-card__meta b { color: var(--erp-text-secondary); font-weight: 600; white-space: nowrap; }
@media (max-width: 1023px) { .ta-queue__list { max-height: 300px; } }
</style>
