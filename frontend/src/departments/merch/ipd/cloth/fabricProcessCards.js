/** Fabric Process card display, mirrored from Desk public/js/Fabric/FabricProcesses.vue. */
import { rowKey, sortBySequence } from "./clothGrids.js"

const num = (value) => (value == null || value === "" ? 0 : Number(value))
const SEP_A = "\u0001"
const SEP_B = "\u0002"

export function escapeHtml(value) {
	return String(value == null ? "" : value)
		.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;").replace(/'/g, "&#39;")
}
const esc = escapeHtml
const muted = (html) => `<span class="ipd-fp-muted">${html}</span>`

/** Groups stored rows into ordered steps, each carrying its own value mappings. */
export function buildSteps(processes = [], mappings = []) {
	const keyed = (processes || []).map((row, index) => ({ ...row, __key: rowKey(row, index) }))
	return sortBySequence(keyed).map((row) => ({
		key: row.__key,
		name: row.name || null,
		sequence: num(row.sequence),
		fabric_process: row.fabric_process || "",
		input_item: row.input_item || "",
		output_item: row.output_item || "",
		quantity_ratio: row.quantity_ratio == null ? 1 : Number(row.quantity_ratio),
		mappings: (mappings || [])
			.filter((mapping) => num(mapping.sequence) === num(row.sequence))
			.sort((left, right) => num(left.mapping_index) - num(right.mapping_index))
			.map((mapping) => ({
				...(mapping.name ? { name: mapping.name } : {}),
				mapping_index: num(mapping.mapping_index),
				attribute: mapping.attribute || "",
				role: mapping.role || "Change",
				from_value: mapping.from_value || "",
				to_value: mapping.to_value || "",
			})),
	}))
}

export function hasConversion(step) {
	return Boolean(step.input_item && step.output_item && step.input_item !== step.output_item)
}

export function shapeOf(step) {
	const roles = new Set(step.mappings.map((row) => row.role))
	const changeAttributes = new Set(step.mappings.filter((row) => row.role === "Change").map((row) => row.attribute))
	if (roles.has("Introduce") || roles.has("Consume") || hasConversion(step)) return { key: "conv", label: "Item conversion" }
	if (changeAttributes.size > 1) return { key: "combo", label: "Combination" }
	if (changeAttributes.size === 1) return { key: "swap", label: "Attribute swap" }
	return { key: "idle", label: "Identity" }
}

/** Shows the cloth recipe ("Yarn A 60% + Yarn B 40%") when the step produces the IPD item. */
export function inputItemLabel(step, item, conversionInputs = []) {
	const inputs = (conversionInputs || []).filter((row) => row?.item)
	if (step.output_item === item && hasConversion(step) && inputs.length) {
		return inputs.map((row) => `${row.item} ${Number(row.ratio || 0)}%`).join(" + ")
	}
	return step.input_item || step.output_item || "(pick input)"
}

export function ratioLabel(step) {
	const ratio = Number(step.quantity_ratio)
	return ratio && ratio !== 1 ? `×${ratio} out/in` : ""
}

/** Joins values with " · ", writing a shared trailing word once ("30 · 24 Dia"). Returns HTML. */
export function joinValues(values) {
	const parts = values.map((value) => String(value == null ? "" : value).split(" "))
	if (values.length > 1 && parts.every((part) => part.length > 1)) {
		const suffix = parts[0].at(-1)
		if (suffix && parts.every((part) => part.at(-1) === suffix)) {
			return parts.map((part) => esc(part.slice(0, -1).join(" "))).join(" · ") + " " + esc(suffix)
		}
	}
	return values.map(esc).join(" · ")
}

export function capItems(items, max = 4) {
	if (items.length <= max) return items.join(" ; ")
	return items.slice(0, max).join(" ; ") + " " + muted(`+${items.length - max} more`)
}

