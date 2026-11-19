<template>
	<section class="ipd-approval__card" :class="[`is-${state}`, { 'is-wide': wide }]" :data-section="section.key">
		<header>
			<span class="ipd-approval__number">{{ number }}</span>
			<h3>{{ section.label }}</h3>
			<span v-if="section.key === 'weight'" class="ipd-approval__tag is-accent">Weight defined by: {{ weightBasis(data) }}</span>
			<span class="ipd-approval__tag">{{ sectionCount(section) }}</span>
			<i v-if="state === 'ok'" class="pi pi-check-circle ipd-approval__ok" aria-label="No warnings" />
		</header>
		<IpdApprovalAlerts :warnings="warningsFor(warnings, section.key)" />
		<div class="ipd-approval__card-body">
			<template v-if="section.key === 'colours'">
				<div class="ipd-approval__chips"><span v-for="colour in data.packing" :key="colour" class="ipd-approval__chip">{{ colour }}</span></div>
				<table v-if="data.set_combos.length" class="erp-data-table ipd-approval__table">
					<thead><tr><th scope="col">{{ attributes.packing }}</th><th v-for="part in attributes.set_parts" :key="part" scope="col">{{ part }}</th></tr></thead>
					<tbody><tr v-for="combo in data.set_combos" :key="combo.major"><td>{{ combo.major }}</td><td v-for="part in attributes.set_parts" :key="part">{{ combo.parts[part] }}</td></tr></tbody>
				</table>
				<p v-if="data.contrast_panels.length" class="ipd-approval__line">Contrast panels: {{ contrastText }}</p>
				<table class="erp-data-table ipd-approval__table">
					<thead><tr><th scope="col">Cloth</th><th scope="col">Item</th><th scope="col" class="is-number">GSM</th></tr></thead>
					<tbody><tr v-for="cloth in data.cloths" :key="cloth.name"><td><strong>{{ cloth.name }}</strong></td><td>{{ cloth.cloth }}</td><td class="is-number">{{ cloth.gsm || "—" }}</td></tr></tbody>
				</table>
			</template>
			<template v-else-if="section.key === 'panels'">
				<div v-for="group in panelsByPart(data, attributes)" :key="group.part" class="ipd-approval__part">
					<div v-if="group.part" class="ipd-approval__part-label">{{ group.part }} <span class="ipd-approval__subtle">· {{ group.pieces }} pieces</span></div>
					<div class="ipd-approval__chips">
						<span v-for="panel in group.panels" :key="panel.panel" class="ipd-approval__chip"><strong>{{ panel.panel }}</strong> ×{{ panel.qty }}<span class="ipd-approval__subtle">{{ panel.cloth.join(", ") }}</span></span>
					</div>
				</div>
			</template>
			<IpdApprovalWeight v-else-if="section.key === 'weight'" :weight="data" :colours="attributes.colours || []" />
			<template v-else-if="section.key === 'cloth_accessories'">
				<p v-if="!data.length" class="ipd-approval__empty">No cloth accessories.</p>
				<table v-else class="erp-data-table ipd-approval__table">
					<thead><tr><th scope="col">Accessory</th><th v-if="attributes.is_set_item" scope="col">Part</th><th scope="col">Weight / piece</th><th scope="col">Colour · cloth</th></tr></thead>
					<tbody>
						<tr v-for="accessory in clothAccessories" :key="accessory.name">
							<td><strong>{{ accessory.name }}</strong></td>
							<td v-if="attributes.is_set_item">{{ accessory.part }}</td>
							<td>
								<span v-if="accessory.weight.missing" class="ipd-approval__tag is-danger">no weight</span>
								<template v-else-if="accessory.weight.single"><strong>{{ accessory.weight.single }}</strong> <span class="ipd-approval__subtle">{{ accessory.weight.note }}</span></template>
								<template v-else><span v-for="row in accessory.weight.list" :key="row.key" class="ipd-approval__pair">{{ row.key }} <strong>{{ row.weight }}</strong></span> <span class="ipd-approval__subtle">· {{ accessory.weight.note }}</span></template>
							</td>
							<td>
								<span v-if="accessory.colourView.empty" class="ipd-approval__subtle">—</span>
								<template v-else-if="accessory.colourView.sameAsGarment">Same as garment colour <span class="ipd-approval__subtle">· {{ accessory.colourView.cloths }}</span></template>
								<template v-else>
									<div class="ipd-approval__chips"><span v-for="(row, index) in accessory.colourView.colours" :key="index" class="ipd-approval__chip">{{ row.major }} → {{ row.colour }}</span></div>
									<div class="ipd-approval__subtle">Cloth: {{ accessory.colourView.cloths }}</div>
								</template>
							</td>
						</tr>
					</tbody>
				</table>
			</template>
			<template v-else-if="section.key === 'accessories'">
				<p v-if="!data.length" class="ipd-approval__empty">No accessories on this IPD.</p>
				<table v-else class="erp-data-table ipd-approval__table">
					<thead><tr><th scope="col">Item</th><th scope="col">Process · stage</th><th scope="col" class="is-number">Qty / piece</th><th scope="col">By colour / size</th></tr></thead>
					<tbody>
						<tr v-for="(accessory, index) in accessories" :key="index">
							<td>{{ accessory.item }}</td>
							<td>{{ accessory.process }}<div class="ipd-approval__subtle">{{ accessory.stage }}</div></td>
							<td class="is-number">{{ perPiece(accessory) }}<div v-if="accessory.wastage_pct" class="ipd-approval__subtle">+{{ accessory.wastage_pct }}% wastage</div></td>
							<td>
								<span v-if="!accessory.mapped" class="ipd-approval__subtle">Same for all</span>
								<span v-else-if="!accessory.mapping?.summary.length" class="ipd-approval__tag is-warning">No mapping rows</span>
								<template v-else>
									<div v-for="(line, lineIndex) in accessory.mappingView.lines" :key="lineIndex"><strong>{{ line.bom }}</strong> {{ line.quantity }} <span class="ipd-approval__subtle">for</span> {{ line.for }}</div>
									<div v-if="accessory.mappingView.more" class="ipd-approval__subtle">+{{ accessory.mappingView.more }} more lines</div>
									<div v-if="accessory.mappingView.same" class="ipd-approval__subtle">{{ accessory.mappingView.same }} follows garment</div>
								</template>
							</td>
						</tr>
					</tbody>
				</table>
			</template>
			<template v-else-if="section.key === 'embellishment'">
				<p v-if="!data.embellishments.length" class="ipd-approval__empty">No embellishment on panels.</p>
				<table v-else class="erp-data-table ipd-approval__table">
					<thead><tr><th scope="col">Process</th><th scope="col">On {{ attributes.panel.toLowerCase() }}s</th><th scope="col">Stage</th><th scope="col">Accessories used</th></tr></thead>
					<tbody>
						<tr v-for="row in data.embellishments" :key="row.process">
							<td><strong>{{ row.process }}</strong></td>
							<td><div class="ipd-approval__chips"><span v-for="panel in row.panels" :key="panel" class="ipd-approval__chip">{{ panel }}</span></div></td>
							<td><span v-if="row.stage">{{ row.stage }}</span><span v-else class="ipd-approval__tag is-warning">not in list</span></td>
							<td class="ipd-approval__muted"><div v-for="item in row.accessories" :key="item">{{ item }}</div><span v-if="!row.accessories.length">—</span></td>
						</tr>
					</tbody>
				</table>
				<p v-if="data.other_processes.length" class="ipd-approval__line"><span class="ipd-approval__muted">Other processes:</span> {{ data.other_processes.map((row) => `${row.process} (${row.stage})`).join(", ") }}</p>
				<p class="ipd-approval__line ipd-approval__muted">Flow: {{ processFlow(data.core_processes) }}</p>
			</template>
		</div>
	</section>
