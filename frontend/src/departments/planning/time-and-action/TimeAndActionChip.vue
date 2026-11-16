<template>
	<span class="ta-chip" :class="`ta-chip--${tone}`"><i v-if="tone === 'blocked'" class="pi pi-lock" aria-hidden="true" />{{ label }}</span>
</template>

<script setup>
/** Status chip of a T&A action: done, due, overdue, blocked, error or info. */
defineProps({ tone: { type: String, required: true }, label: { type: String, required: true } })
</script>

<style scoped>
.ta-chip { display: inline-flex; align-items: center; gap: 5px; height: 22px; padding: 0 8px; font-size: var(--erp-font-size-caption); font-weight: 600; line-height: 1; border-radius: 999px; white-space: nowrap; }
.ta-chip::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.ta-chip i { font-size: 10px; }
.ta-chip--info { color: var(--erp-info); background: var(--erp-info-soft); }
.ta-chip--done { color: var(--erp-success-text); background: var(--erp-success-soft); }
.ta-chip--overdue, .ta-chip--error { color: var(--erp-danger); background: var(--erp-danger-soft); }
.ta-chip--due { color: var(--erp-attention-text); background: var(--erp-attention-soft); }
.ta-chip--blocked { color: var(--erp-text-muted); background: var(--erp-surface-muted); }
.ta-chip--blocked::before { display: none; }
</style>
