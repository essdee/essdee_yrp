<template>
	<ListView :doctype="capability.doctype" :title="title" :search-placeholder="`Search ${title}…`" :name-column-label="label" :row-mark="isDelivery ? 'DC' : 'GRN'" :default-columns="columns" viewport-bounded clickable @row-click="openDocument">
		<template v-if="newRouteName && capability.can_create" #toolbar-actions>
			<Button :label="`New ${label}`" icon="pi pi-plus" @click="router.push({ name: newRouteName })" />
		</template>
	</ListView>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"
import { useRouter } from "vue-router"
import ListView from "../../components/common/ListView.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"

/** Every Delivery Challan or GRN, narrowed only by the status tabs and filters the user sets; departments pass their page and new-document routes. */
const props = defineProps({
	capability: { type: Object, required: true },
	viewRouteName: { type: String, default: "" },
	newRouteName: { type: String, default: "" },
})
const router = useRouter()
const isDelivery = computed(() => props.capability.doctype === "YRP Delivery Challan")
const label = computed(() => isDelivery.value ? "Delivery Challan" : "Goods Received Note")
const title = computed(() => isDelivery.value ? "Delivery Challans" : "Goods Received Notes")
const sourceFields = computed(() => [isDelivery.value ? "work_order" : "against_id", ...(props.viewRouteName ? [] : ["cut_panel_movement"])])
const columns = computed(() => ["posting_date", "supplier", ...sourceFields.value, "docstatus"])
function openDocument(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: props.viewRouteName || (isDelivery.value ? "cut-panel-delivery-challan" : "cut-panel-goods-received-note"),
		paramName: isDelivery.value ? "deliveryChallanId" : "goodsReceivedNoteId",
	})
}
</script>
