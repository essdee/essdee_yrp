<template>
	<section class="department-search" aria-label="Search all departments">
		<span class="department-search__field">
			<i class="pi pi-search" aria-hidden="true" />
			<InputText
				:id="inputId"
				ref="input"
				v-model="query"
				type="search"
				role="combobox"
				autocomplete="off"
				placeholder="Search cards and reports in every department  ( / )"
				aria-label="Search cards and reports in every department"
				:aria-expanded="Boolean(query)"
				:aria-controls="listId"
				:aria-activedescendant="activeResult ? optionId(activeIndex) : undefined"
				fluid
				@keydown="onKeydown"
			/>
		</span>
		<div v-if="query" :id="listId" class="department-search__results erp-card" role="listbox" aria-label="Matching cards">
			<p v-if="loadError" class="department-search__message">{{ loadError }} <button type="button" @click="load">Retry</button></p>
			<p v-else-if="loading" class="department-search__message" role="status">Loading cards…</p>
			<p v-else-if="!results.length" class="department-search__message">No card or report matches “{{ query }}”.</p>
			<template v-else>
				<RouterLink
					v-for="(result, index) in results"
					:id="optionId(index)"
					:key="result.id"
					:to="result.to"
					class="department-search__result"
					:class="{ 'department-search__result--active': index === activeIndex }"
					role="option"
					:aria-selected="index === activeIndex"
					@mouseenter="activeIndex = index"
				>
					<i :class="result.icon" aria-hidden="true" />
					<span class="department-search__text">
						<strong>{{ result.label }}</strong>
						<small v-if="result.description">{{ result.description }}</small>
					</span>
					<span class="department-search__department">{{ result.kind === "report" ? `${result.department} report` : result.department }}</span>
				</RouterLink>
			</template>
		</div>
	</section>
</template>

<script setup>
import InputText from "primevue/inputtext"
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from "vue"
import { RouterLink, useRouter } from "vue-router"

import { getDepartmentCapabilities } from "../../api/departmentSearch.js"
import { isWorkspaceSearchShortcut } from "../../components/common/workspaceSearch.js"
import { getDepartmentEntries } from "./departmentCards.js"
import { dedupeEntries, searchResults } from "./departmentSearch.js"

/** Search the cards and reports of every department the user can open. */
const router = useRouter()
const uid = useId()
const inputId = `department-search-${uid}`
const listId = `department-search-results-${uid}`
const input = ref(null)
const query = ref("")
const activeIndex = ref(0)
const loading = ref(true)
const loadError = ref("")
const allResults = ref([])
const results = computed(() => searchResults(allResults.value, query.value))
const activeResult = computed(() => results.value[activeIndex.value])
const optionId = (index) => `${listId}-${index}`

watch(query, () => { activeIndex.value = 0 })

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		allResults.value = dedupeEntries(await getDepartmentEntries(await getDepartmentCapabilities() || {}))
	} catch (reason) {
		loadError.value = reason?.message || "Unable to load department cards."
	} finally {
		loading.value = false
	}
}

function move(step) {
	const count = results.value.length
	if (count) activeIndex.value = (activeIndex.value + step + count) % count
}

function onKeydown(event) {
	if (event.key === "ArrowDown" || event.key === "ArrowUp") {
		event.preventDefault()
		move(event.key === "ArrowDown" ? 1 : -1)
	} else if (event.key === "Enter" && activeResult.value) {
		event.preventDefault()
		router.push(activeResult.value.to)
	} else if (event.key === "Escape") {
		event.preventDefault()
		query.value = ""
	}
}

const focusInput = () => document.getElementById(inputId)?.focus()

function onWindowKeydown(event) {
	if (!isWorkspaceSearchShortcut(event)) return
	event.preventDefault()
	focusInput()
}

onMounted(() => {
	focusInput()
	window.addEventListener("keydown", onWindowKeydown)
	load()
})
onBeforeUnmount(() => window.removeEventListener("keydown", onWindowKeydown))
</script>

<style scoped>
.department-search {
	position: relative;
	width: 100%;
}

.department-search__field {
	position: relative;
	display: block;
}

.department-search__field > i {
	position: absolute;
	top: 50%;
	left: 12px;
	z-index: 1;
	color: var(--erp-text-muted);
	transform: translateY(-50%);
}

.department-search__field :deep(input) {
	padding-left: 36px;
}

.department-search__results {
	position: absolute;
	top: calc(100% + var(--erp-space-2));
	right: 0;
	z-index: 30;
	display: grid;
	align-content: start;
	box-sizing: border-box;
	width: min(560px, calc(100vw - 2 * var(--erp-page-gutter, 16px)));
	min-width: 100%;
	max-height: min(420px, 60vh);
	padding: var(--erp-space-1);
	overflow-y: auto;
	box-shadow: var(--erp-shadow-pop);
}

@media (max-width: 640px) {
	.department-search__results {
		left: 0;
		width: 100%;
	}
}

.department-search__message {
	margin: 0;
	padding: var(--erp-space-3);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-table);
}

.department-search__result {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr) auto;
	align-items: center;
	gap: var(--erp-space-3);
	padding: var(--erp-space-2) var(--erp-space-3);
	border-radius: var(--erp-control-radius, 8px);
	color: var(--erp-text);
	text-decoration: none;
}

.department-search__result--active {
	background: var(--erp-surface-muted);
}

.department-search__result > i {
	color: var(--erp-accent-ink);
}

.department-search__text {
	display: grid;
	min-width: 0;
}

.department-search__text small {
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	text-overflow: ellipsis;
	white-space: nowrap;
}

.department-search__department {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	white-space: nowrap;
}
</style>
