<template>
	<DepartmentPage title="Suppliers" back-to="/merch" back-label="Merch" :show-title="false" flat full-width inline-navigation>
		<ListView :doctype="SUPPLIER_DOCTYPE" title="Suppliers" eyebrow="Merch" name-column-label="Supplier" search-placeholder="Search Suppliers…"
			:default-columns="SUPPLIER_LIST_COLUMNS" :allow-bulk-actions="false" full-width viewport-bounded clickable @row-click="openRecord">
			<template #toolbar-actions>
				<Button v-if="canCreateDoctype(SUPPLIER_DOCTYPE)" label="New" icon="pi pi-plus" @click="router.push({ name: MERCH_ROUTES.supplierNew })" />
			</template>
		</ListView>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import { useRouter } from "vue-router"

import DepartmentPage from "../../../components/DepartmentPage.vue"
import ListView from "../../../components/common/ListView.vue"
import { openListDocument } from "../../../router/listDocumentNavigation.js"
import { canCreateDoctype } from "../../../utils/linkTarget.js"
import { MERCH_ROUTES } from "../merchRoutes.js"
import { SUPPLIER_DOCTYPE, SUPPLIER_LIST_COLUMNS } from "./supplierViews.js"

/** Supplier list for Merch; Supplier read permission decides who reaches it. */
const router = useRouter()

function openRecord(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: MERCH_ROUTES.supplier, paramName: "supplierId" })
}
</script>
