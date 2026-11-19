<template>
	<DepartmentPage title="Finishing" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher v-else title="Finishing" :items="visibleWorkspaces" :reports="reports" :loading="loading" empty-text="No permitted Finishing workspaces" :skeleton-count="6" />
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getFinishingCapabilities } from "../api/finishing.js"
import { finishingReportTabs } from "./departmentReports.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { FINISHING_WORKSPACES } from "./launcherCards.js"

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const reports = computed(() => finishingReportTabs(sections.value.reports?.reports))
const visibleWorkspaces = computed(() => FINISHING_WORKSPACES.filter((workspace) => sections.value[workspace.key]?.can_read))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await getFinishingCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || "Unable to load the Finishing workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
