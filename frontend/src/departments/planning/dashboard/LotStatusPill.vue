<template>
	<span class="pd-status" :class="`pd-status--${tone}`" :data-lot-status="status">{{ status }}</span>
</template>

<script setup>
import { computed } from "vue"
import { statusTone } from "./dashboardRows.js"

/** Lot ladder status pill; "No Work Order yet" is neutral, fabric process names are grey. */
const props = defineProps({ status: { type: String, required: true } })
const tone = computed(() => statusTone(props.status))
</script>
