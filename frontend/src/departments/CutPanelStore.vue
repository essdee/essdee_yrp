<template>
	<DepartmentPage title="Cut Panel Store" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="Cut Panel Store"
			:items="visibleWorkspaces"
			:reports="cutPanelReportTabs(sections.reports?.reports)"
			:loading="loading"
			empty-text="No permitted Cut Panel Store workspaces"
			:skeleton-count="6"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getCutPanelStoreCapabilities } from "../api/cutPanelStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { cutPanelReportTabs } from "./departmentReports.js"
import { CUT_PANEL_STORE_WORKSPACES } from "./launcherCards.js"

const loading = ref(true)
const error = ref("")
const sections = ref({})
const visibleWorkspaces = computed(() => CUT_PANEL_STORE_WORKSPACES.filter((workspace) => sections.value[workspace.key]?.can_read))

async function load() {
	loading.value = true
	error.value = ""
	try {
		const payload = await getCutPanelStoreCapabilities() || {}
		sections.value = payload.sections || {}
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Cut Panel Store workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
