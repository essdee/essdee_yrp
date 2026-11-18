<template>
	<div class="tab-stack ccr-tab">
		<div v-if="loading" class="loading-state"><Skeleton v-for="key in 3" :key="key" height="3.25rem" /></div>
		<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
		<template v-else>
			<section class="ccr-card">
				<header class="section-heading"><h3><i class="pi pi-th-large"></i><span>CCR</span></h3><span class="row-count">{{ countLabel(markerGroups.length, "marker") }}</span></header>
				<div class="section-body">
					<div v-for="(group, groupIndex) in markerGroups" :key="groupIndex" class="ccr-block">
						<h4>{{ group.panels }}</h4>
						<div class="table-scroll" role="region" tabindex="0" :aria-label="`CCR ${group.panels}`">
							<table class="data-table matrix-table">
								<thead><tr><th>S.No.</th><th>Colour</th><th>Cloth Type</th><th>Received Weight</th><th>Used Weight</th><th>Balance Weight</th><th v-for="size in group.sizes" :key="size">{{ size }}</th><th>Total</th><th>Piece Weight</th><th>Reqd Weight</th></tr></thead>
								<tbody>
									<tr v-for="(row, index) in group.rows" :key="index">
										<td>{{ index + 1 }}</td><td>{{ row.colour }}</td><td>{{ row.cloth_type }}</td>
										<td class="number-cell">{{ fixed(row.received_weight, 3) }}</td><td class="number-cell">{{ fixed(row.used_weight, 3) }}</td><td class="number-cell">{{ fixed(row.balance_weight, 3) }}</td>
										<td v-for="size in group.sizes" :key="size" class="number-cell">{{ whole(row.sizes?.[size]) }}</td>
										<td class="number-cell strong-cell">{{ whole(row.total_pieces) }}</td><td class="number-cell">{{ fixed(row.piece_weight, 4) }}</td><td class="number-cell">{{ fixed(row.required_weight, 4) }}</td>
									</tr>
									<tr class="total-row">
										<td></td><td>Total</td><td></td>
										<td class="number-cell">{{ fixed(group.totals.received_weight, 3) }}</td><td class="number-cell">{{ fixed(group.totals.used_weight, 3) }}</td><td class="number-cell">{{ fixed(group.totals.balance_weight, 3) }}</td>
										<td v-for="size in group.sizes" :key="size" class="number-cell">{{ whole(group.totals.sizes?.[size]) }}</td>
										<td class="number-cell">{{ whole(group.totals.total_pieces) }}</td><td class="number-cell">{{ fixed(group.totals.piece_weight, 4) }}</td><td class="number-cell">{{ fixed(group.totals.required_weight, 4) }}</td>
									</tr>
								</tbody>
							</table>
						</div>
					</div>
					<div v-if="!markerGroups.length" class="erp-empty-state"><i class="pi pi-inbox"></i><strong>No label-printed lay sheets yet.</strong></div>
				</div>
			</section>

			<CcrTable v-if="data.accessories?.length" title="Accessory Summary" :columns="accessoryColumns" :rows="data.accessories" :total-fields="['used_weight']" />
			<CcrTable v-if="data.print_panels?.length" title="Print Panel Summary" :columns="printPanelColumns" :rows="data.print_panels" :total-fields="['weight', 'no_of_rolls', 'panel_count']" />
			<CcrTable v-if="data.recuts?.length" title="Recut Summary" :columns="recutColumns" :rows="data.recuts" :total-fields="['weight', 'no_of_rolls']" />
			<CcrTable v-for="group in data.cloth_groups || []" :key="group.cloth_type" :title="`Cloth Summary · ${group.cloth_type}`" :columns="clothColumns" :rows="group.rows" :total-fields="['weight', 'used_weight', 'balance_weight']" />

			<section v-for="section in sizeSections" :key="section.key" class="ccr-card">
				<header class="section-heading"><h3><span>{{ section.title }}</span></h3></header>
				<div class="section-body">
					<div v-for="(group, groupIndex) in section.groups" :key="groupIndex" class="table-scroll" role="region" tabindex="0" :aria-label="`${section.title} ${groupIndex + 1}`">
						<table class="data-table matrix-table">
							<thead><tr><th>S.No.</th><th>{{ group.pack_attr }}</th><th v-if="group.set_item_attr">{{ group.set_item_attr }}</th><th v-for="value in group.primary_values" :key="value">{{ value }}</th><th v-if="section.key === 'completed'">Total</th></tr></thead>
							<tbody>
								<tr v-for="(row, index) in group.rows" :key="index">
									<td>{{ index + 1 }}</td><td>{{ row.label }}</td><td v-if="group.set_item_attr">{{ row.set_value }}</td>
									<td v-for="value in group.primary_values" :key="value" class="number-cell">{{ section.key === "completed" ? (positive(row.values?.[value]) || "--") : panelCounts(row.values?.[value]) }}</td>
									<td v-if="section.key === 'completed'" class="number-cell strong-cell">{{ completedRowTotal(row, group.primary_values) }}</td>
								</tr>
								<tr v-if="section.key === 'completed'" class="total-row">
									<td>Total</td><td></td><td v-if="group.set_item_attr"></td>
									<td v-for="value in group.primary_values" :key="value" class="number-cell">{{ completedColumnTotal(group, value) }}</td>
									<td class="number-cell">{{ group.primary_values.reduce((total, value) => total + completedColumnTotal(group, value), 0) }}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</section>
		</template>
	</div>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, defineComponent, h, ref, watch } from "vue"

