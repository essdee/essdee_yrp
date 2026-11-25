import {
	arrayQuantities, buildFabricMatrices, carryMatrixSelection, isMatrixAllSelected, isMatrixCellEnabled,
	matrixCellIndex, matrixTotals, moveMatrixFocus, setMatrixAllSelected, setMatrixColumnSelected, setMatrixRowSelected,
} from "../../../frontend/src/departments/fabric-store/fabricMatrix.js";

const STYLE = `
.yrp-fabric-matrix { display: grid; gap: 6px; margin-bottom: 12px; }
.yrp-fabric-matrix__title { color: var(--text-muted); font-size: var(--text-sm); font-weight: 600; }
.yrp-fabric-matrix__wrap { overflow: auto; max-height: min(60vh, 560px); border: 1px solid var(--dark-border-color); border-radius: 8px; overscroll-behavior: contain; }
.yrp-fabric-matrix table { width: 100%; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; margin: 0; }
.yrp-fabric-matrix th, .yrp-fabric-matrix td { padding: 0; border-right: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); background: var(--fg-color); }
.yrp-fabric-matrix tr > :last-child { border-right: 0; }
.yrp-fabric-matrix thead th { position: sticky; top: 0; z-index: 2; padding: 8px 10px; background: var(--subtle-fg); color: var(--text-muted); font-weight: 500; text-align: right; white-space: nowrap; border-bottom-color: var(--dark-border-color); }
.yrp-fabric-matrix .yrp-fabric-matrix__dia { position: sticky; left: 0; z-index: 1; min-width: 104px; padding: 6px 10px; background: var(--subtle-fg); text-align: left; border-right-color: var(--dark-border-color); }
.yrp-fabric-matrix thead .yrp-fabric-matrix__dia, .yrp-fabric-matrix tfoot .yrp-fabric-matrix__dia { z-index: 3; }
.yrp-fabric-matrix label { display: inline-flex; align-items: center; gap: 6px; margin: 0; cursor: pointer; font-weight: inherit; }
.yrp-fabric-matrix input[type="checkbox"] { margin: 0; }
.yrp-fabric-matrix__dia-name { color: var(--text-color); font-weight: 600; white-space: nowrap; }
.yrp-fabric-matrix__avail { display: block; margin: 1px 0 0 20px; color: var(--text-muted); font-size: 11px; white-space: nowrap; }
.yrp-fabric-matrix__cell { min-width: 92px; }
.yrp-fabric-matrix__cell input { width: 100%; padding: 9px 10px; border: 0; outline: 0; background: transparent; color: var(--text-color); text-align: right; }
.yrp-fabric-matrix__cell input::placeholder { color: var(--text-light); opacity: 0.55; }
.yrp-fabric-matrix__cell:hover { background: var(--control-bg); }
.yrp-fabric-matrix__cell:focus-within { box-shadow: inset 0 0 0 2px var(--focus-default, var(--primary)); }
.yrp-fabric-matrix td.yrp-fabric-matrix__cell--na { background: repeating-linear-gradient(135deg, var(--subtle-fg) 0 6px, var(--fg-color) 6px 12px); }
.yrp-fabric-matrix td.yrp-fabric-matrix__cell--off { background: var(--subtle-fg); }
.yrp-fabric-matrix__cell--off input { color: var(--text-light); cursor: not-allowed; }
.yrp-fabric-matrix .yrp-fabric-matrix__off, .yrp-fabric-matrix__off .yrp-fabric-matrix__dia-name { color: var(--text-light); }
.yrp-fabric-matrix__total, .yrp-fabric-matrix tfoot td { min-width: 80px; padding: 8px 10px !important; text-align: right; color: var(--text-muted); font-weight: 500; white-space: nowrap; }
.yrp-fabric-matrix td.yrp-fabric-matrix__total--over { color: var(--red-600, #c62a2a); background: var(--red-50, #fdecec); }
.yrp-fabric-matrix tfoot th, .yrp-fabric-matrix tfoot td { position: sticky; bottom: 0; z-index: 2; background: var(--subtle-fg); border-top: 1px solid var(--dark-border-color); border-bottom: 0; }
.yrp-fabric-matrix tfoot .yrp-fabric-matrix__grand { color: var(--text-color); font-weight: 600; }
.yrp-fabric-matrix__hint { margin: 0; min-height: 18px; color: var(--red-600, #c62a2a); font-size: var(--text-sm); }
@media (max-width: 640px) { .yrp-fabric-matrix .yrp-fabric-matrix__dia { min-width: 84px; } .yrp-fabric-matrix__cell { min-width: 80px; } }
`;

