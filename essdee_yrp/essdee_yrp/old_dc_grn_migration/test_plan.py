import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from essdee_yrp.essdee_yrp.old_dc_grn_migration.cloth import ensure_accessory_dias, ensure_process_chain
from essdee_yrp.essdee_yrp.old_dc_grn_migration.data import LOTS, PROCESS_RATES, YARN_RATES
from essdee_yrp.essdee_yrp.old_dc_grn_migration.documents import cap_receipt_to_pending, fill_receipt_rows
from essdee_yrp.essdee_yrp.old_dc_grn_migration.lot_migrator import LotMigrator, get_booked_dia
from essdee_yrp.essdee_yrp.old_dc_grn_migration.masters import (
	CLOTH_YARN_RECIPES,
	IPD_CLOTHS,
	LOT_CLOTH_PROGRAMS,
	MasterCheck,
	get_cloth_program_selection,
)
from essdee_yrp.essdee_yrp.old_dc_grn_migration.plan import (
	Document,
	Line,
	LotMappings,
	PlanError,
	allocate,
	build_lot_plan,
	build_lot_plan_from_snapshot,
	get_effective_dates,
	get_missing_rates,
	get_process_order,
	get_yarn_shortfall,
	move_to_offered_dias,
	split_dialess_lines,
	to_dia,
)
from essdee_yrp.essdee_yrp.old_dc_grn_migration.process_cost import ProcessRateMissing, ensure_process_cost
from essdee_yrp.essdee_yrp.old_dc_grn_migration.run import RUN_LOTS

DOCUMENTS = "essdee_yrp.essdee_yrp.old_dc_grn_migration.documents"
PLAN = "essdee_yrp.essdee_yrp.old_dc_grn_migration.plan"
CLOTH = "essdee_yrp.essdee_yrp.old_dc_grn_migration.cloth"
PROCESS_COST = "essdee_yrp.essdee_yrp.old_dc_grn_migration.process_cost"
COLOURS = {"A MEL": "Andhra Melange", "BLACK": "Black", "AIRFORCE NAVY": "Airforce"}
SUPPLIERS = {"VIJAY": "Vijay Tex", "KSM": "KSM KNIT BLEACHERS"}
MAPPINGS = LotMappings(
	COLOURS,
	SUPPLIERS,
	"Greige",
	{"GREY FABRIC": "Rib", "A MEL": "Melange Cloth"},
	{"Black": ["Rib"], "Airforce": ["Rib", "Jersey"]},
)


def dc(document_id, process, supplier, date, *lines):
	return Document(
		"DC", document_id, f"DC-{document_id}", date, process, supplier, (), [Line(*line) for line in lines]
	)


def grn(document_id, supplier, date, linked, *lines):
	return Document(
		"GRN",
		document_id,
		f"GRN-{document_id}",
		date,
		"x",
		supplier,
		tuple(linked),
		[Line(*line) for line in lines],
	)


def raise_plan_error(message):
	raise PlanError(message)


