from unittest import TestCase

from essdee_yrp.dyeing_receivable_fill import fill_from_dyeing_receivables


def _qty_row(in_dia, colour, out_dia=None, reference=None, planned_dia=None, **extra):
	out_dia = out_dia or in_dia
	return {
		"in_attrs": {"Dia": in_dia, "Colour": colour},
		"out_attrs": {"Dia": out_dia, "Colour": colour},
		"target_attrs": {"Dia": planned_dia or out_dia, "Colour": colour},
		"reference_item_variant": reference,
		"prefill": 0.5,
		**extra,
	}


def _fill(qty_rows, receivables, reference_targets=None):
	fill_from_dyeing_receivables(
		qty_rows, receivables, reference_targets or {}, dia_attribute="Dia", colour_attribute="Colour"
	)
	return [row["prefill"] for row in qty_rows]


class TestFillFromDyeingReceivables(TestCase):
	def test_each_input_dia_colour_gets_the_full_dyeing_receivable(self):
		rows = [_qty_row("24 Dia", "Black", "26 Dia"), _qty_row("30 Dia", "Black", "32 Dia")]
		receivables = {("", "24 Dia", "Black"): 0.2, ("Ref-A", "30 Dia", "Black"): 1.4}
		self.assertEqual(_fill(rows, receivables), [0.2, 1.4])

	def test_inputs_without_dyeing_receivables_fill_zero(self):
		self.assertEqual(_fill([_qty_row("24 Dia", "Navy")], {("", "24 Dia", "Black"): 3}), [0])

	def test_shared_input_splits_by_the_receivables_final_reference(self):
		rows = [
			_qty_row("24 Dia", "Black", "26 Dia", reference="Cloth-26-Black"),
			_qty_row("24 Dia", "Black", "25 Dia", reference="Cloth-25-Black"),
		]
		receivables = {("Cloth-26-Black", "24 Dia", "Black"): 4, ("Cloth-25-Black", "24 Dia", "Black"): 6}
		self.assertEqual(_fill(rows, receivables), [4, 6])

	def test_actual_dia_receivable_goes_to_its_substitute_row(self):
		rows = [
			_qty_row("20 Dia", "Black", reference="Cloth-20-Black"),
			_qty_row("22 Dia", "Black", reference="Cloth-20-Black", planned_dia="20 Dia"),
		]
		receivables = {("Cloth-20-Black", "22 Dia", "Black"): 25, ("Cloth-20-Black", "20 Dia", "Black"): 5}
		self.assertEqual(_fill(rows, receivables), [5, 25])

	def test_actual_dia_receivable_without_a_substitute_row_goes_to_the_planned_row(self):
		rows = [_qty_row("60 Dia", "Red", reference="Cloth-60-Red")]
		self.assertEqual(_fill(rows, {("Cloth-60-Red", "62 Dia", "Red"): 25}), [25])

	def test_actual_dia_receivable_reaches_an_unreferenced_row_through_its_final_variant(self):
		rows = [_qty_row("60 Dia", "Red")]
		receivables = {("Cloth-60-Red", "62 Dia", "Red"): 25}
		self.assertEqual(_fill(rows, receivables, {"Cloth-60-Red": ("60 Dia", "Red")}), [25])
		self.assertEqual(_fill([_qty_row("60 Dia", "Red")], receivables), [0])

	def test_shared_input_without_references_goes_to_the_first_row(self):
		rows = [_qty_row("24 Dia", "Black", "26 Dia"), _qty_row("24 Dia", "Black", "25 Dia")]
		self.assertEqual(_fill(rows, {("", "24 Dia", "Black"): 10}), [10, 0])

	def test_exact_grn_row_rows_keep_their_source_fill(self):
		rows = [_qty_row("24 Dia", "Black", source_bucket_key="bucket-1")]
		self.assertEqual(_fill(rows, {("", "24 Dia", "Black"): 10}), [0.5])
