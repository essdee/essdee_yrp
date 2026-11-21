export const NEW_ROW_PREFIX = "new:"
export const COMPACTING_SCOPES = ["All Colours", "Separate Colours", "Colour Group"]

const PAIR_SEPARATOR = "\u0000"
const isBlank = (value) => value === null || value === undefined || value === ""
const byNatural = (left, right) => String(left ?? "").localeCompare(String(right ?? ""), undefined, { numeric: true })

export function rowKey(row, index) {
	return row?.name || `${NEW_ROW_PREFIX}${index}`
}

export function rowsToModel(rows = [], fields = []) {
	return Object.fromEntries((rows || []).map((row, index) => [rowKey(row, index), Object.fromEntries(fields.map((field) => [field, row[field] ?? null]))]))
}

export function modelToRows(rows = [], model = {}, fields = []) {
	return (rows || []).map((row, index) => {
		const cells = model[rowKey(row, index)]
		const changed = fields.filter((field) => cells && field in cells && (cells[field] ?? null) !== (row[field] ?? null))
		if (!changed.length) return row
		const next = { ...row }
		for (const field of changed) next[field] = cells[field]
		return next
	})
}

export function removeRow(rows = [], key) {
	return (rows || []).filter((row, index) => rowKey(row, index) !== key)
}

export function gridRows(rows = [], label) {
	return (rows || []).map((row, index) => ({ key: rowKey(row, index), label: label(row, index) }))
}

export function ratioTotal(rows = []) {
	return Math.round((rows || []).reduce((total, row) => total + (Number(row?.ratio) || 0), 0) * 1000) / 1000
}

export function nextSequence(processes = []) {
	const sequences = (processes || []).map((row) => Number(row.sequence) || 0).filter((value) => value > 0)
	return sequences.length ? Math.max(...sequences) + 10 : 10
}

export function sortBySequence(rows = [], fields = ["sequence"]) {
	return (rows || []).map((row, index) => ({ row, index })).sort((left, right) => {
		for (const field of fields) {
			const delta = (Number(left.row[field]) || 0) - (Number(right.row[field]) || 0)
			if (delta) return delta
		}
		return left.index - right.index
	}).map((entry) => entry.row)
}

export function removeProcess(processes = [], mappings = [], key) {
	const target = (processes || []).find((row, index) => rowKey(row, index) === key)
	const sequence = Number(target?.sequence)
	const shared = (processes || []).filter((row) => Number(row.sequence) === sequence).length > 1
	return resequenceProcesses(
		sortBySequence(removeRow(processes, key)),
		target && !shared ? (mappings || []).filter((row) => Number(row.sequence) !== sequence) : mappings,
	)
}

export function resequenceProcesses(processes = [], mappings = []) {
	const renumbered = new Map()
	const nextProcesses = (processes || []).map((row, index) => {
		const sequence = (index + 1) * 10
		if (!renumbered.has(Number(row.sequence))) renumbered.set(Number(row.sequence), sequence)
		return Number(row.sequence) === sequence ? row : { ...row, sequence }
	})
	const nextMappings = (mappings || []).map((row) => {
		const sequence = renumbered.get(Number(row.sequence))
		return sequence === undefined || sequence === Number(row.sequence) ? row : { ...row, sequence }
	})
	return { processes: nextProcesses, mappings: sortBySequence(nextMappings, ["sequence", "mapping_index"]) }
}

function movedProcesses(processes, index, direction) {
	const ordered = sortBySequence(processes)
	const target = index + direction
	if (index < 0 || target < 0 || target >= ordered.length) return null
	const [row] = ordered.splice(index, 1)
	ordered.splice(target, 0, row)
	return ordered
}

export function canMoveProcess(processes = [], index, direction) {
	const ordered = movedProcesses(processes || [], index, direction)
	return Boolean(ordered) && ordered.every((row, position) => {
		const previousOutput = ordered[position - 1]?.output_item
		return !previousOutput || !row.input_item || previousOutput === row.input_item
	})
}

export function moveProcess(processes = [], mappings = [], index, direction) {
	if (!canMoveProcess(processes, index, direction)) return { processes, mappings }
	return resequenceProcesses(movedProcesses(processes, index, direction), mappings)
}

function mappingGroups(mappings = []) {
	const groups = new Map()
	for (const row of mappings || []) {
		const key = `${row.sequence || 0}${PAIR_SEPARATOR}${row.mapping_index || 0}`
		if (!groups.has(key)) groups.set(key, [])
		groups.get(key).push(row)
	}
	return [...groups.values()]
}

