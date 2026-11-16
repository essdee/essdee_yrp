<template>
	<nav
		class="collapsible-nav"
		:class="{ 'is-expanded': expanded, 'is-pinned': pinned }"
		:aria-label="label"
		@mouseenter="hovered = true"
		@mouseleave="collapse"
		@focusin="focused = true"
		@focusout="onFocusOut"
	>
		<div class="collapsible-nav__panel">
			<div class="collapsible-nav__search">
				<i class="pi pi-search" aria-hidden="true" />
				<InputText v-model="search" type="search" :placeholder="searchPlaceholder" :aria-label="`Search ${label.toLowerCase()}`" autocomplete="off" fluid @keydown="onSearchKeydown" />
			</div>
			<div class="collapsible-nav__list">
				<template v-for="group in groups" :key="group.label">
					<p v-if="group.label" class="collapsible-nav__group">{{ group.label }}</p>
					<RouterLink
						v-for="item in group.reports"
						:key="item.key"
						:ref="element => setItemElement(item.key, element)"
						:to="item.to"
						:replace="replace"
						class="collapsible-nav__item"
						:class="{ 'is-selected': item.key === selectedKey, 'is-highlighted': item.key === highlighted && item.key !== selectedKey }"
						:aria-current="item.key === selectedKey ? 'page' : undefined"
						:title="item.label"
					><i :class="item.icon || 'pi pi-table'" aria-hidden="true" /><span>{{ item.label }}</span></RouterLink>
				</template>
				<p v-if="!groups.length" class="collapsible-nav__empty">No match for “{{ search }}”.</p>
			</div>
		</div>
	</nav>
</template>

<script setup>
import InputText from "primevue/inputtext"
import { computed, ref, watch } from "vue"
import { RouterLink, useRouter } from "vue-router"

import { reportGroups, stepReport } from "../reports/reportWorkspace.js"

/** Searchable list of links; `items` are `{ key, label, icon, to, group? }`. An icon rail that expands on hover or keyboard focus, or always open when `pinned`. */
const props = defineProps({
	items: { type: Array, required: true },
	label: { type: String, required: true },
	selectedKey: { type: String, default: "" },
	searchPlaceholder: { type: String, default: "Search" },
	replace: { type: Boolean, default: false },
	pinned: { type: Boolean, default: false },
})
const router = useRouter()
const hovered = ref(false)
const focused = ref(false)
const search = ref("")
const highlighted = ref("")
const itemElements = new Map()

const expanded = computed(() => props.pinned || hovered.value || focused.value)
const groups = computed(() => reportGroups(props.items, search.value))
const visibleKeys = computed(() => groups.value.flatMap(group => group.reports.map(item => item.key)))

watch(search, () => { highlighted.value = visibleKeys.value[0] || "" })

function setItemElement(key, element) {
	if (element) itemElements.set(key, element.$el || element)
	else itemElements.delete(key)
}

function collapse(event) {
	if (props.pinned) return
	hovered.value = false
	focused.value = false
	search.value = ""
	const active = globalThis.document?.activeElement
	if (active && event.currentTarget.contains(active)) active.blur()
}

function onFocusOut(event) {
	if (!event.currentTarget.contains(event.relatedTarget)) focused.value = false
}

function onSearchKeydown(event) {
	const delta = { ArrowDown: 1, ArrowUp: -1 }[event.key]
	if (delta) {
		event.preventDefault()
		highlighted.value = stepReport(visibleKeys.value, highlighted.value || props.selectedKey, delta)
		itemElements.get(highlighted.value)?.scrollIntoView?.({ block: "nearest" })
	} else if (event.key === "Enter") {
		event.preventDefault()
		const key = visibleKeys.value.includes(highlighted.value) ? highlighted.value : visibleKeys.value[0]
		const item = props.items.find(entry => entry.key === key)
		if (item) router[props.replace ? "replace" : "push"](item.to)
	} else if (event.key === "Escape" && search.value) {
		event.preventDefault()
		search.value = ""
	}
}
</script>

<style scoped>
.collapsible-nav {
	--collapsible-nav-rail: 44px;
	--collapsible-nav-open: 248px;
	position: relative;
	z-index: var(--erp-layer-sticky);
	width: var(--collapsible-nav-rail);
	height: 100%;
}

