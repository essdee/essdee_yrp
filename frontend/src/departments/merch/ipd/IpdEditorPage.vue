<template>
	<DepartmentPage title="Item Production Detail" :back-to="ipdRoutes.listPath" back-label="Item Production Details" :show-title="false" flat full-width inline-navigation>
		<IpdEditor :ipd-id="ipdId" :ipd-routes="ipdRoutes" />
	</DepartmentPage>
</template>

<script setup>
import DepartmentPage from "../../../components/DepartmentPage.vue"
import { MERCH_IPD_ROUTES } from "../merchViews.js"
import IpdEditor from "./IpdEditor.vue"

defineProps({ ipdId: { type: String, default: "" }, ipdRoutes: { type: Object, default: () => MERCH_IPD_ROUTES } })
</script>
