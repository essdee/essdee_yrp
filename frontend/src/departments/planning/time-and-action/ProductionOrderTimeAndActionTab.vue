<template>
	<div class="ppo-ta">
		<Skeleton v-if="loading && !context" height="240px" />
		<template v-else>
			<Message v-if="isFrozen(context)" severity="info" :closable="false" class="ppo-ta__frozen">
				Frozen — converted to Lot T&A<template v-if="context.copies.length">:
					<span v-for="(copy, index) in context.copies" :key="copy.name"><DocumentLink doctype="SD YRP Time and Action" :name="copy.name" /> ({{ copy.lot }})<template v-if="index < context.copies.length - 1">, </template></span>
				</template>
			</Message>
			<LotTimeAndActionTab :key="`${context?.time_and_action}-${context?.status}`" subject="Production Order" :time-and-action="context?.time_and_action || ''" :load-error="error" :can-create="Boolean(context?.can_create)" @create="createVisible = true">
				<template #actions>
					<Button v-if="context?.can_convert" label="Convert to Lot T&A" icon="pi pi-clone" severity="secondary" outlined size="small" @click="convertVisible = true" />
				</template>
			</LotTimeAndActionTab>
		</template>
		<CreateTimeAndActionDialog v-model:visible="createVisible" against="YRP Production Order" :against-id="productionOrder" :item="context?.item || ''" :qty="context?.qty || 0" @created="load" />
		<ConvertToLotTimeAndActionDialog v-if="context?.time_and_action" v-model:visible="convertVisible" :time-and-action="context.time_and_action" @converted="load" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { ref, watch } from "vue"

import { getProductionOrderTimeAndAction } from "../../../api/timeAndAction.js"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import ConvertToLotTimeAndActionDialog from "./ConvertToLotTimeAndActionDialog.vue"
import CreateTimeAndActionDialog from "./CreateTimeAndActionDialog.vue"
import LotTimeAndActionTab from "./LotTimeAndActionTab.vue"
import { isFrozen } from "./productionOrderTimeAndAction.js"

/** Production Order "Time and Action" tab: Create T&A, the read-only report, and Convert to Lot T&A. */
const props = defineProps({
	productionOrder: { type: String, required: true },
})
const context = ref(null)
const loading = ref(false)
const error = ref("")
const createVisible = ref(false)
const convertVisible = ref(false)
let sequence = 0

async function load() {
	const current = ++sequence
	loading.value = true
	error.value = ""
	try {
		const payload = await getProductionOrderTimeAndAction(props.productionOrder)
		if (current === sequence) context.value = payload
	} catch (reason) {
		if (current === sequence) error.value = reason?.message || "Unable to load the Time and Action."
	} finally {
		if (current === sequence) loading.value = false
	}
}

watch(() => props.productionOrder, () => {
	context.value = null
	load()
}, { immediate: true })
</script>

<style scoped>
.ppo-ta { display: grid; min-width: 0; gap: var(--erp-space-3); }
.ppo-ta__frozen :deep(a) { font-weight: 600; }
</style>
