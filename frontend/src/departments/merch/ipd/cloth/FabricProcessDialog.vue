<template>
	<Dialog :visible="Boolean(draft)" modal class="erp-entity-dialog erp-dialog--lg ipd-fp-dialog" :header="draft?.fabric_process || 'Process'" @update:visible="(open) => !open && emit('cancel')">
		<div v-if="draft" class="ipd-cloth-dialog__body" data-testid="fp-dialog">
			<div class="ipd-fp-flow">
				<span class="ipd-fp-badge" :class="`ipd-fp-badge--${badge.key}`">{{ badge.label }}</span>
				<span class="ipd-fp-item">{{ inputLabel }}</span>
				<template v-if="draft.shapeKey === 'conv'"><span class="ipd-fp-arrow">→</span><span class="ipd-fp-item">{{ draft.output_item || "(pick output)" }}</span></template>
				<span v-else class="ipd-fp-same">same item</span>
			</div>

			<template v-if="draft.shapeKey === 'conv'">
				<section class="ipd-fp-panel">
					<h4 class="ipd-fp-panel__head">{{ recipe ? "Items — consume the cloth recipe and produce the cloth" : "Items — consume one item and produce another" }}</h4>
					<div class="ipd-fp-row">
						<div v-if="recipe" class="ipd-cloth-dialog__field">
							<span class="erp-field-label">Input materials and ratios</span>
							<span class="ipd-fp-item" data-testid="fp-input-recipe">{{ recipeLabel || "(add input materials)" }}</span>
							<small class="erp-help-text">Edit these in the Yarn Ratio table on this tab.</small>
						</div>
						<div v-else class="ipd-cloth-dialog__field">
							<label class="erp-field-label" for="ipd-fp-input-item">Input item (consumed)</label>
							<LinkField v-model="draft.input_item" doctype="Item" input-id="ipd-fp-input-item" placeholder="Pick the consumed item…" :show-open-button="false" />
						</div>
						<div class="ipd-cloth-dialog__field">
							<label class="erp-field-label" for="ipd-fp-output-item">Output item (produced)</label>
							<LinkField v-model="draft.output_item" doctype="Item" input-id="ipd-fp-output-item" placeholder="Pick the produced item…" :show-open-button="false" />
						</div>
						<div class="ipd-cloth-dialog__field ipd-fp-narrow">
							<label class="erp-field-label" for="ipd-fp-ratio">Qty ratio (out / in)</label>
							<InputNumber v-model="draft.quantity_ratio" input-id="ipd-fp-ratio" :min="0" :max-fraction-digits="3" fluid />
						</div>
					</div>
				</section>

				<section class="ipd-fp-panel">
					<h4 class="ipd-fp-panel__head">① Configured output attributes</h4>
					<p class="erp-help-text">These attributes come from the Process master. The IPD supplies only their values.</p>
					<p v-if="!draft.introduce.length" class="ipd-cloth-strip ipd-cloth-strip--info">This Process has no Output Attributes configured, so it is a pure item conversion with no output attribute matrix.</p>
					<div v-for="(entry, index) in draft.introduce" :key="entry.attr" class="ipd-fp-pair">
						<span class="ipd-fp-chip ipd-fp-chip--introduce">{{ entry.attr }}</span>
						<div v-if="!draft.consume_attrs.length" class="ipd-fp-chipbox">
							<span v-for="(value, valueIndex) in entry.chips" :key="value" class="ipd-fp-chip ipd-fp-chip--introduce">
								{{ value }}<button type="button" class="ipd-fp-x" :aria-label="`Remove ${value}`" @click="entry.chips.splice(valueIndex, 1)">×</button>
							</span>
							<InputText v-model="entry.input" :list="listId(entry.attr)" placeholder="type a value, press Enter" :data-testid="`fp-introduce-input-${index}`" @keydown.enter.prevent="addChip(entry)" />
						</div>
					</div>
					<template v-if="!draft.consume_attrs.length">
						<p v-if="combinationCount" class="erp-help-text">{{ combinationCount }} output combination(s) will be generated</p>
						<p v-else class="erp-help-text">No attributes introduced — a pure item swap (no matrix generated).</p>
					</template>
				</section>

				<section class="ipd-fp-panel">
					<h4 class="ipd-fp-panel__head">② Configured input attributes</h4>
					<div class="ipd-fp-chipbox">
						<span v-for="attribute in draft.consume_attrs" :key="attribute" class="ipd-fp-chip ipd-fp-chip--consume">{{ attribute }}</span>
						<span v-if="!draft.consume_attrs.length" class="erp-help-text">No input attributes configured — the conversion accepts the input item without an attribute-specific rule.</span>
					</div>
				</section>

				<section v-if="draft.consume_attrs.length" class="ipd-fp-panel">
					<h4 class="ipd-fp-panel__head">③ Enter each rule — consumed input → produced output</h4>
					<div v-for="(rule, ruleIndex) in draft.rules" :key="ruleIndex" class="ipd-fp-group">
						<div class="ipd-fp-group__head">Rule {{ ruleIndex + 1 }}
							<Button v-if="draft.rules.length > 1" icon="pi pi-times" text severity="secondary" size="small" :aria-label="`Remove rule ${ruleIndex + 1}`" @click="draft.rules.splice(ruleIndex, 1)" />
						</div>
						<div class="ipd-fp-rule">
							<div class="ipd-fp-rule__side">
								<label v-for="attribute in draft.consume_attrs" :key="attribute" class="ipd-fp-pair">
									<span class="ipd-fp-attr">{{ attribute }}</span>
									<InputText v-model="rule.in[attribute]" :list="listId(attribute)" placeholder="consumed value" :data-testid="`fp-rule-from-${ruleIndex}-${attribute}`" />
								</label>
							</div>
							<span class="ipd-fp-arrow">→</span>
							<div class="ipd-fp-rule__side">
								<label v-for="entry in draft.introduce" :key="entry.attr" class="ipd-fp-pair">
									<span class="ipd-fp-attr">{{ entry.attr }}</span>
									<InputText v-model="rule.out[entry.attr]" :list="listId(entry.attr)" placeholder="produced value" :data-testid="`fp-rule-to-${ruleIndex}-${entry.attr}`" />
								</label>
								<span v-if="!draft.introduce.length" class="erp-help-text">nothing introduced — the consumed attribute is dropped</span>
							</div>
						</div>
					</div>
					<Button label="Another rule" icon="pi pi-plus" text severity="secondary" size="small" data-testid="fp-add-rule" @click="draft.rules.push(blankRule(draft))" />
				</section>
			</template>

			<template v-else-if="draft.shapeKey === 'change'">
				<section class="ipd-fp-panel">
					<h4 class="ipd-fp-panel__head">① Configured value-change attributes</h4>
					<div class="ipd-fp-chipbox"><span v-for="attribute in draft.change_attrs" :key="attribute" class="ipd-fp-chip">{{ attribute }}</span></div>
					<p class="erp-help-text">These attributes come from Value Change Attributes on the Process master.</p>
				</section>
				<section class="ipd-fp-panel">
					<h4 class="ipd-fp-panel__head">② Enter each transition — from → to</h4>
					<div v-for="(group, groupIndex) in draft.groups" :key="groupIndex" class="ipd-fp-group">
						<div class="ipd-fp-group__head">{{ draft.change_attrs.length > 1 ? "Combination" : "Transition" }} {{ groupIndex + 1 }}
							<Button v-if="draft.groups.length > 1" icon="pi pi-times" text severity="secondary" size="small" :aria-label="`Remove transition ${groupIndex + 1}`" @click="draft.groups.splice(groupIndex, 1)" />
						</div>
						<div v-for="attribute in draft.change_attrs" :key="attribute" class="ipd-fp-pair">
							<span class="ipd-fp-attr">{{ attribute }}</span>
							<InputText v-model="group[attribute].from" :list="listId(attribute)" placeholder="from" :data-testid="`fp-from-${groupIndex}-${attribute}`" />
							<span class="ipd-fp-arrow">→</span>
							<InputText v-model="group[attribute].to" :list="listId(attribute)" placeholder="to" :data-testid="`fp-to-${groupIndex}-${attribute}`" />
						</div>
						<div v-if="draft.pin_attr" class="ipd-fp-pair">
							<span class="ipd-fp-attr">when {{ draft.pin_attr }} =</span>
							<InputText v-model="group.__pin" :list="listId(draft.pin_attr)" placeholder="any" :data-testid="`fp-when-${groupIndex}`" />
						</div>
					</div>
					<Button :label="draft.change_attrs.length > 1 ? 'Another combination' : 'Another transition'" icon="pi pi-plus" text severity="secondary" size="small" data-testid="fp-add-group" @click="draft.groups.push(blankGroup(draft.change_attrs))" />
				</section>
				<section class="ipd-fp-panel">
					<h4 class="ipd-fp-panel__head">Hold (pin) an attribute — optional</h4>
					<p class="erp-help-text">Attributes you don't mention carry through unchanged. Holding an attribute limits each transition to one value of it, entered per transition (blank = any).</p>
					<div class="ipd-cloth-dialog__field ipd-fp-narrow">
						<label class="erp-field-label" for="ipd-fp-pin">Hold attribute</label>
						<Select v-model="draft.pin_attr" input-id="ipd-fp-pin" :options="pinOptions" option-label="label" option-value="value" fluid @change="onPinChange" />
					</div>
				</section>
			</template>

			<p v-else class="ipd-cloth-strip ipd-cloth-strip--info">Nothing — pass-through. The item is unchanged and no matrix is built.</p>

			<Message v-if="problem" severity="warn" :closable="false">{{ problem }}</Message>
			<datalist v-for="(values, attribute) in valueOptions" :id="listId(attribute)" :key="attribute">
				<option v-for="value in values" :key="value" :value="value" />
			</datalist>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text data-testid="fp-cancel" @click="emit('cancel')" />
			<Button label="Save step" icon="pi pi-check" data-testid="fp-save-step" :disabled="Boolean(problem)" @click="emit('save')" />
		</template>
	</Dialog>
