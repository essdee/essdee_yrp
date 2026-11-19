<template>
	<ProcessCostEditor :process-cost-id="processCostId" :process-cost-routes="processCostRoutes" />
</template>

<script setup>
import ProcessCostEditor from "./ProcessCostEditor.vue"
import { MERCH_PROCESS_COST_ROUTES } from "./processCostViews.js"
defineProps({ processCostId: { type: String, default: "" }, processCostRoutes: { type: Object, default: () => MERCH_PROCESS_COST_ROUTES } })
</script>
