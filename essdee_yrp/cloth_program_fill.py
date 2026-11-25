from collections import OrderedDict

from frappe.utils import flt
from yrp.attribute_links import value as _attribute_value


def fill_from_cloth_program(qty_rows, program_rows, cloth_item, dia_attribute, colour_attribute):
	"""Prefill dyeing rows with the Lot's saved Cloth Program kg, uncapped by stock.

	Each planned Dia × Colour gets its program weight once: on the planned row, or on
	its actual-Dia substitute row when only the substitute has Knitting stock. Rows
	tied to an exact GRN row keep their source fill.
	"""
	by_reference, by_attrs = _program_weights(program_rows, cloth_item)
	for key, rows in _target_groups(qty_rows, dia_attribute, colour_attribute).items():
		reference, dia, colour = key
		weight = by_reference.get(reference) if reference else None
		if weight is None:
			weight = by_attrs.get((dia, colour), 0)
		target = _target_row(rows, dia_attribute)
		for row in rows:
			row["prefill"] = flt(weight, 3) if row is target else 0


def _program_weights(program_rows, cloth_item):
	by_reference, by_attrs = {}, {}
	for program in program_rows:
		if program.cloth_item != cloth_item:
			continue
		weight = flt(program.weight)
		if program.get("reference_item_variant"):
			reference = program.reference_item_variant
			by_reference[reference] = by_reference.get(reference, 0) + weight
		key = (_attribute_value(program.dia), _attribute_value(program.colour))
		by_attrs[key] = by_attrs.get(key, 0) + weight
	return by_reference, by_attrs


def _target_groups(qty_rows, dia_attribute, colour_attribute):
	groups = OrderedDict()
	for row in qty_rows:
		if row.get("source_bucket_key"):
			continue
		target = row.get("target_attrs") or row.get("out_attrs") or {}
		key = (
			row.get("reference_item_variant") or "",
			target.get(dia_attribute),
			target.get(colour_attribute),
		)
		groups.setdefault(key, []).append(row)
	return groups


def _is_planned_dia(row, dia_attribute):
	target_dia = (row.get("target_attrs") or {}).get(dia_attribute)
	return not target_dia or (row.get("out_attrs") or {}).get(dia_attribute) == target_dia


def _target_row(rows, dia_attribute):
	planned = next((row for row in rows if _is_planned_dia(row, dia_attribute)), rows[0])
	if flt(planned.get("source_available")) > 0:
		return planned
	stocked = (row for row in rows if row is not planned and flt(row.get("source_available")) > 0)
	return next(stocked, planned)
