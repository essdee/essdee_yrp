<template>
	<div class="sales-launcher">
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="Sales"
			:items="visibleItems"
			:reports="salesReportTabs(capabilities)"
			:loading="loading"
			:skeleton-count="2"
			empty-text="No permitted Sales workspaces"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getSalesCapabilities } from "../../api/sales.js"
import WorkspaceLauncher from "../../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import { salesReportTabs } from "../departmentReports.js"
import { SALES_WORKSPACES } from "../launcherCards.js"

const loading = ref(true)
const error = ref("")
const capabilities = ref({ sections: {} })

const visibleItems = computed(() => SALES_WORKSPACES.filter((item) => capabilities.value.sections?.[item.key]?.can_read))

async function load() {
	loading.value = true
	error.value = ""
	try {
		capabilities.value = await getSalesCapabilities() || { sections: {} }
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Sales workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
