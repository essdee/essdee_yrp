<template>
	<div v-if="warnings.length" class="ipd-approval__alerts">
		<Message v-for="(warning, index) in warnings" :key="index" :severity="SEVERITY[warning.level] || 'warn'" size="small" :closable="false">{{ warning.text }}</Message>
	</div>
</template>

<script setup>
import Message from "primevue/message"

defineProps({ warnings: { type: Array, default: () => [] } })
const SEVERITY = { danger: "error", warning: "warn", info: "info" }
</script>