function groupByIndex(mappings, keep = () => true) {
	const groups = new Map()
	for (const row of mappings) {
		if (!keep(row)) continue
		if (!groups.has(row.mapping_index)) groups.set(row.mapping_index, [])
		groups.get(row.mapping_index).push(row)
	}
	return [...groups.entries()].sort((left, right) => num(left[0]) - num(right[0])).map((entry) => entry[1])
}

function introduceParts(step) {
	const byAttribute = new Map()
	step.mappings.filter((row) => row.role === "Introduce" && row.to_value).forEach((row) => {
		if (!byAttribute.has(row.attribute)) byAttribute.set(row.attribute, [])
		const values = byAttribute.get(row.attribute)
		if (!values.includes(row.to_value)) values.push(row.to_value)
	})
	return [...byAttribute.entries()].map(([attribute, values]) => `<b>${esc(attribute)}</b>: ${joinValues(values)}`)
}

function varyingIntroduceAttribute(batch) {
	const attributes = batch[0].intros.map((entry) => entry.attr)
	if (!attributes.length) return null
	const sameShape = batch.every((rule) => rule.intros.length === attributes.length && rule.intros.every((entry, index) => entry.attr === attributes[index]))
	if (!sameShape) return null
	const varying = attributes.filter((attribute, index) => batch.some((rule) => rule.intros[index].val !== batch[0].intros[index].val))
	return varying.length === 1 ? varying[0] : null
}

function ruleText(consumed, rightParts) {
	const left = consumed.map((entry) => esc(entry.val || "—")).join(" · ")
	return rightParts.length ? `${left} → ${rightParts.join(" · ")}` : `${left} → ${muted("dropped")}`
}

function mergedRuleText(batch, varying) {
	const rightParts = []
	batch[0].intros.forEach((entry, index) => {
		if (entry.attr === varying) {
			const values = []
			batch.forEach((rule) => { const value = rule.intros[index].val || "—"; if (!values.includes(value)) values.push(value) })
			rightParts.push(joinValues(values))
		} else if (!batch[0].cons.some((consumed) => consumed.attr === entry.attr && consumed.val === entry.val)) {
			rightParts.push(esc(entry.val || "—"))
		}
	})
	return ruleText(batch[0].cons, rightParts)
}

/** Consume rules sharing one consumed side and varying in one introduced attribute merge into one line. */
function consumeRuleTexts(step) {
	const bySide = new Map()
	for (const rows of groupByIndex(step.mappings, (row) => row.role === "Consume" || row.role === "Introduce")) {
		const cons = rows.filter((row) => row.role === "Consume").map((row) => ({ attr: row.attribute, val: row.from_value || "" }))
		if (!cons.length) continue
		const intros = rows.filter((row) => row.role === "Introduce").map((row) => ({ attr: row.attribute, val: row.to_value || "" }))
		const side = cons.map((entry) => entry.attr + SEP_A + entry.val).join(SEP_B)
		if (!bySide.has(side)) bySide.set(side, [])
		bySide.get(side).push({ cons, intros })
	}
	const texts = []
	for (const batch of bySide.values()) {
		const varying = batch.length > 1 ? varyingIntroduceAttribute(batch) : null
		if (varying) texts.push(mergedRuleText(batch, varying))
		else batch.forEach((rule) => texts.push(ruleText(rule.cons, rule.intros.map((entry) => esc(entry.val || "—")))))
	}
	return texts
}

function transitionText(changes, pinOrder, pinValues, join) {
	const attributes = changes.map((row) => esc(row.attribute)).join(" · ")
	const froms = changes.map((row) => esc(row.from_value || "—")).join(" · ")
	const tos = changes.map((row) => esc(row.to_value || "—")).join(" · ")
	const held = pinOrder.length ? " " + muted(`(held ${pinOrder.map((attribute) => esc(attribute) + " " + join(pinValues[attribute])).join(", ")})`) : ""
	return `<b>${attributes}</b>: ${froms} → ${tos}${held}`
}

