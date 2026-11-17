<template>
	<DepartmentPage :title="config.pluralLabel" back-to="/planning" back-label="Planning" :show-title="false" flat full-width inline-navigation>
		<ListView :key="kind" :doctype="config.doctype" :title="config.label" eyebrow="Planning" :default-columns="config.listColumns"
			:allow-bulk-actions="false" full-width viewport-bounded clickable @row-click="openRecord">
			<template #toolbar-actions>
				<Button v-if="canCreateDoctype(config.doctype)" label="New" icon="pi pi-plus" @click="router.push({ name: config.routes.new })" />
			</template>
		</ListView>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"
import { useRouter } from "vue-router"

import DepartmentPage from "../../../components/DepartmentPage.vue"
import ListView from "../../../components/common/ListView.vue"
import { openListDocument } from "../../../router/listDocumentNavigation.js"
import { canCreateDoctype } from "../../../utils/linkTarget.js"
import { ACTION_MASTER_KINDS } from "./actionMaster.js"

/** Action Master or Action Master Template list. */
const props = defineProps({ kind: { type: String, default: "master" } })
const router = useRouter()
const config = computed(() => ACTION_MASTER_KINDS[props.kind])

function openRecord(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: config.value.routes.view, paramName: "documentName" })
}
</script>
