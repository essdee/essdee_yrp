<template>
	<DepartmentPage title="Cutting" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loadingPermissions" @retry="load" />
		<WorkspaceLauncher v-else title="Cutting" :items="visibleWorkspaces" :reports="reports" :loading="loadingPermissions" empty-text="No permitted Cutting workspaces" :skeleton-count="5" />
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getCuttingReportPermissions } from "../api/cuttingReports.js"
import { getCuttingCapabilities } from "../api/cuttingWorkspaces.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { cuttingReportTabs } from "./departmentReports.js"
import { CUTTING_WORKSPACES } from "./launcherCards.js"

const loadingPermissions = ref(true)
const capabilities = ref({})
const loadError = ref("")
const reports = ref([])
const visibleWorkspaces = computed(() => CUTTING_WORKSPACES.filter((workspace) => capabilities.value[workspace.key]?.can_read))

async function load() {
	loadingPermissions.value = true
	loadError.value = ""
	try {
		capabilities.value = await getCuttingCapabilities() || {}
		reports.value = capabilities.value.reports?.can_read ? cuttingReportTabs(await getCuttingReportPermissions() || {}) : []
	} catch (reason) {
		capabilities.value = {}
		reports.value = []
		loadError.value = reason?.message || "Unable to load the Cutting workspace."
	} finally {
		loadingPermissions.value = false
	}

}

onMounted(load)

</script>
