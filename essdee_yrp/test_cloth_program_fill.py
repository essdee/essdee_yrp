from unittest import TestCase

import frappe

from essdee_yrp.cloth_program_fill import fill_from_cloth_program

CLOTH = "Dyed Cloth"


def _program(dia, colour, weight, cloth=CLOTH):
	return frappe._dict(
		cloth_item=cloth,
		dia=dia,
		colour=colour,
		weight=weight,
		reference_item_variant=f"{cloth}-{dia}-{colour}",
	)


def _qty_row(colour, dia, available, planned=None, **extra):
	planned = planned or dia
	row = {
		"key": f"{colour}:{dia}",
		"out_attrs": {"Colour": colour, "Dia": dia},
		"target_attrs": {"Colour": colour, "Dia": planned},
		"reference_item_variant": f"{CLOTH}-{planned}-{colour}",
		"source_available": available,
		"prefill": 0,
		**extra,
	}
	if planned != dia:
		row["source_item_variant"] = f"{CLOTH}-{dia}-Greige"
	return row


def _fill(qty_rows, programs):
	fill_from_cloth_program(qty_rows, programs, CLOTH, dia_attribute="Dia", colour_attribute="Colour")
	return [row["prefill"] for row in qty_rows]


class TestFillFromClothProgram(TestCase):
	def test_each_dia_colour_gets_its_cloth_program_weight(self):
		rows = [
			_qty_row("Black", "12 Dia", 274),
			_qty_row("Maroon", "12 Dia", 274),
			_qty_row("Black", "16 Dia", 284),
		]
		programs = [
			_program("12 Dia", "Black", 46),
			_program("12 Dia", "Maroon", 40),
			_program("16 Dia", "Black", 56),
		]
		self.assertEqual(_fill(rows, programs), [46, 40, 56])

	def test_weight_is_not_capped_at_available_stock(self):
		self.assertEqual(_fill([_qty_row("Black", "12 Dia", 10)], [_program("12 Dia", "Black", 46)]), [46])

	def test_substitute_row_takes_the_weight_when_the_planned_dia_has_no_stock(self):
		rows = [_qty_row("Black", "20 Dia", 0), _qty_row("Black", "22 Dia", 414.2, planned="20 Dia")]
		self.assertEqual(_fill(rows, [_program("20 Dia", "Black", 86)]), [0, 86])

	def test_planned_row_keeps_the_weight_when_it_has_stock(self):
		rows = [_qty_row("Black", "20 Dia", 50), _qty_row("Black", "22 Dia", 414.2, planned="20 Dia")]
		self.assertEqual(_fill(rows, [_program("20 Dia", "Black", 86)]), [86, 0])

	def test_planned_row_keeps_the_weight_when_nothing_has_stock(self):
		rows = [_qty_row("Black", "20 Dia", 0), _qty_row("Black", "22 Dia", 0, planned="20 Dia")]
		self.assertEqual(_fill(rows, [_program("20 Dia", "Black", 86)]), [86, 0])

	def test_other_cloth_items_and_missing_programs_fill_zero(self):
		rows = [_qty_row("Black", "12 Dia", 274), _qty_row("Navy", "12 Dia", 274)]
		programs = [_program("12 Dia", "Black", 46, cloth="Other Cloth")]
		self.assertEqual(_fill(rows, programs), [0, 0])

	def test_rows_without_a_reference_match_on_dia_and_colour(self):
		row = _qty_row("Black", "12 Dia", 274)
		row.pop("reference_item_variant")
		program = _program("12 Dia", "Black", 46)
		program.reference_item_variant = ""
		self.assertEqual(_fill([row], [program]), [46])

	def test_exact_grn_row_rows_keep_their_source_fill(self):
		rows = [_qty_row("Black", "12 Dia", 274, source_bucket_key="bucket-1", prefill=30)]
		self.assertEqual(_fill(rows, [_program("12 Dia", "Black", 46)]), [30])
