from frappe.utils import flt


def fill_from_dyeing_receivables(qty_rows, receivables, reference_targets, dia_attribute, colour_attribute):
	"""Prefill post-dyeing rows with the full dyeing receivable kg.

	``receivables`` is {(final reference or "", dia, colour): kg} and ``reference_targets``
	{final reference: (planned dia, colour)}. A receivable goes to its reference's row with
	the same input Dia × Colour (an actual-Dia substitute row) or that reference's planned
	row; else to a row with the same input; else to the planned row of its final variant.
	Rows tied to an exact GRN row keep their source fill.
	"""
	rows = [row for row in qty_rows if row.get("in_attrs") and not row.get("source_bucket_key")]
	for row in rows:
		row["prefill"] = 0
	for (reference, dia, colour), qty in receivables.items():
		target = _receiving_row(
			rows, reference, (dia, colour), reference_targets.get(reference), dia_attribute, colour_attribute
		)
		if target:
			target["prefill"] = flt(target["prefill"] + flt(qty), 3)


def _receiving_row(rows, reference, input_key, final_target, dia_attribute, colour_attribute):
	def attrs_key(attrs):
		return ((attrs or {}).get(dia_attribute), (attrs or {}).get(colour_attribute))

	def is_planned(row):
		return attrs_key(row.get("out_attrs")) == attrs_key(row.get("target_attrs") or row.get("out_attrs"))

	referenced = [row for row in rows if reference and row.get("reference_item_variant") == reference]
	candidates = (
		[row for row in referenced if attrs_key(row["in_attrs"]) == input_key],
		[row for row in referenced if is_planned(row)],
		sorted(
			(row for row in rows if attrs_key(row["in_attrs"]) == input_key),
			key=lambda row: bool(row.get("reference_item_variant")),
		),
		[
			row
			for row in rows
			if final_target and attrs_key(row.get("target_attrs")) == final_target and is_planned(row)
		],
	)
	return next((group[0] for group in candidates if group), None)
