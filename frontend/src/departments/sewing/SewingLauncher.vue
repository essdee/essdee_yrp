<template>
	<SewingWorkspaceShell v-slot="{ capabilities, supplier }">
		<WorkspaceLauncher
			title="Sewing"
			:items="workspaces(capabilities, supplier)"
			:reports="sewingReportTabs(capabilities.reports)"
			report-query-key="tab"
			empty-text="No permitted Sewing workspaces"
			:skeleton-count="4"
			compact
		>
			<template #context><SewingUnitPicker /></template>
		</WorkspaceLauncher>
	</SewingWorkspaceShell>
</template>

<script setup>
import WorkspaceLauncher from "../../components/common/WorkspaceLauncher.vue"
import { sewingReportTabs } from "../departmentReports.js"
import SewingWorkspaceShell from "./SewingWorkspaceShell.vue"
import SewingUnitPicker from "./SewingUnitPicker.vue"
import { SEWING_WORKSPACES } from "../launcherCards.js"


function workspaces(capabilities, supplier) {
	return SEWING_WORKSPACES.filter((item) => capabilities.sections?.[item.key]?.can_read).map((item) => ({
		...item,
		to: { path: item.to, query: supplier ? { supplier } : {} },
	}))
}
</script>
