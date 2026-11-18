<template>
	<DepartmentPage title="Supplier" :back-to="SUPPLIERS_PATH" back-label="Suppliers" :show-title="false" flat full-width inline-navigation
		:activity-doctype="supplierId ? SUPPLIER_DOCTYPE : ''" :activity-name="supplierId" :activity-record="record">
		<FormView :doctype="SUPPLIER_DOCTYPE" :name="supplierId" title="Supplier" :readonly="readonly" :group-layout="groupLayout" uniform-grid show-cancel
			@loaded="record = $event.doc" @saved="saved" @cancel="router.push(SUPPLIERS_PATH)">
			<template #header-actions>
				<DocumentDeleteButton v-if="supplierId" :doctype="SUPPLIER_DOCTYPE" :name="supplierId" :redirect-to="SUPPLIERS_PATH" />
			</template>
			<template #tab-end="{ tab, mode }">
				<template v-if="tab.key === ADDRESS_CONTACT_GROUP && supplierId">
					<SupplierLinkedRecords v-if="mode === 'view'" :supplier="supplierId" />
					<p v-else class="supplier-page__hint">Save or cancel editing to manage addresses and contacts.</p>
				</template>
			</template>
		</FormView>
	</DepartmentPage>
</template>

<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"

import DepartmentPage from "../../../components/DepartmentPage.vue"
import FormView from "../../../components/common/FormView.vue"
import DocumentDeleteButton from "../../../components/documents/DocumentDeleteButton.vue"
import { useDocumentPermissions } from "../../../composables/useDocumentPermissions.js"
import { canCreateDoctype } from "../../../utils/linkTarget.js"
import { MERCH_ROUTES } from "../merchRoutes.js"
import SupplierLinkedRecords from "./SupplierLinkedRecords.vue"
import { ADDRESS_CONTACT_GROUP, SUPPLIER_DOCTYPE, SUPPLIERS_PATH, supplierGroups } from "./supplierViews.js"

/** New or existing Supplier as the Desk form, grouped Details → Address & Contact → Accounting → Tax → Tax Identification → Settings → the rest. */
const props = defineProps({ supplierId: { type: String, default: "" } })
const router = useRouter()
const record = ref({})
const permissions = useDocumentPermissions(() => [SUPPLIER_DOCTYPE, props.supplierId, 0])
const readonly = computed(() => props.supplierId ? !permissions.value?.write : !canCreateDoctype(SUPPLIER_DOCTYPE))
const groupLayout = (tabs, meta) => supplierGroups(tabs, meta, { existing: Boolean(props.supplierId) })

function saved(doc) {
	record.value = doc || {}
	if (doc?.name && doc.name !== props.supplierId) router.replace({ name: MERCH_ROUTES.supplier, params: { supplierId: doc.name } })
}
</script>

<style scoped>
.supplier-page__hint { margin: 0; padding: 16px; color: var(--erp-text-muted); background: var(--erp-surface); border: 1px dashed var(--erp-border); border-radius: var(--erp-panel-radius); }
</style>