</template>

<script setup>
import { computed, watch } from "vue"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"

import LinkField from "../../../../components/common/LinkField.vue"
import { addChip, blankGroup, blankRule, draftProblem, introduceCombinationCount, usesInputRecipe } from "./fabricProcessDraft.js"

const props = defineProps({
	draft: { type: Object, default: null },
	item: { type: String, default: "" },
	conversionInputs: { type: Array, default: () => [] },
	attributes: { type: Array, default: () => [] },
	valueOptions: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["save", "cancel", "need-values"])

const context = computed(() => ({ item: props.item, conversionInputs: props.conversionInputs }))
const recipe = computed(() => usesInputRecipe(props.draft, props.item))
const recipeLabel = computed(() => props.conversionInputs.map((row) => `${row.item} ${Number(row.ratio || 0)}%`).join(" + "))
const inputLabel = computed(() => (recipe.value ? recipeLabel.value : props.draft?.input_item || props.draft?.output_item) || "(pick input)")
const problem = computed(() => (props.draft ? draftProblem(props.draft, context.value) : ""))
const combinationCount = computed(() => (props.draft ? introduceCombinationCount(props.draft) : 0))
const pinOptions = computed(() => [{ label: "(hold nothing)", value: "" }, ...props.attributes.filter((attribute) => !props.draft?.change_attrs.includes(attribute)).map((attribute) => ({ label: attribute, value: attribute }))])
const badge = computed(() => {
	const draft = props.draft
	if (draft?.shapeKey === "conv") return { key: "conv", label: "Item conversion" }
	if (draft?.shapeKey === "change") return draft.change_attrs.length > 1 ? { key: "combo", label: "Combination" } : { key: "swap", label: "Attribute swap" }
	return { key: "idle", label: "Identity" }
})

const listId = (attribute) => `ipd-fp-values-${String(attribute).replace(/\W+/g, "-")}`

function onPinChange() {
	props.draft.groups.forEach((group) => { group.__pin = "" })
	if (props.draft.pin_attr) emit("need-values", [props.draft.pin_attr])
}

watch(() => props.draft, (draft) => {
	if (!draft) return
	emit("need-values", [...draft.introduce.map((entry) => entry.attr), ...draft.consume_attrs, ...draft.change_attrs, draft.pin_attr].filter(Boolean))
})
</script>
