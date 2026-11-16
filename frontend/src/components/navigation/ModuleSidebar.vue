<template>
	<aside v-if="department && !isLanding" class="module-sidebar" :class="{ 'is-visible': cards.length > 1 }">
		<div hidden aria-hidden="true"><component :is="landing" :key="department.key" /></div>
		<CollapsibleNavList v-if="cards.length > 1" :items="cards" :label="`${department.label} workspaces`" :selected-key="selectedKey" :search-placeholder="`Search ${department.label}`" />
	</aside>
</template>

<script setup>
import { computed, defineAsyncComponent, provide, shallowRef, watch } from "vue"
import { useRoute } from "vue-router"

import CollapsibleNavList from "./CollapsibleNavList.vue"
import { getSelectedCardKey, workspaceCardsSinkKey } from "./moduleSidebar.js"

/** Left rail of the active department's other workspace cards, loaded through the department's own launcher. */
const props = defineProps({
	department: { type: Object, default: null },
})
const route = useRoute()
const cards = shallowRef([])
const isLanding = computed(() => route.path === props.department?.path)
const landing = computed(() => props.department && defineAsyncComponent(props.department.component))
const selectedKey = computed(() => getSelectedCardKey(cards.value, route.path))

watch(() => props.department?.key, () => { cards.value = [] })
provide(workspaceCardsSinkKey, (items) => { cards.value = items })
</script>

<style scoped>
.module-sidebar {
	position: fixed;
	z-index: var(--erp-layer-overlay);
	top: calc(var(--erp-shell-header-height) + var(--erp-space-2));
	bottom: var(--erp-space-2);
	left: var(--erp-space-2);
	--collapsible-nav-height: 100%;
}

@media (max-width: 760px), (hover: none) {
	.module-sidebar { display: none; }
}
</style>
