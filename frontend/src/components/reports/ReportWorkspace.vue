<template>
	<div class="report-workspace" :class="{ 'report-workspace--single': !hasList }">
		<div v-if="hasList" class="report-workspace__nav">
			<CollapsibleNavList :items="navItems" :label="label" :selected-key="selected" search-placeholder="Search reports" replace pinned />
		</div>
		<div v-if="hasList" class="report-workspace__mobile common-field">
			<label :for="mobileInputId">Report</label>
			<Select v-model="selected" :input-id="mobileInputId" :options="reports" option-label="label" option-value="value" filter filter-placeholder="Search reports" aria-label="Report" fluid />
		</div>
		<section v-if="current" class="report-workspace__content" :aria-label="current.label">
			<div v-if="$slots.default" :key="current.value"><slot :report="current" /></div>
			<KeepAlive v-else-if="keepAlive"><component :is="current.component" :key="current.value" v-bind="current.props" /></KeepAlive>
			<component :is="current.component" v-else :key="current.value" v-bind="current.props" />
		</section>
	</div>
</template>

<script setup>
import Select from "primevue/select"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { usePageTitle } from "../../composables/usePageTitle.js"
import CollapsibleNavList from "../navigation/CollapsibleNavList.vue"
import { chooseReport, readRememberedReport, rememberReport } from "./reportWorkspace.js"

/** Master-detail report picker: searchable list of report links on the left, selected report on the right, kept in the URL. */
const props = defineProps({
	reports: { type: Array, required: true },
	label: { type: String, default: "Reports" },
	queryKey: { type: String, default: "report" },
	storageKey: { type: String, default: "" },
	keepAlive: { type: Boolean, default: false },
})
const route = useRoute()
const router = useRouter()
const storageId = computed(() => props.storageKey || route.path || "reports")
const mobileInputId = `report-workspace-${Math.random().toString(36).slice(2, 8)}`
const remembered = ref(readRememberedReport(storageId.value))

const hasList = computed(() => props.reports.length > 1)
const navItems = computed(() => props.reports.map(report => ({
	key: report.value,
	label: report.label,
	icon: report.icon,
	group: report.group,
	to: { query: { ...route.query, [props.queryKey]: report.value }, hash: route.hash },
})))
const selected = computed({
	get: () => chooseReport(props.reports, route.query?.[props.queryKey], remembered.value),
	set: value => router.replace({ query: { ...route.query, [props.queryKey]: value }, hash: route.hash }),
})
const current = computed(() => props.reports.find(report => report.value === selected.value))
usePageTitle(() => current.value?.label)

watch(() => route.query?.[props.queryKey], value => {
	if (!value || !props.reports.some(report => report.value === value)) return
	remembered.value = value
	rememberReport(storageId.value, value)
})
</script>

<style scoped>
.report-workspace {
	--report-workspace-top: var(--erp-shell-header-height);
	display: grid;
	grid-template-columns: minmax(184px, 228px) minmax(0, 1fr);
	align-items: start;
	gap: var(--erp-space-4);
	min-width: 0;
}

.report-workspace--single {
	grid-template-columns: minmax(0, 1fr);
}

.report-workspace__nav {
	position: sticky;
	z-index: var(--erp-layer-sticky);
	top: calc(var(--report-workspace-top) + var(--erp-space-2));
	--collapsible-nav-max-height: calc(100vh - var(--report-workspace-top) - var(--erp-space-4));
}

.report-workspace__mobile {
	display: none;
}

.report-workspace__content {
	min-width: 0;
}

@media (max-width: 760px) {
	.report-workspace {
		grid-template-columns: minmax(0, 1fr);
		gap: var(--erp-space-2);
	}

	.report-workspace__nav {
		display: none;
	}

	.report-workspace__mobile {
		position: sticky;
		z-index: var(--erp-layer-sticky);
		top: var(--report-workspace-top);
		display: grid;
		gap: 6px;
		padding: var(--erp-space-2) 0;
		background: var(--erp-bg);
		font-size: var(--erp-font-size-caption);
		font-weight: 650;
	}
}
</style>