</template>

<script setup>
import { computed } from "vue"

import IpdApprovalAlerts from "./IpdApprovalAlerts.vue"
import IpdApprovalWeight from "./IpdApprovalWeight.vue"
import {
	clothAccessoryColours, clothAccessoryWeight, mappingLines, panelsByPart, perPiece, processFlow,
	sectionCount, sectionState, warningsFor, weightBasis,
} from "./ipdApproval.js"

const props = defineProps({
	number: { type: Number, required: true },
	section: { type: Object, required: true },
	warnings: { type: Array, default: () => [] },
	attributes: { type: Object, default: () => ({}) },
})
const data = computed(() => props.section.data)
const state = computed(() => sectionState(props.warnings, props.section.key))
const wide = computed(() => !["colours", "panels"].includes(props.section.key))
const clothAccessories = computed(() => props.section.key === "cloth_accessories"
	? data.value.map((accessory) => ({ ...accessory, weight: clothAccessoryWeight(accessory), colourView: clothAccessoryColours(accessory) }))
	: [])
const accessories = computed(() => props.section.key === "accessories"
	? data.value.map((accessory) => ({ ...accessory, mappingView: mappingLines(accessory) }))
	: [])
const contrastText = computed(() => (data.value.contrast_panels || [])
	.map((row) => `${row.major}: ${Object.entries(row.panels).map(([panel, colour]) => `${panel} ${colour}`).join(", ")}`)
	.join("; "))
</script>