.collapsible-nav__panel {
	position: absolute;
	top: 0;
	left: 0;
	height: var(--collapsible-nav-height, auto);
	max-height: var(--collapsible-nav-max-height, none);
	display: grid;
	grid-template-rows: auto minmax(0, 1fr);
	gap: var(--erp-space-2);
	box-sizing: border-box;
	width: var(--collapsible-nav-rail);
	padding: var(--erp-space-2) 4px;
	overflow: hidden;
	border: 1px solid var(--erp-border-subtle);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	transition: width var(--erp-transition-fast), box-shadow var(--erp-transition-fast);
}

.collapsible-nav.is-expanded .collapsible-nav__panel {
	width: var(--collapsible-nav-open);
	padding-inline: var(--erp-space-2);
	box-shadow: var(--erp-shadow-pop);
}

.collapsible-nav.is-pinned {
	width: 100%;
	height: auto;
}

.collapsible-nav.is-pinned .collapsible-nav__panel {
	position: static;
	width: 100%;
	padding-inline: var(--erp-space-2);
	box-shadow: none;
	transition: none;
}

.collapsible-nav__search {
	position: relative;
	min-width: 0;
}

.collapsible-nav__search > i {
	position: absolute;
	top: 50%;
	left: 10px;
	transform: translateY(-50%);
	color: var(--erp-text-subtle);
	font-size: var(--erp-font-size-caption);
	pointer-events: none;
}

.collapsible-nav__search :deep(.p-inputtext) {
	padding-left: 30px;
	font-size: var(--erp-font-size-caption);
}

.collapsible-nav:not(.is-expanded) .collapsible-nav__search :deep(.p-inputtext) {
	border-color: transparent;
	background: transparent;
	box-shadow: none;
	color: transparent;
}

.collapsible-nav:not(.is-expanded) .collapsible-nav__search :deep(.p-inputtext)::placeholder {
	color: transparent;
}

.collapsible-nav__list {
	display: grid;
	align-content: start;
	gap: 1px;
	min-height: 0;
	overflow-x: hidden;
	overflow-y: auto;
	overscroll-behavior: contain;
	scrollbar-width: thin;
}

.collapsible-nav:not(.is-expanded) .collapsible-nav__list {
	scrollbar-width: none;
}

.collapsible-nav__group {
	margin: var(--erp-space-2) 0 2px;
	padding: 0 8px;
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: 0.04em;
	text-transform: uppercase;
	white-space: nowrap;
}

.collapsible-nav:not(.is-expanded) .collapsible-nav__group {
	height: 0;
	margin: 4px 0;
	border-top: 1px solid var(--erp-border-subtle);
	color: transparent;
}

.collapsible-nav__item {
	display: flex;
	align-items: center;
	gap: 10px;
	min-width: 0;
	min-height: 32px;
	padding: 5px 10px;
	border-radius: var(--erp-control-radius);
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-caption);
	text-decoration: none;
	white-space: nowrap;
	transition: background var(--erp-transition-fast), color var(--erp-transition-fast);
}

.collapsible-nav__item i {
	flex: none;
	width: 14px;
	color: var(--erp-text-subtle);
	font-size: 0.82rem;
	text-align: center;
}

.collapsible-nav__item span {
	min-width: 0;
	overflow: hidden;
	text-overflow: ellipsis;
}

.collapsible-nav:not(.is-expanded) .collapsible-nav__item span {
	visibility: hidden;
}

.collapsible-nav__item:hover,
.collapsible-nav__item.is-highlighted {
	background: var(--erp-surface-hover);
	color: var(--erp-text);
}

.collapsible-nav__item:focus-visible {
	outline: none;
	box-shadow: var(--erp-focus-ring);
}

.collapsible-nav__item.is-selected {
	background: var(--erp-accent-soft);
	color: var(--erp-accent-ink);
	font-weight: var(--erp-font-weight-semibold);
}

.collapsible-nav__item.is-selected i {
	color: var(--erp-accent-ink);
}

.collapsible-nav__empty {
	margin: var(--erp-space-2) 8px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	white-space: normal;
}

.collapsible-nav:not(.is-expanded) .collapsible-nav__empty {
	visibility: hidden;
}

@media (prefers-reduced-motion: reduce) {
	.collapsible-nav__panel { transition: none; }
}
</style>