class OldDcGrnPlanTest(unittest.TestCase):
	def test_allocate_keeps_total_and_ratio(self):
		self.assertEqual(allocate(100, [1, 1, 2]), [25.0, 25.0, 50.0])
		self.assertAlmostEqual(sum(allocate(10, [1, 1, 1])), 10)
		self.assertEqual(allocate(10, [1, 1, 1])[-1], 3.334)

	def test_allocate_equal_split_when_weights_are_zero(self):
		self.assertEqual(allocate(9, [0, 0, 0]), [3.0, 3.0, 3.0])

	def test_allocate_rejects_empty_weights(self):
		with self.assertRaises(PlanError):
			allocate(5, [])

	def test_to_dia_formats_old_dia(self):
		self.assertEqual(to_dia("18"), "18 Dia")
		self.assertEqual(to_dia(" 18.0 "), "18 Dia")
		assert to_dia("0") is None
		assert to_dia("") is None

	def test_split_dialess_lines_uses_reference_dia_ratio_of_same_colour(self):
		lines = [Line("BLACK", "0", 10, 300.0), Line("NAVY", "14", 2, 20.0)]
		reference = [
			Line("BLACK", "14", 4, 100.0),
			Line("BLACK", "16", 4, 200.0),
			Line("NAVY", "20", 1, 999.0),
		]
		result = split_dialess_lines(lines, reference)
		self.assertEqual(
			[(line.colour, line.dia, line.kg) for line in result],
			[
				("BLACK", "14", 100.0),
				("BLACK", "16", 200.0),
				("NAVY", "14", 20.0),
			],
		)
		self.assertEqual(sum(line.rolls for line in result if line.colour == "BLACK"), 10)

	def test_split_dialess_lines_fails_without_reference(self):
		with self.assertRaisesRegex(PlanError, "no Dia"):
			split_dialess_lines([Line("BLACK", "", 1, 5.0)], [Line("NAVY", "14", 1, 5.0)])

	def test_process_order_is_knitting_dyeing_then_first_dc_date(self):
		documents = [
			dc(1, "Washing", "x", "2026-10-01", ("BLACK", "14", 1, 5.0)),
			dc(2, "Knitting Program", "x", "2026-10-05", ("BLACK", "14", 1, 5.0)),
			dc(3, "Dyeing", "x", "2026-10-09", ("BLACK", "14", 1, 5.0)),
			dc(4, "Heat Setting", "x", "2026-09-01", ("BLACK", "14", 1, 5.0)),
		]
		self.assertEqual(get_process_order(documents), ["Knitting", "Dyeing", "Heat Setting", "Washing"])

	def test_build_lot_plan_makes_one_work_order_per_old_dc_and_maps_masters(self):
		documents = [
			dc(
				10,
				"Knitting Program",
				"VIJAY",
				"2026-10-07",
				("GREY FABRIC", "18", 0, 920.0),
				("GREY FABRIC", "20", 0, 400.0),
			),
			grn(20, "VIJAY", "2026-10-14", [10], ("GREY FABRIC", "18", 73, 739.4)),
			dc(11, "Bleaching", "KSM", "2026-10-14", ("BLACK", "18", 72, 739.4)),
			grn(21, "KSM", "2026-10-21", [11], ("BLACK", "0", 72, 719.0)),
		]
		plan = build_lot_plan("F0926-51", documents, MAPPINGS)
		self.assertEqual(plan.processes, ["Knitting", "Bleaching"])
		knitting, bleaching = plan.work_orders
		self.assertEqual(knitting.grns[0].lines[0].planned_dia, "18 Dia")
		self.assertEqual(
			(knitting.process, knitting.supplier, knitting.dc.number), ("Knitting", "Vijay Tex", "DC-10")
		)
		self.assertEqual(
			[(line.colour, line.dia, line.kg) for line in knitting.lines],
			[("Greige", "18 Dia", 920.0), ("Greige", "20 Dia", 400.0)],
		)
		self.assertEqual(
			[(g.number, [(line.colour, line.dia, line.kg) for line in g.lines]) for g in knitting.grns],
			[("GRN-20", [("Greige", "18 Dia", 739.4)])],
		)
		self.assertEqual(bleaching.grns[0].lines[0].dia, "18 Dia")
		self.assertEqual(bleaching.grns[0].lines[0].kg, 719.0)

	def test_build_lot_plan_fails_for_unmapped_supplier(self):
		documents = [dc(10, "Dyeing", "UNKNOWN", "2026-10-07", ("BLACK", "18", 1, 5.0))]
		with self.assertRaisesRegex(PlanError, "UNKNOWN"):
			build_lot_plan("L", documents, MAPPINGS)

	def test_build_lot_plan_fails_for_unmapped_colour(self):
		documents = [dc(10, "Dyeing", "VIJAY", "2026-10-07", ("PINK", "18", 1, 5.0))]
		with self.assertRaisesRegex(PlanError, "PINK"):
			build_lot_plan("L", documents, MAPPINGS)

	def test_grn_linked_to_two_dcs_is_split_by_matching_lines(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-07", ("GREY FABRIC", "18", 0, 100.0)),
			dc(11, "Knitting Program", "VIJAY", "2026-10-08", ("GREY FABRIC", "20", 0, 50.0)),
			grn(
				20,
				"VIJAY",
				"2026-10-14",
				[10, 11],
				("GREY FABRIC", "18", 5, 99.0),
				("GREY FABRIC", "20", 3, 51.0),
			),
		]
		first, second = build_lot_plan("L", documents, MAPPINGS).work_orders
		self.assertEqual([(line.dia, line.kg) for line in first.grns[0].lines], [("18 Dia", 99.0)])
		self.assertEqual([(line.dia, line.kg) for line in second.grns[0].lines], [("20 Dia", 51.0)])

	def test_grn_line_with_no_matching_dc_line_fails(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-07", ("GREY FABRIC", "18", 0, 100.0)),
			grn(20, "VIJAY", "2026-10-14", [10], ("BLACK", "18", 5, 99.0)),
		]
		with self.assertRaisesRegex(PlanError, "GRN-20"):
			build_lot_plan("L", documents, MAPPINGS)

	def test_knitting_grn_with_other_dia_is_received_as_actual_dia_of_the_same_colour(self):
		documents = [
			dc(
				10,
				"Knitting Program",
				"VIJAY",
				"2026-10-07",
				("GREY FABRIC", "20", 0, 100.0),
				("BLACK", "20", 0, 10.0),
			),
			grn(20, "VIJAY", "2026-10-14", [10], ("GREY FABRIC", "18", 5, 99.0)),
		]
		(work_order,) = build_lot_plan("L", documents, MAPPINGS).work_orders
		(line,) = work_order.grns[0].lines
		self.assertEqual(
			(line.colour, line.dia, line.planned_dia, line.kg), ("Greige", "18 Dia", "20 Dia", 99.0)
		)

	def test_non_knitting_grn_with_other_dia_fails(self):
		documents = [
			dc(10, "Dyeing", "VIJAY", "2026-10-07", ("BLACK", "20", 0, 100.0)),
			grn(20, "VIJAY", "2026-10-14", [10], ("BLACK", "18", 5, 99.0)),
		]
		with self.assertRaisesRegex(PlanError, "GRN-20"):
			build_lot_plan("L", documents, MAPPINGS)

	def test_grn_linked_to_other_lots_dcs_uses_only_this_lots_dc(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-07", ("GREY FABRIC", "18", 0, 100.0)),
			grn(20, "VIJAY", "2026-10-14", [10, 77], ("GREY FABRIC", "18", 5, 99.0)),
		]
		(work_order,) = build_lot_plan("L", documents, MAPPINGS).work_orders
		self.assertEqual(work_order.grns[0].lines[0].kg, 99.0)

	def test_grn_linked_to_unknown_dc_fails(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-07", ("GREY FABRIC", "18", 0, 100.0)),
			grn(20, "VIJAY", "2026-10-14", [99], ("GREY FABRIC", "18", 5, 99.0)),
		]
		with self.assertRaisesRegex(PlanError, "GRN-20"):
			build_lot_plan("L", documents, MAPPINGS)

	def test_yarn_shortfall_reuses_existing_stock(self):
		needed = {"Yarn A": 100.0, "Yarn B": 50.0, "Yarn C": 10.0}
		available = {"Yarn A": 40.0, "Yarn B": 80.0}
		self.assertEqual(get_yarn_shortfall(needed, available), {"Yarn A": 60.0, "Yarn C": 10.0})

	def test_missing_rates_lists_null_rates_only(self):
		rates = {"Yarn A": 210.5, "Yarn C": None}
		self.assertEqual(
			get_missing_rates({"Yarn A": 1.0, "Yarn C": 2.0, "Yarn D": 3.0}, rates), ["Yarn C", "Yarn D"]
		)

	def test_yarn_rates_are_keyed_by_migrated_lot(self):
		lots = {lot["lot"] for lot in LOTS}
		self.assertLessEqual(set(YARN_RATES), lots)
		self.assertEqual(YARN_RATES["GY0926-13"]["Yarn 36's RL-Greige"], 326)
		self.assertEqual(YARN_RATES["GY0926-24"]["Yarn 36's RL-Greige"], 336)

	def test_knitting_dc_is_split_into_one_work_order_per_cloth(self):
		documents = [
			dc(
				10,
				"Knitting Program",
				"VIJAY",
				"2026-10-07",
				("GREY FABRIC", "18", 0, 100.0),
				("A MEL", "20", 0, 50.0),
			),
			grn(20, "VIJAY", "2026-10-14", [10], ("A MEL", "20", 2, 49.0), ("GREY FABRIC", "18", 5, 99.0)),
		]
		rib, melange = build_lot_plan("L", documents, MAPPINGS).work_orders
		self.assertEqual(
			(rib.cloth, [line.kg for line in rib.lines], [line.kg for line in rib.grns[0].lines]),
			("Rib", [100.0], [99.0]),
		)
		self.assertEqual(
			(melange.cloth, [line.kg for line in melange.lines], [line.kg for line in melange.grns[0].lines]),
			("Melange Cloth", [50.0], [49.0]),
		)

	def test_dyed_colour_resolves_cloth_from_ipd_colours(self):
		documents = [dc(10, "Dyeing", "VIJAY", "2026-10-07", ("BLACK", "18", 1, 5.0))]
		(work_order,) = build_lot_plan("L", documents, MAPPINGS).work_orders
		self.assertEqual(work_order.cloth, "Rib")

	def test_colour_on_two_cloths_fails(self):
		documents = [dc(10, "Dyeing", "VIJAY", "2026-10-07", ("AIRFORCE NAVY", "18", 1, 5.0))]
		with self.assertRaisesRegex(PlanError, "cloth"):
			build_lot_plan("L", documents, MAPPINGS)

	def test_plan_builds_from_embedded_lot_data(self):
		data = {
			"lot": "L",
			"mappings": {
				"colours": COLOURS,
				"suppliers": SUPPLIERS,
				"greige_colour": "Greige",
				"cloth_by_old_colour": {"GREY FABRIC": "Rib"},
				"cloth_by_colour": {},
			},
			"documents": [
				{
					"side": "DC",
					"document_id": 1,
					"number": "PG-1",
					"date": "2026-10-07",
					"process": "Knitting Program",
					"supplier": "VIJAY",
					"linked_dc_ids": [],
					"lines": [{"colour": "GREY FABRIC", "dia": "18", "rolls": 0, "kg": 10.0}],
				}
			],
		}
		(work_order,) = build_lot_plan_from_snapshot(data).work_orders
		self.assertEqual(
			(work_order.process, work_order.supplier, work_order.cloth, work_order.kg),
			("Knitting", "Vijay Tex", "Rib", 10.0),
		)

	def test_downstream_dc_waits_for_enough_upstream_receipts(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-09-04", ("GREY FABRIC", "18", 0, 100.0)),
			grn(20, "VIJAY", "2026-10-05", [10], ("GREY FABRIC", "18", 5, 60.0)),
			grn(21, "VIJAY", "2026-10-09", [10], ("GREY FABRIC", "18", 5, 40.0)),
			dc(11, "Dyeing", "KSM", "2026-09-15", ("BLACK", "18", 5, 50.0)),
			dc(12, "Dyeing", "KSM", "2026-10-20", ("BLACK", "18", 5, 50.0)),
			grn(22, "KSM", "2026-10-01", [11], ("BLACK", "18", 5, 50.0)),
		]
		plan = build_lot_plan("L", documents, MAPPINGS)
		dates = get_effective_dates(plan)
		knitting, first_dyeing, second_dyeing = plan.work_orders
		self.assertEqual(dates[("DC", first_dyeing.dc.number, "Rib")], "2026-10-05")
		self.assertEqual(dates[("DC", second_dyeing.dc.number, "Rib")], "2026-10-20")
		self.assertEqual(dates[("GRN", "GRN-22", "DC-11", "Rib")], "2026-10-05")
		self.assertEqual(dates[("DC", knitting.dc.number, "Rib")], "2026-09-04")

	def test_knitting_quantity_is_raised_to_what_was_received(self):
		documents = [
			dc(
				10,
				"Knitting Program",
				"VIJAY",
				"2026-10-07",
				("GREY FABRIC", "18", 0, 100.0),
				("GREY FABRIC", "20", 0, 50.0),
			),
			grn(
				20,
				"VIJAY",
				"2026-10-14",
				[10],
				("GREY FABRIC", "18", 5, 103.5),
				("GREY FABRIC", "20", 3, 40.0),
			),
		]
		(work_order,) = build_lot_plan("L", documents, MAPPINGS).work_orders
		self.assertEqual(
			[(line.dia, line.kg) for line in work_order.lines], [("18 Dia", 103.5), ("20 Dia", 50.0)]
		)

	def knitting_plan(self, program, received):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-03", *program),
			grn(20, "VIJAY", "2026-10-05", [10], *received),
		]
		(work_order,) = build_lot_plan("L", documents, MAPPINGS).work_orders
		return work_order

	def test_dia_the_ipd_does_not_knit_moves_to_the_dia_that_received_the_extra(self):
		work_order = self.knitting_plan(
			[("A MEL", "22", 0, 67.0), ("A MEL", "24", 0, 20.0), ("A MEL", "26", 0, 118.0)],
			[("A MEL", "24", 3, 62.7), ("A MEL", "26", 7, 122.8)],
		)
		offered = {("Andhra Melange", "24 Dia"), ("Andhra Melange", "26 Dia")}
		notes = move_to_offered_dias(work_order, offered)
		self.assertEqual(
			[(line.dia, line.kg) for line in work_order.lines], [("24 Dia", 87.0), ("26 Dia", 122.8)]
		)
		self.assertEqual(len(notes), 1)
		self.assertEqual(move_to_offered_dias(work_order, offered), [])

	def test_dia_move_follows_a_grn_line_planned_on_the_old_dia(self):
		work_order = self.knitting_plan([("A MEL", "22", 0, 23.0)], [("A MEL", "32", 1, 20.0)])
		move_to_offered_dias(work_order, {("Andhra Melange", "32 Dia")})
		self.assertEqual([(line.dia, line.kg) for line in work_order.lines], [("32 Dia", 23.0)])
		(line,) = work_order.grns[0].lines
		self.assertEqual((line.dia, line.planned_dia), ("32 Dia", "32 Dia"))

	def test_dia_move_uses_the_user_decided_dia(self):
		work_order = self.knitting_plan([("A MEL", "22", 0, 23.0)], [("A MEL", "32", 1, 20.0)])
		offered = {("Andhra Melange", "24 Dia"), ("Andhra Melange", "26 Dia")}
		with patch.dict(f"{PLAN}.KNIT_DIA_MOVES", {("DC-10", "Andhra Melange", "22 Dia"): "24 Dia"}):
			(note,) = move_to_offered_dias(work_order, offered)
		self.assertIn("user decision", note)
		self.assertEqual([(line.dia, line.kg) for line in work_order.lines], [("24 Dia", 23.0)])
		self.assertEqual([(g.dia, g.planned_dia) for g in work_order.grns[0].lines], [("32 Dia", "24 Dia")])

	def test_user_decided_dia_move_applies_to_a_dia_the_ipd_knits(self):
		work_order = self.knitting_plan(
			[
				("GREY FABRIC", "24", 0, 356.0),
				("GREY FABRIC", "26", 0, 103.0),
				("GREY FABRIC", "28", 0, 302.0),
			],
			[("GREY FABRIC", "26", 20, 453.2), ("GREY FABRIC", "28", 15, 300.0)],
		)
		self.assertEqual(work_order.kg, 1111.2)
		offered = {("Greige", "24 Dia"), ("Greige", "26 Dia"), ("Greige", "28 Dia")}
		with patch.dict(f"{PLAN}.KNIT_DIA_MOVES", {("DC-10", "Greige", "24 Dia"): "26 Dia"}):
			(note,) = move_to_offered_dias(work_order, offered)
		self.assertIn("knitted by the IPD; user decision", note)
		self.assertEqual(
			[(line.dia, line.kg) for line in work_order.lines], [("26 Dia", 459.0), ("28 Dia", 302.0)]
		)
		self.assertEqual(work_order.kg, 761.0)

	def test_dia_move_fails_without_a_single_dia_that_received_extra(self):
		work_order = self.knitting_plan(
			[("A MEL", "22", 0, 10.0), ("A MEL", "24", 0, 10.0), ("A MEL", "26", 0, 10.0)],
			[("A MEL", "24", 1, 20.0), ("A MEL", "26", 1, 20.0)],
		)
		with self.assertRaisesRegex(PlanError, "DC-10: Andhra Melange 22 Dia 10 kg"):
			move_to_offered_dias(work_order, {("Andhra Melange", "24 Dia"), ("Andhra Melange", "26 Dia")})

	def test_dia_move_leaves_colours_the_ipd_does_not_knit_to_the_route_check(self):
		work_order = self.knitting_plan([("A MEL", "22", 0, 10.0)], [("A MEL", "22", 1, 10.0)])
		self.assertEqual(move_to_offered_dias(work_order, {("Black", "24 Dia")}), [])
		self.assertEqual([line.dia for line in work_order.lines], ["22 Dia"])

	def test_knitting_grn_in_another_dia_is_booked_only_on_the_dia_it_replaced(self):
		work_order = self.knitting_plan(
			[
				("GREY FABRIC", "12", 18, 208.0),
				("GREY FABRIC", "16", 18, 334.0),
				("GREY FABRIC", "20", 30, 500.0),
			],
			[
				("GREY FABRIC", "12", 18, 209.7),
				("GREY FABRIC", "16", 24, 337.1),
				("GREY FABRIC", "18", 36, 479.1),
			],
		)
		self.assertEqual(
			[(g.dia, g.planned_dia, g.kg, g.rolls) for g in work_order.grns[0].lines],
			[
				("12 Dia", "12 Dia", 209.7, 18),
				("16 Dia", "16 Dia", 337.1, 24),
				("18 Dia", "20 Dia", 479.1, 36),
			],
		)
		self.assertEqual(
			[(line.dia, line.kg) for line in work_order.lines],
			[("12 Dia", 209.7), ("16 Dia", 337.1), ("20 Dia", 500.0)],
		)

	def test_knitting_grn_in_another_dia_fails_when_no_single_dia_fell_short(self):
		with self.assertRaisesRegex(
			PlanError, "Greige received in 18 Dia 99 kg replaces no single programmed Dia"
		):
			self.knitting_plan(
				[("GREY FABRIC", "12", 0, 100.0), ("GREY FABRIC", "20", 0, 100.0)],
				[("GREY FABRIC", "18", 5, 99.0)],
			)

	def test_dyed_lines_follow_the_dia_knitted_greige_was_booked_on(self):
		remaps = {("Rib", "Greige", "18 Dia"): "20 Dia", ("Rib", "Black", "22 Dia"): "24 Dia"}
		cases = [
			("Airforce", "18 Dia", "20 Dia"),
			("Black", "22 Dia", "24 Dia"),
			("Airforce", "22 Dia", "22 Dia"),
		]
		for colour, dia, booked in cases:
			self.assertEqual(get_booked_dia(remaps, "Rib", colour, dia), booked)

	def test_knitting_grn_in_another_dia_is_actual_dia_only_when_the_ipd_knits_it(self):
		work_order = self.knitting_plan([("A MEL", "20", 0, 100.0)], [("A MEL", "18", 5, 99.0)])
		attrs = {"Cloth-20": {"Colour": "Andhra Melange", "Dia": "20 Dia"}}
		cases = [({("Andhra Melange", "18 Dia")}, "Cloth-18", 0), (set(), "Cloth-20", 1)]
		for knit_routes, variant, note_count in cases:
			rows = [{"item_variant": "Cloth-20", "received_type": None, "quantity": 0}]
			with (
				patch(f"{DOCUMENTS}.frappe") as frappe,
				patch(f"{DOCUMENTS}._variant_attrs", side_effect=attrs.get),
				patch(
					f"{DOCUMENTS}.get_dia_variant", side_effect=lambda item, dia: f"Cloth-{dia.split()[0]}"
				),
			):
				frappe.db.get_single_value.return_value = None
				(row,), notes = fill_receipt_rows(rows, work_order.grns[0], knit_routes)
			self.assertEqual((row["item_variant"], row["quantity"], row["secondary_qty"]), (variant, 99.0, 5))
			self.assertEqual(len(notes), note_count)

	def test_grn_line_is_split_over_the_source_bucket_rows_of_its_variant(self):
		work_order = self.knitting_plan([("A MEL", "20", 0, 100.0)], [("A MEL", "20", 4, 90.0)])
		rows = [
			{"item_variant": "Cloth-20", "received_type": None, "quantity": 0, "pending_quantity": pending}
			for pending in (60.0, 30.0)
		]
		attrs = {"Cloth-20": {"Colour": "Andhra Melange", "Dia": "20 Dia"}}
		with (
			patch(f"{DOCUMENTS}.frappe") as frappe,
			patch(f"{DOCUMENTS}._variant_attrs", side_effect=attrs.get),
		):
			frappe.db.get_single_value.return_value = None
			booked, _notes = fill_receipt_rows(rows, work_order.grns[0], set())
		self.assertEqual([(row["quantity"], row["secondary_qty"]) for row in booked], [(60.0, 3), (30.0, 1)])

	def test_downstream_dc_waits_for_the_upstream_receipts_of_its_own_colour(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-01", ("BLACK", "18", 0, 100.0)),
			dc(11, "Knitting Program", "VIJAY", "2026-10-01", ("A MEL", "18", 0, 100.0)),
			grn(20, "VIJAY", "2026-10-03", [10], ("BLACK", "18", 0, 100.0)),
			grn(21, "VIJAY", "2026-10-08", [11], ("A MEL", "18", 0, 100.0)),
			dc(12, "Heat Setting", "VIJAY", "2026-10-01", ("A MEL", "18", 0, 100.0)),
		]
		mappings = LotMappings(COLOURS, SUPPLIERS, "Greige", {"BLACK": "Rib", "A MEL": "Rib"}, {})
		dates = get_effective_dates(build_lot_plan("L", documents, mappings))
		self.assertEqual(dates[("DC", "DC-12", "Rib")], "2026-10-08")

	def test_minimum_dc_date_moves_its_grns_and_the_downstream_dc(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-09-04", ("GREY FABRIC", "18", 0, 100.0)),
			grn(20, "VIJAY", "2026-09-10", [10], ("GREY FABRIC", "18", 5, 100.0)),
			dc(11, "Dyeing", "KSM", "2026-09-15", ("BLACK", "18", 5, 100.0)),
		]
		plan = build_lot_plan("L", documents, MAPPINGS)
		dates = get_effective_dates(plan, {("DC-10", "Rib"): "2026-09-20"})
		self.assertEqual(dates[("DC", "DC-10", "Rib")], "2026-09-20")
		self.assertEqual(dates[("GRN", "GRN-20", "DC-10", "Rib")], "2026-09-20")
		self.assertEqual(dates[("DC", "DC-11", "Rib")], "2026-09-20")

	def test_receipt_gain_is_booked_up_to_pending(self):
		rows = [
			{"item_variant": "Navy", "quantity": 105.0, "pending_quantity": 100.0},
			{"item_variant": "Red", "quantity": 40.0, "pending_quantity": 50.0},
			{"item_variant": "Black", "quantity": 5.0, "pending_quantity": 0},
		]
		capped, notes = cap_receipt_to_pending(rows, "GRN-1")
		self.assertEqual(
			[(row["item_variant"], row["quantity"]) for row in capped], [("Navy", 100.0), ("Red", 40.0)]
		)
		self.assertEqual(len(notes), 2)

	def test_supplier_and_warehouse_are_synced_only_when_missing(self):
		cases = [
			({"Supplier": False, "Warehouse": False}, ["Supplier", "Warehouse"]),
			({"Supplier": True, "Warehouse": False}, ["Warehouse"]),
			({"Supplier": True, "Warehouse": True}, []),
		]
		for existing, expected in cases:
			check = MasterCheck([])
			with patch("essdee_yrp.essdee_yrp.old_dc_grn_migration.masters.frappe") as frappe:
				frappe.db.exists.side_effect = lambda doctype, name, existing=existing: existing[doctype]
				check.check_suppliers()
			self.assertEqual([row["kind"] for row in check.sync], expected)
			self.assertEqual({row["name"] for row in check.sync}, {"Sri Pavai Knits"} if expected else set())

	def test_colour_step_lot_carries_the_finished_colour_after_knitting(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-01", ("GREY FABRIC", "18", 2, 100.0)),
			grn(20, "VIJAY", "2026-10-05", [10], ("GREY FABRIC", "18", 2, 100.0)),
			dc(11, "Bleaching", "KSM", "2026-10-06", ("GREY FABRIC", "18", 2, 100.0)),
			grn(21, "KSM", "2026-10-08", [11], ("GREY FABRIC", "18", 2, 98.0)),
		]
		knitting, bleaching = build_lot_plan("F0826-18", documents, MAPPINGS).work_orders
		self.assertEqual({line.colour for line in knitting.lines + knitting.grns[0].lines}, {"Greige"})
		self.assertEqual({line.colour for line in bleaching.lines + bleaching.grns[0].lines}, {"White"})
		other_lot = build_lot_plan("L", documents, MAPPINGS).work_orders[1]
		self.assertEqual(other_lot.lines[0].colour, "Greige")

	def test_colour_process_takes_over_the_dyeing_step_and_later_steps_are_appended(self):
		rows = [
			SimpleNamespace(sequence=10, fabric_process="Knitting"),
			SimpleNamespace(sequence=20, fabric_process="Dyeing"),
		]
		ipd = SimpleNamespace(
			approval_status="Draft",
			item="Cloth",
			fabric_processes=rows,
			dyeing_process="Dyeing",
			save=lambda: None,
		)
		ipd.get = lambda field: getattr(ipd, field)
		ipd.append = lambda _field, row: rows.append(SimpleNamespace(**row))
		with patch("essdee_yrp.essdee_yrp.old_dc_grn_migration.cloth.frappe") as frappe:
			frappe.get_doc.return_value = ipd
			changes, log = ensure_process_chain("IPD", ["Knitting", "Bleaching", "Washing"], "Bleaching")
			self.assertEqual(changes, ["Bleaching in place of Dyeing", "Washing"])
			self.assertEqual([row.fabric_process for row in rows], ["Knitting", "Bleaching", "Washing"])
			self.assertEqual((ipd.dyeing_process, log), ("Bleaching", []))
			self.assertEqual(
				ensure_process_chain("IPD", ["Knitting", "Bleaching", "Washing"], "Bleaching"), ([], [])
			)

	def test_cloth_recipe_and_ipd_cloth_are_synced_only_when_they_differ(self):
		masters = "essdee_yrp.essdee_yrp.old_dc_grn_migration.masters"
		for same, expected in (
			(False, ["Cloth Yarn Recipe"] * len(CLOTH_YARN_RECIPES) + ["IPD Cloth"]),
			(True, []),
		):
			check = MasterCheck([])
			with (
				patch(f"{masters}.has_yarn_recipe", return_value=same),
				patch(
					f"{masters}.get_ipd_cloths",
					side_effect=lambda ipd, same=same: IPD_CLOTHS[ipd] if same else {},
				),
				patch(f"{masters}.get_lot_cloths", side_effect=lambda lot: set(LOT_CLOTH_PROGRAMS[lot])),
			):
				check.check_cloths()
			self.assertEqual([row["kind"] for row in check.sync], expected)

	def test_lot_cloth_programs_are_built_only_when_the_lot_lacks_a_cloth(self):
		masters = "essdee_yrp.essdee_yrp.old_dc_grn_migration.masters"
		for lot_cloths, expected in (
			({"36's GL Dyed Cloth"}, ["GY0926-10"]),
			(set(LOT_CLOTH_PROGRAMS["GY0926-10"]), []),
		):
			check = MasterCheck([])
			with (
				patch(f"{masters}.has_yarn_recipe", return_value=True),
				patch(f"{masters}.get_ipd_cloths", side_effect=lambda ipd: IPD_CLOTHS[ipd]),
				patch(
					f"{masters}.get_lot_cloths",
					side_effect=lambda lot, cloths=lot_cloths: (
						cloths if lot == "GY0926-10" else set(LOT_CLOTH_PROGRAMS[lot])
					),
				),
			):
				check.check_cloths()
			self.assertEqual(
				[row["name"] for row in check.sync if row["kind"] == "Lot Cloth Programs"], expected
			)

	def test_cloth_program_selection_keeps_the_prod_routes(self):
		routes = LOT_CLOTH_PROGRAMS["GY0926-10"]["36's GL Dyed Cloth"]
		with patch("essdee_yrp.essdee_yrp.old_dc_grn_migration.masters.frappe") as frappe:
			frappe.get_doc.return_value.get.return_value = [
				SimpleNamespace(yarn_item="Yarn 36's GL", ratio=100.0)
			]
			selection = get_cloth_program_selection("36's GL Dyed Cloth", routes)
		self.assertEqual(len(selection["fabric_routes"]), 9)
		self.assertEqual(
			{route["knitting_output_colour"] for route in selection["fabric_routes"]}, {"Greige"}
		)
		self.assertIn(
			{
				"finished_dia": "24 Dia",
				"finished_colour": "Red",
				"knitting_output_dia": "24 Dia",
				"knitting_output_colour": "Greige",
				"use_dyed_yarn": 0,
			},
			selection["fabric_routes"],
		)
		self.assertEqual({row["yarn_colour"] for row in selection["colour_yarn_recipes"]}, {"Greige"})

	def test_folding_dia_goes_to_the_second_cloth_through_every_process(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-09-11", ("GREY FABRIC", "14", 0, 120.0)),
			dc(11, "Knitting Program", "VIJAY", "2026-10-06", ("GREY FABRIC", "16", 0, 97.0)),
			grn(
				20,
				"VIJAY",
				"2026-10-13",
				[10, 11],
				("GREY FABRIC", "14", 18, 146.2),
				("GREY FABRIC", "16", 10, 101.7),
			),
			dc(12, "Bleaching", "KSM", "2026-10-13", ("WHITE", "14", 18, 146.2), ("WHITE", "16", 10, 101.7)),
			grn(21, "KSM", "2026-10-20", [12], ("WHITE", "16", 12, 98.0)),
		]
		mappings = LotMappings(
			{"WHITE": "White"}, SUPPLIERS, "Greige", {"GREY FABRIC": "Rib"}, {"White": ["Rib"]}
		)
		with patch.dict(f"{PLAN}.CLOTH_BY_DIA", {"L": {"14 Dia": "Folding"}}):
			plan = build_lot_plan("L", documents, mappings)
		cloths = {(w.dc.number, w.cloth): [line.dia for line in w.lines] for w in plan.work_orders}
		self.assertEqual(
			cloths,
			{
				("DC-10", "Folding"): ["14 Dia"],
				("DC-11", "Rib"): ["16 Dia"],
				("DC-12", "Folding"): ["14 Dia"],
				("DC-12", "Rib"): ["16 Dia"],
			},
		)
		folding_knitting = plan.work_orders[0]
		self.assertEqual([(g.number, g.lines[0].kg) for g in folding_knitting.grns], [("GRN-20", 146.2)])

	def test_grn_extra_dc_receives_another_dia_of_an_unlinked_program(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-09-11", ("GREY FABRIC", "14", 0, 132.0)),
			dc(11, "Knitting Program", "VIJAY", "2026-10-06", ("GREY FABRIC", "16", 0, 127.0)),
			grn(
				20,
				"VIJAY",
				"2026-10-20",
				[11],
				("GREY FABRIC", "15", 15, 125.8),
				("GREY FABRIC", "16", 15, 124.9),
			),
		]
		folding = {"L": {"14 Dia": "Folding", "15 Dia": "Folding"}}
		with patch.dict(f"{PLAN}.CLOTH_BY_DIA", folding):
			with self.assertRaisesRegex(PlanError, "GRN-20: GREY FABRIC 15 Dia 125.8 kg matches no line"):
				build_lot_plan("L", documents, MAPPINGS)
			with patch.dict(f"{PLAN}.GRN_EXTRA_DCS", {"GRN-20": ("DC-10",)}):
				folding_knitting, rib_knitting = build_lot_plan("L", documents, MAPPINGS).work_orders
		self.assertEqual(
			[(g.dia, g.planned_dia, g.kg) for g in folding_knitting.grns[0].lines],
			[("15 Dia", "14 Dia", 125.8)],
		)
		self.assertEqual([line.kg for line in folding_knitting.lines], [132.0])
		self.assertEqual([(g.dia, g.kg) for g in rib_knitting.grns[0].lines], [("16 Dia", 124.9)])

	def test_synthetic_grn_receives_the_next_dc_quantity_for_the_configured_lot_only(self):
		documents = [
			dc(10, "Bleaching", "KSM", "2026-10-20", ("WHITE", "15", 15, 125.8), ("WHITE", "16", 15, 124.9)),
			grn(20, "KSM", "2026-11-02", [10], ("WHITE", "16", 15, 119.0)),
			dc(11, "Steaming", "KSM", "2026-11-02", ("WHITE", "15", 15, 125.8)),
		]
		mappings = LotMappings({"WHITE": "White"}, SUPPLIERS, "Greige", {}, {"White": ["Rib"]})
		config = {"L": ({"dc": "DC-10", "from_dc": "DC-11"},)}
		with patch.dict(f"{PLAN}.SYNTHETIC_GRNS", config):
			plan = build_lot_plan("L", documents, mappings)
			other_bleaching, _ = build_lot_plan("L2", documents, mappings).work_orders
		bleaching, steaming = plan.work_orders
		derived = bleaching.grns[1]
		self.assertEqual((derived.number, derived.date), ("DERIVED-DC-11", "2026-11-02"))
		self.assertEqual([(line.dia, line.rolls, line.kg) for line in derived.lines], [("15 Dia", 15, 125.8)])
		self.assertIn("no Bleaching GRN for DC-10; quantity taken from Steaming DC DC-11", derived.remark)
		self.assertEqual([g.number for g in other_bleaching.grns], ["GRN-20"])
		dates = get_effective_dates(plan)
		self.assertEqual(dates[("DC", "DC-11", steaming.cloth)], "2026-11-02")
		with patch.dict(f"{PLAN}.SYNTHETIC_GRNS", {"L": ({"dc": "DC-11", "from_dc": "DC-10"},)}):
			with self.assertRaisesRegex(PlanError, "DC-10 \\(2026-10-20\\) is before DC-11"):
				build_lot_plan("L", documents, mappings)

	def test_line_dias_merge_a_wrong_dia_line_into_its_corrected_dia_for_the_configured_lot_only(self):
		documents = [
			dc(10, "Dyeing", "KSM", "2026-10-15", ("BLACK", "15", 1, 21.0), ("BLACK", "24", 2, 38.7)),
			grn(20, "KSM", "2026-10-28", [10], ("BLACK", "0", 3, 60.0)),
		]
		with patch.dict(f"{PLAN}.LINE_DIAS", {"L": {("DC-10", "BLACK", "15"): "24"}}):
			(dyeing,) = build_lot_plan("L", documents, MAPPINGS).work_orders
			(other,) = build_lot_plan("L2", documents, MAPPINGS).work_orders
			with patch.dict(f"{PLAN}.LINE_DIAS", {"L": {("DC-10", "BLACK", "16"): "24"}}):
				with self.assertRaisesRegex(PlanError, "LINE_DIAS line"):
					build_lot_plan("L", documents, MAPPINGS)
		self.assertEqual([(line.dia, line.rolls, line.kg) for line in dyeing.lines], [("24 Dia", 3, 59.7)])
		self.assertEqual([(line.dia, line.kg) for line in dyeing.grns[0].lines], [("24 Dia", 60.0)])
		self.assertEqual([line.dia for line in other.lines], ["15 Dia", "24 Dia"])

	def test_skipped_documents_are_dropped_for_the_configured_lot_only(self):
		documents = [
			dc(10, "Steaming", "KSM", "2026-10-15", ("BLACK", "14", 1, 20.0)),
			grn(20, "KSM", "2026-10-20", [10], ("BLACK", "14", 1, 20.0)),
			grn(21, "KSM", "2026-10-27", [10], ("BLACK", "14", 1, 20.0)),
		]
		with patch.dict(f"{PLAN}.SKIPPED_DOCUMENTS", {"L": {"GRN-21"}}):
			(steaming,) = build_lot_plan("L", documents, MAPPINGS).work_orders
			(other,) = build_lot_plan("L2", documents, MAPPINGS).work_orders
			with patch.dict(f"{PLAN}.SKIPPED_DOCUMENTS", {"L": {"GRN-99"}}):
				with self.assertRaisesRegex(PlanError, "SKIPPED_DOCUMENTS"):
					build_lot_plan("L", documents, MAPPINGS)
		self.assertEqual([grn.number for grn in steaming.grns], ["GRN-20"])
		self.assertEqual([grn.number for grn in other.grns], ["GRN-20", "GRN-21"])

	def test_yarn_is_needed_only_for_knitting_work_orders_this_run_creates(self):
		migrator = LotMigrator.__new__(LotMigrator)
		migrator.reused, migrator.migrated = {"WO-REAL"}, {"WO-TAGGED"}
		self.assertEqual(
			migrator.get_new_work_orders(["WO-TAGGED", "WO-NEW", "WO-REAL", "WO-NEW"]), ["WO-NEW"]
		)

	def test_batch_two_lots_plan_from_the_embedded_data(self):
		data = {lot["lot"]: lot for lot in LOTS}
		plans = {lot: build_lot_plan_from_snapshot(data[lot]) for lot in RUN_LOTS}
		grns = {
			lot: {grn.number: grn for work_order in plan.work_orders for grn in work_order.grns}
			for lot, plan in plans.items()
		}
		self.assertNotIn("GRN-2526-11024", grns["F0926-48"])
		self.assertIn("GRN-2526-10862", grns["F0926-48"])
		self.assertNotIn("28 Dia", {line.dia for line in grns["F0926-55"]["GRN-2526-10976"].lines})
		self.assertEqual(YARN_RATES["GY0926-11"], {"Yarn 34's-G Mel": 337.15, "Yarn 36's RL-Greige": 338})

	def test_dc_cloths_and_grn_links_split_one_old_colour_over_two_cloths(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-07", ("GREY FABRIC", "26", 2, 36.0)),
			dc(11, "Knitting Program", "VIJAY", "2026-10-07", ("GREY FABRIC", "26", 0, 18.0)),
			grn(20, "VIJAY", "2026-10-16", [11], ("GREY FABRIC", "26", 2, 36.6)),
			grn(21, "VIJAY", "2026-10-23", [11], ("GREY FABRIC", "26", 5, 18.5)),
			dc(12, "Washing", "KSM", "2026-10-24", ("GREY FABRIC", "26", 5, 18.5)),
			grn(22, "KSM", "2026-11-04", [12], ("GREY FABRIC", "0", 5, 18.0)),
		]
		config = {
			"L": {
				"DC-10": ("Dyed Cloth", None),
				"DC-11": ("White Fabric", "White"),
				"DC-12": ("White Fabric", "White"),
			}
		}
		with (
			patch.dict(f"{PLAN}.DC_CLOTHS", config),
			patch.dict(f"{PLAN}.GRN_LINKS", {"GRN-20": ("DC-10",)}),
		):
			plan = build_lot_plan("L", documents, MAPPINGS)
		summary = {
			(w.dc.number, w.cloth): [(g.number, [(line.colour, line.kg) for line in g.lines]) for g in w.grns]
			for w in plan.work_orders
		}
		self.assertEqual(
			summary,
			{
				("DC-10", "Dyed Cloth"): [("GRN-20", [("Greige", 36.6)])],
				("DC-11", "White Fabric"): [("GRN-21", [("White", 18.5)])],
				("DC-12", "White Fabric"): [("GRN-22", [("White", 18.0)])],
			},
		)
		self.assertEqual(plan.get_stages("White Fabric"), ["Knitting", "Washing"])

	def test_cloth_stages_follow_the_ipd_order_when_set(self):
		documents = [
			dc(10, "Knitting Program", "VIJAY", "2026-10-01", ("BLACK", "26", 1, 10.0)),
			grn(20, "VIJAY", "2026-10-05", [10], ("BLACK", "26", 1, 10.0)),
			dc(11, "Washing", "KSM", "2026-10-06", ("BLACK", "26", 1, 10.0)),
			grn(21, "KSM", "2026-10-09", [11], ("BLACK", "26", 1, 10.0)),
			dc(12, "Dyeing", "KSM", "2026-10-08", ("BLACK", "26", 1, 10.0)),
		]
		plan = build_lot_plan("L", documents, MAPPINGS)
		self.assertEqual(plan.get_stages("Rib"), ["Knitting", "Dyeing", "Washing"])
		self.assertEqual(get_effective_dates(plan)[("DC", "DC-11", "Rib")], "2026-10-06")
		plan.cloth_processes["Rib"] = ["Knitting", "Washing", "Dyeing"]
		self.assertEqual(get_effective_dates(plan)[("DC", "DC-12", "Rib")], "2026-10-09")

	def accessory_lot(self, accessory_dias, other_lots=()):
		lot = SimpleNamespace(name="L", production_detail="IPD")
		saved = []
		ipd = SimpleNamespace(save=lambda: saved.append(ipd.cloth_accessory_json))
		items = [{"Colour": "Black", "Accessory": "Folding", "Dia": dia} for dia in accessory_dias]
		with (
			patch.dict(f"{CLOTH}.IPD_ACCESSORY_DIAS", {"L": ("IPD", "26 Dia", "24 Dia")}),
			patch(f"{CLOTH}.frappe") as frappe,
		):
			frappe.throw.side_effect = raise_plan_error
			frappe.get_all.return_value = list(other_lots)
			frappe.db.get_value.side_effect = lambda _doctype, _name, field: (
				"Not Approved" if field == "approval_status" else json.dumps({"items": items})
			)
			frappe.get_doc.return_value = ipd
			result = ensure_accessory_dias(lot)
		return result, saved

	def test_accessory_dia_is_changed_on_the_lot_ipd(self):
		(change, log), saved = self.accessory_lot(["26 Dia", "26 Dia"])
		self.assertEqual((change, log), ("IPD: accessory 26 Dia changed to 24 Dia", []))
		self.assertEqual([row["Dia"] for row in json.loads(saved[0])["items"]], ["24 Dia", "24 Dia"])
		self.assertEqual(self.accessory_lot(["24 Dia"]), ((None, []), []))

	def test_accessory_dia_change_stops_on_a_shared_or_unexpected_ipd(self):
		with self.assertRaisesRegex(PlanError, "also used by lot"):
			self.accessory_lot(["26 Dia"], other_lots=["L2"])
		with self.assertRaisesRegex(PlanError, "has no accessory in 26 Dia"):
			self.accessory_lot(["36 Dia"])

	def test_process_rates_cover_every_key_with_colour_wise_dyeing(self):
		self.assertEqual(len(PROCESS_RATES), 45)
		for key, rate in PROCESS_RATES.items():
			rates = rate.values() if key.startswith("Dyeing|") else [rate]
			self.assertIsInstance(rate, dict if key.startswith("Dyeing|") else float, key)
			self.assertTrue(rates and all(value > 1 for value in rates), key)

	def build_process_cost(self, rate, colours, placeholder_rates=False):
		work_order = SimpleNamespace(
			process_name="Dyeing",
			supplier="S",
			item="Cloth",
			lot="L",
			wo_date="2026-10-01",
			receivables=[SimpleNamespace(item_variant=colour) for colour in colours],
			get_receivable_process_cost=lambda: None,
		)
		doc = SimpleNamespace(values=[], fields={}, name="PC-1", docstatus=1, workflow_state="Approved")
		doc.update = doc.fields.update
		doc.append = lambda _table, row: doc.values.append(row)
		doc.insert = lambda: None
		with (
			patch.dict(f"{PROCESS_COST}.PROCESS_RATES", {"Dyeing|S|Cloth": rate}, clear=True),
			patch(f"{PROCESS_COST}.frappe") as frappe,
			patch(f"{PROCESS_COST}.apply_workflow", return_value=doc),
			patch(f"{PROCESS_COST}.get_variant_attributes", side_effect=lambda variant: {"Colour": variant}),
			patch(
				f"{PROCESS_COST}.attribute_links.link",
				side_effect=lambda value, attribute: f"{attribute}:{value}",
			),
		):
			frappe.new_doc.return_value = doc
			frappe.db.get_value.return_value = None
			name, missing = ensure_process_cost(work_order, placeholder_rates)
		return name, missing, doc

	def test_process_cost_is_colour_wise_for_a_colour_rate(self):
		name, missing, doc = self.build_process_cost(
			{"Red": 80.0, "Navy": 72.0, "Grey": 70.0}, ["Red", "Navy", "Red"]
		)
		self.assertEqual((name, missing), ("PC-1", []))
		self.assertEqual((doc.fields["depends_on_attribute"], doc.fields["attribute"]), (1, "Colour"))
		self.assertEqual(
			doc.values,
			[
				{"price": 72.0, "attribute_value": "Colour:Navy"},
				{"price": 80.0, "attribute_value": "Colour:Red"},
			],
		)

	def test_process_cost_single_rate_has_no_attribute(self):
		_name, missing, doc = self.build_process_cost(13.0, ["Red", "Navy"])
		self.assertEqual(missing, [])
		self.assertNotIn("attribute", doc.fields)
		self.assertEqual(doc.values, [{"price": 13.0, "attribute_value": None}])

	def test_process_cost_fails_on_a_colour_without_rate(self):
		with self.assertRaises(ProcessRateMissing) as error:
			self.build_process_cost({"Red": 80.0}, ["Red", "Peach"])
		self.assertEqual(error.exception.needed, ["Dyeing|S|Cloth [Peach]"])
		_name, missing, doc = self.build_process_cost({"Red": 80.0}, ["Red", "Peach"], placeholder_rates=True)
		self.assertEqual(missing, ["Dyeing|S|Cloth [Peach]"])
		self.assertEqual([row["price"] for row in doc.values], [1.0, 80.0])
