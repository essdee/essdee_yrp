/** Dia × Colour layout for the fabric deliverables popup, shared by Desk and /web. Cells point at qty_rows indexes; callers own the quantities. */

const STEPS = { Enter: [1, 0], ArrowDown: [1, 0], ArrowUp: [-1, 0], ArrowRight: [0, 1], ArrowLeft: [0, -1] }

function number(value) {
	return Number(value || 0)
}

function diaNumber(dia) {
	const parsed = parseFloat(dia)
	return Number.isNaN(parsed) ? Infinity : parsed
}

function diaShortName(dia) {
	return String(dia).match(/^[\d.]+/)?.[0] || dia
}

/** `{ get(index), set(index, value) }` over a plain array. */
export function arrayQuantities(values) {
	return { get: (index) => number(values[index]), set: (index, value) => { values[index] = number(value) } }
}

function inputTitle(qtyRow) {
	return (qtyRow.input_specs || []).map((spec) => spec.item).filter(Boolean).join(" + ")
}

function cellPosition(qtyRow, attributes) {
	const dia = qtyRow.out_attrs?.[attributes.dia]
	const colour = qtyRow.out_attrs?.[attributes.colour]
	if (!dia || !colour || (qtyRow.knitting_inputs || []).length) return null
	const planned = qtyRow.target_attrs?.[attributes.dia] || dia
	return { dia, planned, colour, substitute: planned !== dia }
}

function matrixRow(position) {
	const { dia, planned, substitute } = position
	return {
		key: substitute ? `${dia}|${planned}` : dia,
		label: substitute ? `${diaShortName(dia)} → ${planned}` : dia,
		dia, planned, substitute, selected: true,
	}
}

function emptyMatrix(title) {
	return { title, columns: [], rows: [], cells: {}, pools: {} }
}

function addCell(matrix, position, qtyRow, index) {
	const candidate = matrixRow(position)
	const row = rowByKey(matrix, candidate.key) || candidate
	if (row === candidate) matrix.rows.push(row)
	if (!columnByKey(matrix, position.colour)) matrix.columns.push({ key: position.colour, label: position.colour, selected: true })
	matrix.cells[row.key] ||= {}
	if (matrix.cells[row.key][position.colour] !== undefined) return false
	matrix.cells[row.key][position.colour] = index
	const available = qtyRow.source_available ?? qtyRow.available
	if (available != null) matrix.pools[index] = { key: qtyRow.source_pool_key || `row:${row.key}`, available: number(available) }
	return true
}

function compareRows(left, right) {
	return diaNumber(left.planned) - diaNumber(right.planned)
		|| String(left.planned).localeCompare(String(right.planned), undefined, { numeric: true })
		|| Number(left.substitute) - Number(right.substitute)
		|| diaNumber(left.dia) - diaNumber(right.dia)
}

/** The row's stock when every cell draws from one pool (dyeing greige); null for per-colour stock. */
function sharedRowAvailable(matrix, row) {
	const pools = Object.values(matrix.cells[row.key]).map((index) => matrix.pools[index])
	const keys = new Set(pools.map((pool) => pool?.key))
	return keys.size === 1 && pools[0] ? pools[0].available : null
}

function finishMatrix(matrix) {
	matrix.rows.sort(compareRows)
	for (const row of matrix.rows) row.available = sharedRowAvailable(matrix, row)
	return matrix
}

/** One matrix per input item, or null when any row cannot map to a single Dia × Colour cell. */
export function buildFabricMatrices(qtyRows, attributes) {
	if (!attributes?.dia || !attributes?.colour || !(qtyRows || []).length) return null
	const matrices = new Map()
	for (const [index, qtyRow] of qtyRows.entries()) {
		const position = cellPosition(qtyRow, attributes)
		if (!position) return null
		const title = inputTitle(qtyRow)
		if (!matrices.has(title)) matrices.set(title, emptyMatrix(title))
		if (!addCell(matrices.get(title), position, qtyRow, index)) return null
	}
	return [...matrices.values()].map(finishMatrix)
}

export function matrixCellIndex(matrix, rowKey, columnKey) {
	return matrix.cells[rowKey]?.[columnKey]
}

