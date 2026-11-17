<template>
	<section class="action-master-steps" aria-labelledby="action-master-steps-title">
		<header class="erp-section-header action-master-steps__header">
			<h2 id="action-master-steps-title">Actions</h2>
			<small>{{ steps.filter((step) => step.action).length }} actions</small>
		</header>
		<div class="erp-table-wrap" role="region" aria-label="Action Master actions">
			<table class="erp-data-table action-master-steps__table">
				<thead>
					<tr><th class="erp-number action-master-steps__index">#</th><th>Action</th><th class="erp-number">Lead Time</th><th>Department</th><th>Dependent Actions</th><th v-if="!disabled" aria-label="Row actions" /></tr>
				</thead>
				<tbody>
					<tr v-for="(step, index) in steps" :key="step.key">
						<td class="erp-number action-master-steps__index">{{ index + 1 }}</td>
						<td class="action-master-steps__action">
							<LinkField v-if="!disabled" :model-value="step.action" doctype="SD YRP Action" :aria-label="`Action ${index + 1}`" :show-open-button="false" @update:model-value="setAction(index, $event)" @select="fillAction(index, $event)" />
							<span v-else>{{ step.action }}</span>
						</td>
						<td class="erp-number action-master-steps__lead">
							<InputNumber v-if="!disabled" :model-value="step.lead_time" :min="1" :use-grouping="false" :aria-label="`Lead Time ${index + 1}`" fluid @update:model-value="update(index, { lead_time: $event })" />
							<span v-else>{{ step.lead_time }}</span>
						</td>
						<td>
							<LinkField v-if="!disabled" :model-value="step.department" doctype="Department" :aria-label="`Department ${index + 1}`" :allow-create="false" :show-open-button="false" @update:model-value="update(index, { department: $event })" />
							<span v-else>{{ step.department || "—" }}</span>
						</td>
						<td class="action-master-steps__dependencies">
							<MultiSelectField v-if="!disabled" :model-value="step.dependent_action" :options="dependencyOptions(steps, index).map((action) => ({ label: action, value: action }))" placeholder="None" :aria-label="`Dependent Actions ${index + 1}`" @update:model-value="update(index, { dependent_action: $event })" />
							<span v-else>{{ step.dependent_action.join(", ") || "—" }}</span>
						</td>
						<td v-if="!disabled" class="action-master-steps__row-actions">
							<Button icon="pi pi-arrow-up" text rounded severity="secondary" :disabled="index === 0" :aria-label="`Move action ${index + 1} up`" @click="emit('update:steps', moveStep(steps, index, index - 1))" />
							<Button icon="pi pi-arrow-down" text rounded severity="secondary" :disabled="index === steps.length - 1" :aria-label="`Move action ${index + 1} down`" @click="emit('update:steps', moveStep(steps, index, index + 1))" />
							<Button icon="pi pi-trash" text rounded severity="danger" :aria-label="`Remove action ${index + 1}`" @click="emit('update:steps', removeStep(steps, index))" />
						</td>
					</tr>
					<tr v-if="!steps.length"><td :colspan="disabled ? 5 : 6" class="action-master-steps__empty">No actions yet.</td></tr>
				</tbody>
			</table>
		</div>
		<Button v-if="!disabled" class="action-master-steps__add" label="Add Action" icon="pi pi-plus" severity="secondary" outlined @click="emit('update:steps', [...steps, newStep()])" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"

import { getDoc } from "../../../api/frappe.js"
import LinkField from "../../../components/common/LinkField.vue"
import MultiSelectField from "../../../components/common/MultiSelectField.vue"
import { dependencyOptions, moveStep, newStep, pruneDependencies, removeStep } from "./actionMaster.js"

/** Editable Details + Dependent Details of an Action Master, one row per action. */
const props = defineProps({
	steps: { type: Array, required: true },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:steps"])

function update(index, values) {
	emit("update:steps", pruneDependencies(props.steps.map((step, position) => position === index ? { ...step, ...values } : step)))
}

function setAction(index, action) {
	if (action !== props.steps[index].action) update(index, { action })
}

async function fillAction(index, { name, row }) {
	let action = row
	if (action?.lead_time === undefined) {
		action = await getDoc("SD YRP Action", name)
		if (props.steps[index]?.action !== name) return
	}
	update(index, { action: name, lead_time: action?.lead_time ?? null, department: action?.department || "" })
}
</script>

<style scoped>
.action-master-steps { display: grid; gap: var(--erp-space-3, 12px); }
.action-master-steps__header small { color: var(--erp-text-muted); }
.action-master-steps__table { width: 100%; }
.action-master-steps__table td { vertical-align: middle; }
.action-master-steps__index { width: 48px; text-align: right; }
.action-master-steps__action { min-width: 240px; }
.action-master-steps__lead { width: 120px; }
.action-master-steps__dependencies { min-width: 240px; }
.action-master-steps__row-actions { width: 128px; white-space: nowrap; }
.action-master-steps__empty { color: var(--erp-text-muted); text-align: center; }
.action-master-steps__add { justify-self: start; }
</style>
