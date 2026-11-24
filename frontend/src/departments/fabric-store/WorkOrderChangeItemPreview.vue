<template>
	<section class="work-order-change-item-preview" aria-label="Change Item preview">
		<p v-if="!changes.length" class="work-order-change-item-preview__empty">No recalculated changes were found for the selected Item BOM rows.</p>
		<template v-else>
			<p class="work-order-change-item-preview__summary" role="status">{{ readyCount }} of {{ changes.length }} row(s) ready to update. Quantities stay as they are unless the unit changes, then the recalculated quantity is used.</p>
			<div class="work-order-change-item-preview__wrap" role="region" tabindex="0" aria-label="Change Item rows">
				<table class="erp-data-table">
					<thead><tr><th>Item BOM</th><th>Current</th><th class="erp-number">Current qty</th><th>Recalculated</th><th class="erp-number">Calculated qty</th><th class="erp-number">New qty</th><th>Status</th></tr></thead>
					<tbody>
						<tr v-for="(change, index) in changes" :key="`${change.selection_id}-${change.row_name}-${change.new_variant}-${index}`" :class="`work-order-change-item-preview__row--${change.action}`">
							<td>{{ change.item }}</td>
							<td><strong>{{ change.old_variant || "—" }}</strong><small v-if="change.old_attributes">{{ change.old_attributes }}</small></td>
							<td class="erp-number">{{ change.old_variant ? `${number(change.old_qty)} ${change.old_uom || ""}` : "—" }}</td>
							<td><strong>{{ change.new_variant || "—" }}</strong><small v-if="change.new_attributes">{{ change.new_attributes }}</small></td>
							<td class="erp-number">{{ change.new_variant ? `${number(change.calculated_qty)} ${change.calculated_uom || ""}` : "—" }}</td>
							<td class="erp-number">{{ change.action === "replace" ? `${number(change.new_qty)} ${change.new_uom || ""}` : "—" }}</td>
							<td><span class="work-order-change-item-preview__status">{{ statusLabel(change) }}</span><small v-if="change.action === 'blocked' && change.reason">{{ change.reason }}</small></td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>
	</section>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({ changes: { type: Array, default: () => [] } })
const readyCount = computed(() => props.changes.filter((change) => change.action === "replace" && change.eligible).length)

function statusLabel(change) {
	if (change.action === "replace") return change.note ? `Ready — ${change.note}` : "Ready"
	if (change.action === "unchanged") return "No change"
	return "Blocked"
}
function number(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
</script>

<style scoped>
.work-order-change-item-preview { display: grid; gap: var(--erp-space-2); }
.work-order-change-item-preview__summary, .work-order-change-item-preview__empty { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.work-order-change-item-preview__wrap { max-width: 100%; max-height: 46vh; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.work-order-change-item-preview__wrap:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.work-order-change-item-preview table { width: 100%; min-width: 860px; }
.work-order-change-item-preview td small { display: block; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-change-item-preview__status { font-weight: 700; }
.work-order-change-item-preview__row--replace .work-order-change-item-preview__status { color: var(--erp-success-text); }
.work-order-change-item-preview__row--blocked .work-order-change-item-preview__status { color: var(--erp-danger); }
.work-order-change-item-preview__row--unchanged { color: var(--erp-text-muted); }
</style>