function rowByKey(matrix, rowKey) {
	return matrix.rows.find((row) => row.key === rowKey)
}

function columnByKey(matrix, columnKey) {
	return matrix.columns.find((column) => column.key === columnKey)
}

export function isMatrixCellEnabled(matrix, rowKey, columnKey) {
	if (matrixCellIndex(matrix, rowKey, columnKey) === undefined) return false
	return Boolean(rowByKey(matrix, rowKey)?.selected && columnByKey(matrix, columnKey)?.selected)
}

function zeroCells(matrix, quantities, rowKeys, columnKeys) {
	for (const rowKey of rowKeys) {
		for (const columnKey of columnKeys) {
			const index = matrixCellIndex(matrix, rowKey, columnKey)
			if (index !== undefined) quantities.set(index, 0)
		}
	}
}

const allColumnKeys = (matrix) => matrix.columns.map((column) => column.key)
const allRowKeys = (matrix) => matrix.rows.map((row) => row.key)

/** Unticking zeroes the row's cells; reticking only re-enables them. */
export function setMatrixRowSelected(matrix, rowKey, selected, quantities) {
	rowByKey(matrix, rowKey).selected = selected
	if (!selected) zeroCells(matrix, quantities, [rowKey], allColumnKeys(matrix))
}

export function setMatrixColumnSelected(matrix, columnKey, selected, quantities) {
	columnByKey(matrix, columnKey).selected = selected
	if (!selected) zeroCells(matrix, quantities, allRowKeys(matrix), [columnKey])
}

export function setMatrixAllSelected(matrix, selected, quantities) {
	for (const row of matrix.rows) row.selected = selected
	for (const column of matrix.columns) column.selected = selected
	if (!selected) zeroCells(matrix, quantities, allRowKeys(matrix), allColumnKeys(matrix))
}

export function isMatrixAllSelected(matrix) {
	return matrix.rows.every((row) => row.selected) && matrix.columns.every((column) => column.selected)
}

function forEachCell(matrix, callback) {
	for (const row of matrix.rows) {
		for (const column of matrix.columns) {
			const index = matrixCellIndex(matrix, row.key, column.key)
			if (index !== undefined) callback(row, column, index)
		}
	}
}

/** Fill Quantity: enabled cells take `values[index]`, the rest stay zero. */
export function fillMatrix(matrix, quantities, values) {
	forEachCell(matrix, (row, column, index) => {
		quantities.set(index, row.selected && column.selected ? number(values[index]) : 0)
	})
}

/** Copies ticks from `source` by Dia/colour key and zeroes the cells that end up unticked. */
export function carryMatrixSelection(target, source, quantities) {
	for (const row of target.rows) row.selected = rowByKey(source, row.key)?.selected ?? true
	for (const column of target.columns) column.selected = columnByKey(source, column.key)?.selected ?? true
	forEachCell(target, (row, column, index) => {
		if (!row.selected || !column.selected) quantities.set(index, 0)
	})
}

/** Live totals over the current quantities. */
export function matrixTotals(matrix, quantities) {
	const rows = Object.fromEntries(matrix.rows.map((row) => [row.key, 0]))
	const columns = Object.fromEntries(matrix.columns.map((column) => [column.key, 0]))
	let grand = 0
	forEachCell(matrix, (row, column, index) => {
		const qty = quantities.get(index)
		rows[row.key] += qty
		columns[column.key] += qty
		grand += qty
	})
	return { rows, columns, grand }
}

/** Next enabled cell for Enter/arrow navigation, or null at the edge. */
export function moveMatrixFocus(matrix, rowKey, columnKey, key) {
	const step = STEPS[key]
	if (!step) return null
	let rowIndex = matrix.rows.findIndex((row) => row.key === rowKey) + step[0]
	let columnIndex = matrix.columns.findIndex((column) => column.key === columnKey) + step[1]
	while (matrix.rows[rowIndex] && matrix.columns[columnIndex]) {
		const next = { rowKey: matrix.rows[rowIndex].key, columnKey: matrix.columns[columnIndex].key }
		if (isMatrixCellEnabled(matrix, next.rowKey, next.columnKey)) return next
		rowIndex += step[0]
		columnIndex += step[1]
	}
	return null
}
