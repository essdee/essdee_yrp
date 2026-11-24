<template>
	<DepartmentPage :title="title" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			:title="title"
			:eyebrow="eyebrow"
			:sections="sections"
			:loading="loading"
			empty-text="No permitted workspaces in this layout"
			:skeleton-count="cardCount"
		/>
	</DepartmentPage>
</template>

<script setup>
import { onMounted, ref } from "vue"

import { getDepartmentCapabilities } from "../../api/departmentSearch.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLauncher from "../../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import { getReadableSections, getWorkspaceView } from "./workspaceSections.js"

/** `departmentKey` is set for an overridden department landing; without it this is the user's /workspace home. */
const props = defineProps({ departmentKey: { type: String, default: "" } })
const view = getWorkspaceView(props.departmentKey)
const title = view.title
const eyebrow = props.departmentKey ? "Department workspace" : "Your workspace"
const cardCount = Math.max(1, view.sections.reduce((count, section) => count + section.cards.length, 0))
const loading = ref(true)
const loadError = ref("")
const sections = ref([])

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = await getReadableSections(view.sections, await getDepartmentCapabilities() || {})
	} catch (reason) {
		sections.value = []
		loadError.value = reason?.message || "Unable to load your workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