/** Change groups with the same transition render once, their held values merged. */
function changeGroupTexts(step) {
	const aggregates = new Map()
	for (const rows of groupByIndex(step.mappings, (row) => row.role !== "Introduce")) {
		const changes = rows.filter((row) => row.role === "Change")
		if (!changes.length) continue
		const key = changes.map((row) => [row.attribute, row.from_value, row.to_value].join(SEP_A)).join(SEP_B)
		if (!aggregates.has(key)) aggregates.set(key, { changes, pinOrder: [], pinValues: {} })
		const aggregate = aggregates.get(key)
		rows.filter((row) => row.role === "Pin" && row.from_value).forEach((pin) => {
			if (!aggregate.pinValues[pin.attribute]) { aggregate.pinValues[pin.attribute] = []; aggregate.pinOrder.push(pin.attribute) }
			if (!aggregate.pinValues[pin.attribute].includes(pin.from_value)) aggregate.pinValues[pin.attribute].push(pin.from_value)
		})
	}
	return [...aggregates.values()].map((entry) => transitionText(entry.changes, entry.pinOrder, entry.pinValues, joinValues))
}

/** One-line "What changes" summary (HTML, values escaped). */
export function summaryOf(step) {
	const key = shapeOf(step).key
	if (key === "conv") {
		const rules = consumeRuleTexts(step)
		if (rules.length) return capItems(rules)
		const introduced = introduceParts(step)
		if (introduced.length) return `Introduces ${introduced.join("; ")}`
		return `Converts ${esc(step.input_item)} → ${esc(step.output_item)} ${muted("(no attribute change · no matrix)")}`
	}
	if (key === "combo") return `Together — ${capItems(changeGroupTexts(step))}`
	if (key === "swap") return capItems(changeGroupTexts(step))
	return muted("Nothing changes · no matrix")
}

function conversionDetail(rows) {
	const consumed = rows.filter((row) => row.role === "Consume")
	const introduced = rows.filter((row) => row.role === "Introduce")
	if (!consumed.length && !introduced.length) return null
	if (!consumed.length) return "Introduces " + introduced.map((row) => `<b>${esc(row.attribute)}</b> ${esc(row.to_value || "—")}`).join(" · ")
	const right = introduced.length ? introduced.map((row) => esc(row.to_value || "—")).join(" · ") : muted("dropped")
	return `${consumed.map((row) => esc(row.from_value || "—")).join(" · ")} → ${right}`
}

function changeDetail(rows) {
	const changes = rows.filter((row) => row.role === "Change")
	if (!changes.length) return null
	const pins = rows.filter((row) => row.role === "Pin" && row.from_value)
	const pinValues = Object.fromEntries(pins.map((pin) => [pin.attribute, pin.from_value]))
	return transitionText(changes, pins.map((pin) => pin.attribute), pinValues, esc)
}

/** Uncapped, unaggregated rows behind the summary: one per mapping group. */
export function combinationRows(step) {
	const detail = shapeOf(step).key === "conv" ? conversionDetail : changeDetail
	return groupByIndex(step.mappings).map(detail).filter(Boolean)
}

/** Flattens steps back into the two stored child tables, sequenced by tens. */
export function stepsToRows(steps = []) {
	const processes = []
	const mappings = []
	steps.forEach((step, index) => {
		const sequence = (index + 1) * 10
		processes.push({
			...(step.name ? { name: step.name } : {}),
			sequence,
			fabric_process: step.fabric_process,
			input_item: step.input_item || null,
			output_item: step.output_item || null,
			quantity_ratio: step.quantity_ratio == null ? 1 : step.quantity_ratio,
		})
		step.mappings.forEach((row) => mappings.push({ sequence, ...row, from_value: row.from_value || "", to_value: row.to_value || "" }))
	})
	return { processes, mappings }
}

export function availableProcesses(allProcesses = [], steps = []) {
	const used = new Set(steps.map((step) => step.fabric_process).filter(Boolean))
	return allProcesses.filter((process) => !used.has(process))
}
