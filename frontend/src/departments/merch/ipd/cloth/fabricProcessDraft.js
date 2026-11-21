/** Fabric Process define/edit draft, mirrored from Desk public/js/Fabric/FabricProcesses.vue. */
const num = (value) => (value == null || value === "" ? 0 : Number(value))
const unique = (values) => [...new Set(values)]

/** Maps get_process_transform's shape onto the editor kind: conv, change or idle. */
export function transformShape(transform = {}) {
	const key = transform.shape === "conversion" ? "conv" : ["swap", "multi_swap"].includes(transform.shape) ? "change" : "idle"
	return {
		key,
		change_attributes: (transform.change_attributes || []).filter(Boolean),
		input_attributes: (transform.input_attributes || []).filter(Boolean),
		output_attributes: (transform.output_attributes || []).filter(Boolean),
	}
}

export function blankRule(draft) {
	return {
		in: Object.fromEntries(draft.consume_attrs.map((attribute) => [attribute, ""])),
		out: Object.fromEntries(draft.introduce.map((entry) => [entry.attr, ""])),
	}
}

export function blankGroup(attributes = []) {
	return { ...Object.fromEntries(attributes.map((attribute) => [attribute, { from: "", to: "" }])), __pin: "" }
}

/** A new draft for `process`; `item` is the IPD cloth item, `defaultInput` its first yarn. */
export function blankDraft(process, sequence, shape, { item = "", defaultInput = "" } = {}) {
	const draft = {
		index: null,
		sequence,
		fabric_process: process,
		shapeKey: shape.key,
		input_item: shape.key === "conv" ? defaultInput || "" : item || "",
		output_item: item || "",
		quantity_ratio: 1,
		introduce: shape.output_attributes.map((attr) => ({ attr, chips: [], input: "" })),
		consume_attrs: [...shape.input_attributes],
		rules: [],
		change_attrs: [...shape.change_attributes],
		groups: [],
		pin_attr: "",
	}
	if (draft.shapeKey === "conv" && draft.consume_attrs.length) draft.rules = [blankRule(draft)]
	if (draft.shapeKey === "change") draft.groups = [blankGroup(draft.change_attrs)]
	return draft
}

function unconfigured(rows, allowed) {
	return unique(rows.filter((row) => allowed[row.role] && !allowed[row.role].has(row.attribute)).map((row) => row.attribute))
}

/** Why the editor cannot represent `step` without dropping data, or "" when it can. */
export function editRefusal(step, shape) {
	const roles = unique(step.mappings.map((row) => row.role))
	if (shape.key === "conv") {
		const representable = roles.includes("Consume") ? ["Consume", "Introduce"] : ["Introduce"]
		const foreign = roles.filter((role) => !representable.includes(role))
		if (foreign.length) return `This conversion step carries ${foreign.join(", ")} entries the editor cannot represent`
		const missing = unconfigured(step.mappings, { Consume: new Set(shape.input_attributes), Introduce: new Set(shape.output_attributes) })
		return missing.length ? `This step uses attributes not configured on its Process master (${missing.join(", ")})` : ""
	}
	if (shape.key === "change") {
		const missing = unconfigured(step.mappings, { Change: new Set(shape.change_attributes) })
		if (missing.length) return `This step changes attributes not configured on its Process master (${missing.join(", ")})`
		const pins = step.mappings.filter((row) => row.role === "Pin")
		const pinAttributes = unique(pins.map((row) => row.attribute))
		if (pinAttributes.length > 1) return `This step holds ${pinAttributes.length} different attributes across its rules (${pinAttributes.join(", ")})`
		const indexes = pins.map((row) => row.mapping_index)
		return new Set(indexes).size < indexes.length ? "This step carries more than one hold entry inside a single rule" : ""
	}
	return step.mappings.length ? "This step carries value-mapping entries the identity editor does not show" : ""
}

function mappingGroups(step) {
	const groups = new Map()
	step.mappings.forEach((row) => { if (!groups.has(row.mapping_index)) groups.set(row.mapping_index, []); groups.get(row.mapping_index).push(row) })
	return [...groups.entries()].sort((left, right) => num(left[0]) - num(right[0])).map((entry) => entry[1])
}

function fillConversion(draft, step, groups) {
	if (draft.consume_attrs.length) {
		draft.rules = groups.map((rows) => {
			const rule = { in: {}, out: {} }
			rows.forEach((row) => {
				if (row.role === "Consume") rule.in[row.attribute] = row.from_value || ""
				else if (row.role === "Introduce") rule.out[row.attribute] = row.to_value || ""
			})
			return rule
		})
		if (!draft.rules.length) draft.rules = [blankRule(draft)]
		return
	}
	draft.introduce.forEach((entry) => {
		entry.chips = unique(step.mappings.filter((row) => row.role === "Introduce" && row.attribute === entry.attr && row.to_value).map((row) => row.to_value))
	})
}

function fillChange(draft, step, groups) {
	draft.groups = groups.map((rows) => {
		const group = blankGroup(draft.change_attrs)
		draft.change_attrs.forEach((attribute) => {
			const change = rows.find((row) => row.role === "Change" && row.attribute === attribute)
			group[attribute] = { from: change?.from_value || "", to: change?.to_value || "" }
		})
		group.__pin = rows.find((row) => row.role === "Pin")?.from_value || ""
		return group
	})
	if (!draft.groups.length) draft.groups = [blankGroup(draft.change_attrs)]
	draft.pin_attr = step.mappings.find((row) => row.role === "Pin")?.attribute || ""
}

