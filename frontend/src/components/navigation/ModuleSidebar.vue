<template>
	<aside v-if="department && !isLanding" id="module-sidebar" class="module-sidebar" :class="{ 'is-visible': cards.length > 1, 'is-open': isDrawerOpen, 'is-pinned': isAvailable && isPinned && !isDrawer }">
		<div hidden aria-hidden="true"><component :is="landing" :key="department.key" /></div>
		<CollapsibleNavList v-if="cards.length > 1" :items="cards" :label="`${department.label} workspaces`" :selected-key="selectedKey" :search-placeholder="`Search ${department.label}`" :pinned="isDrawer || isPinned" />
	</aside>
	<div v-if="isDrawerOpen" class="module-sidebar__backdrop" aria-hidden="true" @click="emit('update:open', false)" />
</template>

<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, provide, ref, shallowRef, watch } from "vue"
import { useRoute } from "vue-router"

import CollapsibleNavList from "./CollapsibleNavList.vue"
import { DRAWER_MEDIA_QUERY, getSelectedCardKey, isSidebarPinned, saveSidebarPinned, workspaceCardsSinkKey } from "./moduleSidebar.js"
import { getSessionUser } from "./sessionUser.js"

/** Left rail of the active department's other workspace cards, loaded through the department's own launcher; kept open per user on desktop, an off-canvas drawer on tablets and phones. */
const props = defineProps({
	department: { type: Object, default: null },
	open: { type: Boolean, default: false },
})
const emit = defineEmits(["update:open", "availability"])
const route = useRoute()
const cards = shallowRef([])
const isLanding = computed(() => route.path === props.department?.path)
const landing = computed(() => props.department && defineAsyncComponent(props.department.component))
const selectedKey = computed(() => getSelectedCardKey(cards.value, route.path))
const isAvailable = computed(() => Boolean(props.department) && !isLanding.value && cards.value.length > 1)

const drawerMedia = globalThis.window?.matchMedia?.(DRAWER_MEDIA_QUERY)
const isDrawer = ref(Boolean(drawerMedia?.matches))
const isDrawerOpen = computed(() => isDrawer.value && isAvailable.value && props.open)
const user = getSessionUser().id
const isPinned = ref(isSidebarPinned(user))
const isExpanded = computed(() => (isDrawer.value ? isDrawerOpen.value : isPinned.value))

/** Top-bar toggle: opens the drawer on tablets and phones, keeps the rail open on desktop. */
function toggle() {
	if (isDrawer.value) return emit("update:open", !props.open)
	isPinned.value = !isPinned.value
	saveSidebarPinned(user, isPinned.value)
}

function onMediaChange(event) {
	isDrawer.value = event.matches
	if (!event.matches) emit("update:open", false)
}
function onKeydown(event) {
	if (event.key === "Escape" && isDrawerOpen.value) emit("update:open", false)
}
drawerMedia?.addEventListener?.("change", onMediaChange)
globalThis.window?.addEventListener?.("keydown", onKeydown)
onBeforeUnmount(() => {
	drawerMedia?.removeEventListener?.("change", onMediaChange)
	globalThis.window?.removeEventListener?.("keydown", onKeydown)
})

watch(() => props.department?.key, () => { cards.value = [] })
watch(isAvailable, (available) => emit("availability", available), { immediate: true })
provide(workspaceCardsSinkKey, (items) => { cards.value = items })
defineExpose({ toggle, isExpanded })
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

.module-sidebar.is-pinned { width: 248px; }
.module-sidebar.is-pinned :deep(.collapsible-nav) { height: 100%; }

.module-sidebar__backdrop {
	position: fixed;
	z-index: calc(var(--erp-layer-overlay) - 1);
	inset: var(--erp-shell-header-height) 0 0;
	background: rgba(16, 20, 18, .36);
}

@media (max-width: 900px), (hover: none) {
	.module-sidebar { display: none; }
	.module-sidebar.is-open {
		display: block;
		top: var(--erp-shell-header-height);
		bottom: 0;
		left: 0;
		box-sizing: border-box;
		width: min(320px, 86vw);
		padding: var(--erp-space-2);
		background: var(--erp-surface);
		border-right: 1px solid var(--erp-border);
		box-shadow: var(--erp-shadow-pop);
	}
	.module-sidebar.is-open :deep(.collapsible-nav) { height: 100%; }
	.module-sidebar.is-open :deep(.collapsible-nav__panel) { border: 0; padding: 2px; }
	.module-sidebar.is-open :deep(.collapsible-nav__item) {
		min-height: 44px;
		font-size: var(--erp-font-size-body);
	}
	.module-sidebar.is-open :deep(.collapsible-nav__search .p-inputtext) { font-size: 16px; }
}
</style>