import { getCuttingPlanCcr } from "../../api/cuttingWorkspaces.js"

const props = defineProps({ cuttingPlan: { type: String, required: true } })

const data = ref({})
const loading = ref(true)
const error = ref("")
let sequence = 0

const markerGroups = computed(() => data.value.marker_groups || [])
const sizeSections = computed(() => [
	{ key: "completed", title: "Completed Pieces", groups: data.value.completed || [] },
	{ key: "excess", title: "Excess Panels", groups: data.value.excess || [] },
].filter((section) => section.groups.length))
const accessoryColumns = [["item", "Cloth"], ["cloth_type", "Cloth Type"], ["colour", "Colour"], ["dia", "Dia"], ["used_weight", "Used Weight", 3]]
const printPanelColumns = [["cloth_type", "Cloth Type"], ["colour", "Colour"], ["dia", "Dia"], ["shade", "Shade"], ["weight", "Weight in Kg's", 3], ["no_of_rolls", "No of Rolls", 0], ["panel_count", "Panel Count", 0]]
const recutColumns = printPanelColumns.slice(0, -1)
const clothColumns = [["item", "Cloth"], ["cloth_type", "Cloth Type"], ["colour", "Colour"], ["dia", "Dia"], ["weight", "Received Weight", 3], ["used_weight", "Used Weight", 3], ["balance_weight", "Balance Weight", 3]]

async function load() {
	const current = ++sequence
	loading.value = true
	error.value = ""
	try {
		const payload = await getCuttingPlanCcr(props.cuttingPlan)
		if (current === sequence) data.value = payload || {}
	} catch (reason) {
		if (current === sequence) error.value = reason?.message || "Unable to load the CCR."
	} finally {
		if (current === sequence) loading.value = false
	}
}

function numeric(value) {
	const number = Number(value || 0)
	return Number.isFinite(number) ? number : 0
}

function fixed(value, precision) {
	return numeric(value).toFixed(precision)
}

function whole(value) {
	return Math.trunc(numeric(value))
}

function positive(value) {
	return numeric(value) > 0 ? numeric(value) : 0
}

function countLabel(count, noun) {
	return `${count} ${noun}${count === 1 ? "" : "s"}`
}

function panelCounts(value) {
	const entries = Object.entries(value || {}).filter(([, count]) => numeric(count) > 0)
	return entries.length ? entries.map(([panel, count]) => `${panel} ${numeric(count)}`).join(", ") : ""
}

function completedRowTotal(row, primaryValues) {
	return primaryValues.reduce((total, value) => total + positive(row.values?.[value]), 0)
}

function completedColumnTotal(group, value) {
	return group.rows.reduce((total, row) => total + positive(row.values?.[value]), 0)
}

watch(() => props.cuttingPlan, load, { immediate: true })

defineExpose({ load })

const CcrTable = defineComponent({
	props: { title: String, columns: Array, rows: Array, totalFields: Array },
	setup(tableProps) {
		const cell = (row, [field, , precision]) => precision === undefined ? (row[field] ?? "") : fixed(row[field], precision)
		const total = (column) => tableProps.totalFields.includes(column[0]) ? fixed(tableProps.rows.reduce((sum, row) => sum + numeric(row[column[0]]), 0), column[2]) : ""
		return () => h("section", { class: "ccr-card" }, [
			h("header", { class: "section-heading" }, [h("h3", [h("span", tableProps.title)]), h("span", { class: "row-count" }, countLabel(tableProps.rows.length, "row"))]),
			h("div", { class: "section-body" }, [h("div", { class: "table-scroll", role: "region", tabindex: 0, "aria-label": tableProps.title }, [h("table", { class: "data-table" }, [
				h("thead", [h("tr", [h("th", "S.No."), ...tableProps.columns.map((column) => h("th", column[1]))])]),
				h("tbody", [
					...tableProps.rows.map((row, index) => h("tr", [h("td", index + 1), ...tableProps.columns.map((column) => h("td", { class: column[2] === undefined ? "" : "number-cell" }, cell(row, column)))])),
					h("tr", { class: "total-row" }, [h("td", "Total"), ...tableProps.columns.map((column) => h("td", { class: "number-cell" }, total(column)))]),
				]),
			])])]),
		])
	},
})
</script>

<style scoped>
.ccr-card {
	overflow: hidden;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-card);
}

.ccr-block {
	display: grid;
	gap: 6px;
}

.ccr-block h4 {
	margin: 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: 700;
}

.ccr-tab {
	display: grid;
	gap: 12px;
}

.loading-state {
	display: grid;
	gap: 10px;
}
</style>