/** Reverses a stored step into an editor draft; returns { error } when it cannot be edited safely. */
export function draftFromStep(step, index, shape, context = {}) {
	const error = editRefusal(step, shape)
	if (error) return { error }
	const draft = blankDraft(step.fabric_process, step.sequence, shape, context)
	Object.assign(draft, { index, input_item: step.input_item, output_item: step.output_item, quantity_ratio: step.quantity_ratio })
	const groups = mappingGroups(step)
	if (shape.key === "conv") fillConversion(draft, step, groups)
	else if (shape.key === "change") fillChange(draft, step, groups)
	return { draft }
}

export function addChip(entry) {
	const value = (entry.input || "").trim()
	if (value && !entry.chips.includes(value)) entry.chips.push(value)
	entry.input = ""
}

export function isCompleteRule(draft, rule) {
	return draft.consume_attrs.every((attribute) => rule.in?.[attribute]) && draft.introduce.every((entry) => rule.out?.[entry.attr])
}

export function isCompleteGroup(draft, group) {
	return draft.change_attrs.every((attribute) => group[attribute]?.from && group[attribute]?.to)
}

export function introduceCombinationCount(draft) {
	const sizes = draft.introduce.filter((entry) => entry.chips.length).map((entry) => entry.chips.length)
	return sizes.length ? sizes.reduce((total, size) => total * size, 1) : 0
}

/** True when the conversion produces the IPD item, so its input is the Yarn Ratio recipe. */
export function usesInputRecipe(draft, item) {
	return Boolean(draft?.shapeKey === "conv" && draft.output_item && draft.output_item === item)
}

export function isRecipeValid(inputs = [], outputItem = "") {
	const items = inputs.map((row) => row.item).filter(Boolean)
	const total = Number(inputs.reduce((sum, row) => sum + Number(row.ratio || 0), 0).toFixed(3))
	return inputs.length > 0 && items.length === inputs.length && new Set(items).size === items.length
		&& inputs.every((row) => Number(row.ratio) > 0) && Math.abs(total - 100) <= 0.001 && !items.includes(outputItem)
}

/** Why the draft cannot be saved yet, or "" when it can. */
export function draftProblem(draft, { item = "", conversionInputs = [] } = {}) {
	if (draft.shapeKey === "change") {
		return draft.change_attrs.length && draft.groups.some((group) => isCompleteGroup(draft, group)) ? "" : "Fill from and to for every attribute in at least one transition."
	}
	if (draft.shapeKey !== "conv") return ""
	if (!draft.output_item) return "Pick the produced item."
	if (usesInputRecipe(draft, item)) {
		if (!isRecipeValid(conversionInputs, draft.output_item)) return "The Yarn Ratio must contain positive, unique inputs totalling exactly 100%."
	} else if (!draft.input_item) return "Pick the consumed item — a conversion needs a distinct input."
	else if (draft.input_item === draft.output_item) return "A conversion's input and output must be different items."
	if (draft.consume_attrs.length && !draft.rules.some((rule) => isCompleteRule(draft, rule))) return "Fill every value in at least one rule."
	return ""
}

export function crossProduct(lists) {
	return lists.reduce((combos, list) => combos.flatMap((combo) => list.map((value) => [...combo, value])), [[]])
}

function conversionMappings(draft) {
	if (draft.consume_attrs.length) {
		return draft.rules.filter((rule) => isCompleteRule(draft, rule)).flatMap((rule, index) => [
			...draft.consume_attrs.map((attribute) => ({ mapping_index: index, attribute, role: "Consume", from_value: rule.in[attribute], to_value: "" })),
			...draft.introduce.map((entry) => ({ mapping_index: index, attribute: entry.attr, role: "Introduce", from_value: "", to_value: rule.out[entry.attr] })),
		])
	}
	draft.introduce.forEach(addChip)
	const active = draft.introduce.filter((entry) => entry.chips.length)
	const combos = active.length ? crossProduct(active.map((entry) => entry.chips)) : []
	return combos.flatMap((combo, index) => active.map((entry, position) => ({ mapping_index: index, attribute: entry.attr, role: "Introduce", from_value: "", to_value: combo[position] })))
}

function changeMappings(draft) {
	return draft.groups.filter((group) => isCompleteGroup(draft, group)).flatMap((group, index) => [
		...draft.change_attrs.map((attribute) => ({ mapping_index: index, attribute, role: "Change", from_value: group[attribute].from, to_value: group[attribute].to })),
		...(draft.pin_attr ? [{ mapping_index: index, attribute: draft.pin_attr, role: "Pin", from_value: group.__pin || "", to_value: group.__pin || "" }] : []),
	])
}

/** Builds the stored step (process row + value mappings) from a saved draft. */
export function draftToStep(draft, { item = "", conversionInputs = [] } = {}) {
	const isConversion = draft.shapeKey === "conv"
	const inputItem = usesInputRecipe(draft, item) ? conversionInputs[0]?.item || "" : draft.input_item
	return {
		sequence: draft.sequence,
		fabric_process: draft.fabric_process,
		input_item: isConversion ? inputItem : item || draft.input_item || "",
		output_item: isConversion ? draft.output_item : item || "",
		quantity_ratio: isConversion ? Number(draft.quantity_ratio) || 1 : 1,
		mappings: isConversion ? conversionMappings(draft) : draft.shapeKey === "change" ? changeMappings(draft) : [],
	}
}