function mappingPairs(draft, { colourAttribute, diaAttribute }, addPair) {
	const mappings = draft.fabric_value_mappings || []
	const introducedDias = [...new Set(mappings.filter((row) => row.attribute === diaAttribute && row.role === "Introduce").map((row) => row.to_value).filter(Boolean))]
	for (const rows of mappingGroups(mappings)) {
		const colourEntry = rows.find((row) => row.attribute === colourAttribute && ["Change", "Introduce"].includes(row.role))
		const diaEntry = rows.find((row) => row.attribute === diaAttribute && ["Change", "Pin", "Introduce"].includes(row.role))
		const colour = colourEntry?.to_value || colourEntry?.from_value || ""
		const dia = diaEntry?.to_value || diaEntry?.from_value || ""
		if (colour && dia) addPair(colour, dia)
		else if (colour) introducedDias.forEach((value) => addPair(colour, value))
	}
	return introducedDias
}

export function compactingRoutePairs(draft = {}, attributes = {}) {
	const seen = new Set()
	const pairs = []
	const addPair = (colour, inputDia) => {
		if (!colour || !inputDia) return
		const key = `${colour}${PAIR_SEPARATOR}${inputDia}`
		if (seen.has(key)) return
		seen.add(key)
		pairs.push({ colour, input_dia: inputDia })
	}
	for (const row of draft.fabric_routes || []) addPair(row.finished_colour || "", row.finished_dia || "")
	if (!pairs.length) {
		const introducedDias = mappingPairs(draft, attributes, addPair)
		if (!pairs.length) {
			const recipeColours = [...new Set((draft.colour_yarn_recipes || []).map((row) => row.colour).filter(Boolean))]
			recipeColours.forEach((colour) => introducedDias.forEach((dia) => addPair(colour, dia)))
		}
	}
	return pairs.sort((left, right) => byNatural(left.input_dia, right.input_dia) || byNatural(left.colour, right.colour))
}

export function pairColours(pairs = []) {
	return [...new Set(pairs.map((pair) => pair.colour))].sort(byNatural)
}

export function compactingTargets(pairs = [], scope = "All Colours", selectedColours = []) {
	if (scope === "All Colours") return [...new Set(pairs.map((pair) => pair.input_dia))].map((inputDia) => ({ colour: "", input_dia: inputDia }))
	if (scope === "Colour Group") {
		const selected = new Set(selectedColours)
		return pairs.filter((pair) => selected.has(pair.colour))
	}
	return pairs
}

const compactingKey = (row) => `${row.colour || ""}${PAIR_SEPARATOR}${row.input_dia || ""}`

export function addCompactingTargets(rows = [], targets = []) {
	const existing = new Set((rows || []).map(compactingKey))
	const added = []
	for (const target of targets) {
		const key = compactingKey(target)
		if (existing.has(key)) continue
		existing.add(key)
		added.push({ colour: target.colour || null, input_dia: target.input_dia, compacting_dia: null, notes: null })
	}
	return { rows: [...(rows || []), ...added], added: added.length }
}

export function compactingInputDias(rows = []) {
	return [...new Set((rows || []).map((row) => row.input_dia).filter(Boolean))].sort(byNatural)
}

export function fillCompactingDia(rows = [], keys = [], compactingDia) {
	const wanted = new Set(keys)
	const selected = (rows || []).filter((row, index) => wanted.has(rowKey(row, index)))
	if (!selected.length) return { rows, updated: 0, error: "Select the rows to fill." }
	if (new Set(selected.map((row) => row.input_dia).filter(Boolean)).size !== 1) {
		return { rows, updated: 0, error: "Select rows sharing the same Knitting/Input Dia." }
	}
	if (isBlank(compactingDia)) return { rows, updated: 0, error: "Choose the Compacting Dia." }
	const next = (rows || []).map((row, index) => (wanted.has(rowKey(row, index)) ? { ...row, compacting_dia: compactingDia } : row))
	return { rows: next, updated: selected.length, error: "" }
}

export function withStoredOptions(options = [], rows = [], fields = []) {
	const values = new Set(options)
	const extra = []
	for (const row of rows || []) {
		for (const field of fields) {
			const value = row?.[field]
			if (!isBlank(value) && !values.has(value)) { values.add(value); extra.push(value) }
		}
	}
	return extra.length ? [...options, ...extra] : options
}