const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
const display = (value) => Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 });

function checkbox(attributes, checked, label) {
	return `<input type="checkbox" ${attributes} ${checked ? "checked" : ""} aria-label="${escape(label)}">`;
}

function headHtml(matrix) {
	const columns = matrix.columns.map((column, index) => `<th class="${column.selected ? "" : "yrp-fabric-matrix__off"}">`
		+ `<label>${checkbox(`data-column-tick="${index}"`, column.selected, __("Use colour {0}", [column.label]))}${escape(column.label)}</label></th>`).join("");
	return `<tr><th class="yrp-fabric-matrix__dia"><label>${checkbox("data-all-tick", isMatrixAllSelected(matrix), __("Select all Dia and colours"))}${__("Dia")}</label></th>`
		+ `${columns}<th class="yrp-fabric-matrix__total">${__("Total")}</th></tr>`;
}

function cellHtml(matrix, quantities, row, rowIndex, column, columnIndex) {
	const index = matrixCellIndex(matrix, row.key, column.key);
	if (index === undefined) return `<td class="yrp-fabric-matrix__cell yrp-fabric-matrix__cell--na" aria-label="${escape(__("Not applicable"))}"></td>`;
	const enabled = isMatrixCellEnabled(matrix, row.key, column.key);
	const qty = quantities.get(index);
	return `<td class="yrp-fabric-matrix__cell ${enabled ? "" : "yrp-fabric-matrix__cell--off"}">`
		+ `<input type="text" inputmode="decimal" placeholder="0" value="${qty ? qty : ""}" ${enabled ? "" : "disabled"}`
		+ ` data-row="${rowIndex}" data-column="${columnIndex}" aria-label="${escape(`${column.label}, ${row.label}, ${__("Quantity")}`)}"></td>`;
}

function bodyHtml(matrix, quantities) {
	return matrix.rows.map((row, rowIndex) => {
		const available = row.available > 0 ? `<small class="yrp-fabric-matrix__avail">${__("Avail")} ${display(row.available)}</small>` : "";
		const cells = matrix.columns.map((column, columnIndex) => cellHtml(matrix, quantities, row, rowIndex, column, columnIndex)).join("");
		return `<tr class="${row.selected ? "" : "yrp-fabric-matrix__off"}"><th class="yrp-fabric-matrix__dia"><label>`
			+ `${checkbox(`data-row-tick="${rowIndex}"`, row.selected, __("Use {0}", [row.label]))}`
			+ `<span class="yrp-fabric-matrix__dia-name">${escape(row.label)}</span></label>${available}</th>`
			+ `${cells}<td class="yrp-fabric-matrix__total" data-row-total="${rowIndex}"></td></tr>`;
	}).join("");
}

function footHtml(matrix) {
	const columns = matrix.columns.map((column, index) => `<td data-column-total="${index}"></td>`).join("");
	return `<tr><th class="yrp-fabric-matrix__dia">${__("Total")}</th>${columns}<td class="yrp-fabric-matrix__grand" data-grand-total></td></tr>`;
}

function renderTotals(root, matrix, quantities) {
	const totals = matrixTotals(matrix, quantities);
	matrix.rows.forEach((row, index) => {
		const cell = root.querySelector(`[data-row-total="${index}"]`);
		cell.textContent = display(totals.rows[row.key]);
		cell.classList.toggle("yrp-fabric-matrix__total--over", totals.over.has(row.key));
	});
	matrix.columns.forEach((column, index) => {
		root.querySelector(`[data-column-total="${index}"]`).textContent = display(totals.columns[column.key]);
	});
	root.querySelector("[data-grand-total]").textContent = display(totals.grand);
	root.querySelector(".yrp-fabric-matrix__hint").textContent = totals.overLabels.length
		? __("More than available: {0}", [totals.overLabels.join(", ")])
		: "";
}

