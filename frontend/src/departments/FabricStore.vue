<template>
	<DepartmentPage :title="storeName" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			:title="storeName"
			:items="visibleWorkspaces"
			:reports="storeReportTabs(reportCapabilities, basePath.slice(1), reportKeys)"
			:loading="loading"
			:empty-text="`No permitted ${storeName} workspaces`"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getCutPanelStoreCapabilities } from "../api/cutPanelStore.js"
import { getFabricStoreCapabilities } from "../api/fabricStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { storeReportTabs } from "./departmentReports.js"
import { CUT_PANEL_STICKER_KEYS, FABRIC_STORE_WORKSPACE_KEYS, storeSections, visibleStoreWorkspaces } from "./fabric-store/storeWorkspaces.js"

const props = defineProps({
	storeName: { type: String, default: "Fabric Store" },
	basePath: { type: String, default: "/fabric-store" },
	workspaceKeys: { type: Array, default: () => FABRIC_STORE_WORKSPACE_KEYS },
	reportKeys: { type: Array, default: () => ["stock_balance"] },
	extraWorkspaces: { type: Array, default: () => [] },
	extraCapabilitiesLoader: { type: Function, default: null },
})
const loading = ref(true)
const error = ref("")
const sections = ref({})
const reportCapabilities = ref({})
const visibleWorkspaces = computed(() => visibleStoreWorkspaces(sections.value, props))

async function load() {
	loading.value = true
	error.value = ""
	try {
		const stickerKeys = CUT_PANEL_STICKER_KEYS.filter((key) => props.workspaceKeys.includes(key))
		const [payload, cutPanelPayload, extraPayload] = await Promise.all([
			getFabricStoreCapabilities(),
			stickerKeys.length ? getCutPanelStoreCapabilities() : null,
			props.extraCapabilitiesLoader ? props.extraCapabilitiesLoader() : null,
		])
		sections.value = storeSections(props.workspaceKeys, payload?.sections, cutPanelPayload?.sections, extraPayload?.sections)
		reportCapabilities.value = payload?.sections?.reports?.reports || {}
	} catch (reason) {
		error.value = reason?.message || `Unable to load the ${props.storeName} workspace.`
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
