<template>
	<div class="ppo-ta">
		<Skeleton v-if="loading && !context" height="240px" />
		<template v-else>
			<Message v-if="isFrozen(context)" severity="info" :closable="false" class="ppo-ta__frozen">
				Frozen — converted to Lot T&A<template v-if="context.copies.length">:
					<span v-for="(copy, index) in context.copies" :key="copy.name"><RouterLink :to="departmentLotLocation(route.path, copy.lot, 'time-and-action')">{{ copy.name }} ({{ copy.lot }})</RouterLink><template v-if="index < context.copies.length - 1">, </template></span>
				</template>
			</Message>
			<LotTimeAndActionTab :key="`${context?.time_and_action}-${context?.status}`" subject="Production Order" :update-route-name="updateRouteName" :time-and-action="context?.time_and_action || ''" :load-error="error" :can-create="Boolean(context?.can_create)" :create-blocked-reason="context?.create_blocked_reason || ''" @create="emit('create')" @reverted="emit('changed')">
				<template #actions>
					<Button v-if="context?.can_convert" label="Convert to Lot T&A" icon="pi pi-clone" severity="secondary" outlined size="small" @click="convertVisible = true" />
				</template>
			</LotTimeAndActionTab>
		</template>
		<ConvertToLotTimeAndActionDialog v-if="context?.time_and_action" v-model:visible="convertVisible" :time-and-action="context.time_and_action" @converted="emit('changed')" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { ref } from "vue"
import { useRoute } from "vue-router"

import ConvertToLotTimeAndActionDialog from "./ConvertToLotTimeAndActionDialog.vue"
import LotTimeAndActionTab from "./LotTimeAndActionTab.vue"
import { isFrozen } from "./productionOrderTimeAndAction.js"
import { departmentLotLocation } from "./timeAndAction.js"

/** Production Order "Time and Action" tab: the read-only report, Create T&A prompt, and Convert to Lot T&A; the page owns the context. */
defineProps({
	context: { type: Object, default: null },
	loading: { type: Boolean, default: false },
	error: { type: String, default: "" },
	updateRouteName: { type: String, default: undefined },
})
const emit = defineEmits(["create", "changed"])
const convertVisible = ref(false)
const route = useRoute()
</script>

<style scoped>
.ppo-ta { display: grid; min-width: 0; gap: var(--erp-space-3); }
</style>