function renderMatrix(root, matrix, quantities, showTitle) {
	root.innerHTML = (showTitle ? `<div class="yrp-fabric-matrix__title">${escape(matrix.title)}</div>` : "")
		+ `<div class="yrp-fabric-matrix__wrap"><table aria-label="${escape(__("Quantity by Dia and Colour"))}">`
		+ `<thead>${headHtml(matrix)}</thead><tbody>${bodyHtml(matrix, quantities)}</tbody><tfoot>${footHtml(matrix)}</tfoot></table></div>`
		+ `<p class="yrp-fabric-matrix__hint" aria-live="polite"></p>`;
	renderTotals(root, matrix, quantities);
}

function isCaretAtEdge(input, key) {
	if (key === "ArrowLeft") return input.selectionStart === 0;
	if (key === "ArrowRight") return input.selectionEnd === input.value.length;
	return true;
}

function moveFocus(root, matrix, event) {
	const input = event.target;
	if (input.type !== "text" || !isCaretAtEdge(input, event.key)) return;
	const row = matrix.rows[Number(input.dataset.row)];
	const column = matrix.columns[Number(input.dataset.column)];
	const next = moveMatrixFocus(matrix, row.key, column.key, event.key);
	if (event.key === "Enter") {
		event.preventDefault();
		event.stopPropagation();
	}
	if (!next) return;
	event.preventDefault();
	const rowIndex = matrix.rows.findIndex((candidate) => candidate.key === next.rowKey);
	const columnIndex = matrix.columns.findIndex((candidate) => candidate.key === next.columnKey);
	root.querySelector(`input[data-row="${rowIndex}"][data-column="${columnIndex}"]`)?.focus();
}

function onTick(root, matrix, quantities, showTitle, input) {
	if (input.dataset.allTick !== undefined) setMatrixAllSelected(matrix, input.checked, quantities);
	else if (input.dataset.rowTick !== undefined) setMatrixRowSelected(matrix, matrix.rows[Number(input.dataset.rowTick)].key, input.checked, quantities);
	else if (input.dataset.columnTick !== undefined) setMatrixColumnSelected(matrix, matrix.columns[Number(input.dataset.columnTick)].key, input.checked, quantities);
	renderMatrix(root, matrix, quantities, showTitle);
}

function bindMatrix(root, matrix, quantities, showTitle) {
	root.addEventListener("input", (event) => {
		const input = event.target;
		if (input.type !== "text") return;
		const qty = parseFloat(input.value);
		const index = matrixCellIndex(matrix, matrix.rows[Number(input.dataset.row)].key, matrix.columns[Number(input.dataset.column)].key);
		quantities.set(index, Number.isNaN(qty) || qty < 0 ? 0 : qty);
		renderTotals(root, matrix, quantities);
	});
	root.addEventListener("change", (event) => {
		if (event.target.type === "checkbox") onTick(root, matrix, quantities, showTitle, event.target);
	});
	root.addEventListener("focusin", (event) => event.target.type === "text" && event.target.select());
	root.addEventListener("keydown", (event) => moveFocus(root, matrix, event));
}

function ensureStyle() {
	if (document.querySelector("style[data-yrp-fabric-matrix]")) return;
	document.head.insertAdjacentHTML("beforeend", `<style data-yrp-fabric-matrix>${STYLE}</style>`);
}

/** Desk popup state for one fabric row: matrices plus `values[j]` per qty_rows index. */
export function createFabricMatrixState(row, attributes, previousState = null) {
	const matrices = row.kind === "knitting" ? null : buildFabricMatrices(row.qty_rows, attributes);
	if (!matrices) return null;
	const values = (row.qty_rows || []).map((qtyRow) => Number(qtyRow.prefill || 0));
	const quantities = arrayQuantities(values);
	for (const matrix of matrices) {
		const source = previousState?.matrices.find((candidate) => candidate.title === matrix.title);
		if (source) carryMatrixSelection(matrix, source, quantities);
	}
	return { fabric_row: row.fabric_row, matrices, values, quantities };
}

export function mountFabricMatrices(wrapper, state) {
	ensureStyle();
	wrapper.innerHTML = "";
	for (const matrix of state.matrices) {
		const root = document.createElement("section");
		root.className = "yrp-fabric-matrix";
		wrapper.appendChild(root);
		renderMatrix(root, matrix, state.quantities, state.matrices.length > 1);
		bindMatrix(root, matrix, state.quantities, state.matrices.length > 1);
	}
}
