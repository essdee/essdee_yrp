from unittest import TestCase

from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics
from essdee_yrp.planning.dashboard.production_orders import get_ppo_quantity
from essdee_yrp.planning.dashboard.set_quantities import SetQuantities, count_sets, get_major_colour


def facts(**values):
	return {
		"planned": 1000,
		"cut": 0,
		"dispatch": 0,
		"to_alternative": 0,
		"pack_delivered": 0,
		"sewing_delivered": 0,
		"sewing_received": 0,
		"cutting_status": "",
		"lay_sheets": 0,
		"has_work_order": True,
		"has_cutting_plan": False,
		"has_cutting_work_order": False,
		"is_cutting_delivered": False,
		"fabric_process": "",
		"fabric_step": 0,
		"purchase_status": "",
		**values,
	}


class TestLotStatusLadder(TestCase):
	def status(self, **values):
		return ladder.get_lot_status(facts(**values))

	def test_dispatched_above_ninety_percent_of_basis(self):
		self.assertEqual(self.status(dispatch=901), "Dispatched")

	def test_pieces_moved_to_alternative_count_as_dispatched(self):
		self.assertEqual(self.status(dispatch=550, to_alternative=400), "Dispatched")
		self.assertEqual(self.status(to_alternative=400), "Packing in progress")

	def test_exactly_ninety_percent_dispatched_is_not_dispatched(self):
		self.assertEqual(self.status(dispatch=900), "Packing in progress")

	def test_basis_is_cut_when_cut_exists(self):
		self.assertEqual(self.status(cut=2000, dispatch=1000), "Packing in progress")

	def test_packing_in_progress_from_packing_delivered(self):
		self.assertEqual(self.status(pack_delivered=1), "Packing in progress")

	def test_ready_for_packing_at_exactly_ninety_percent_sewn(self):
		self.assertEqual(self.status(sewing_received=900), "Ready for packing")

	def test_in_sewing_when_sewing_issued(self):
		self.assertEqual(self.status(sewing_delivered=10), "In sewing")

	def test_in_sewing_when_sewing_output_below_ninety_percent(self):
		self.assertEqual(self.status(sewing_received=899), "In sewing")

	def test_waiting_for_sewing_after_cutting_plan_completed(self):
		self.assertEqual(self.status(cutting_status="Completed"), "Waiting for sewing")
		self.assertEqual(self.status(cutting_status="Cut Panel Dispatch Pending"), "Waiting for sewing")

	def test_in_cutting_with_lay_sheets(self):
		self.assertEqual(self.status(cutting_status="Cutting In Progress", lay_sheets=2), "In cutting")

	def test_in_cutting_when_cutting_work_order_has_a_delivery_challan(self):
		self.assertEqual(self.status(has_cutting_work_order=True, is_cutting_delivered=True), "In cutting")

	def test_waiting_for_cutting_needs_cutting_plan_and_cutting_work_order(self):
		self.assertEqual(
			self.status(has_cutting_plan=True, has_cutting_work_order=True, fabric_process="Dyeing"),
			"Waiting for cutting",
		)

	def test_cutting_work_order_without_cutting_plan_is_not_waiting_for_cutting(self):
		self.assertEqual(self.status(has_cutting_work_order=True), "Fabric not received")

	def test_fabric_process_when_cutting_work_order_missing(self):
		self.assertEqual(self.status(has_cutting_plan=True, fabric_process="Knitting"), "Knitting")

	def test_fabric_not_received_with_cutting_plan_and_no_cutting_work_order(self):
		self.assertEqual(self.status(has_cutting_plan=True, cutting_status="Planned"), "Fabric not received")

	def test_cutting_plan_without_work_order_is_fabric_not_received(self):
		self.assertEqual(self.status(has_work_order=False, has_cutting_plan=True), "Fabric not received")

	def test_no_work_order_yet_without_work_order_or_cutting_plan(self):
		self.assertEqual(self.status(has_work_order=False), ladder.NO_WORK_ORDER)

	def test_po_created_without_work_order_while_receipts_are_below_ninety_percent(self):
		self.assertEqual(self.status(has_work_order=False, purchase_status=ladder.PO_CREATED), "PO Created")

	def test_material_received_without_work_order(self):
		self.assertEqual(
			self.status(has_work_order=False, purchase_status=ladder.MATERIAL_RECEIVED),
			"Yarn / Fabric Received",
		)

	def test_work_order_outranks_purchase_status(self):
		self.assertEqual(
			self.status(purchase_status=ladder.PO_CREATED, fabric_process="Knitting"), "Knitting"
		)

	def test_fabric_not_received_otherwise(self):
		self.assertEqual(self.status(), "Fabric not received")

	def test_zero_basis_never_dispatched(self):
		self.assertEqual(self.status(planned=0, dispatch=5), "Packing in progress")


class TestFabricProcess(TestCase):
	def test_steps_take_the_furthest_position_over_cloth_routes(self):
		routes = [["Knitting", "Dyeing", "Washing"], ["Knitting", "Bleaching"]]
		self.assertEqual(
			ladder.get_fabric_steps(routes), {"Knitting": 0, "Dyeing": 1, "Washing": 2, "Bleaching": 1}
		)

	def test_furthest_route_process_with_a_work_order(self):
		steps = {"Knitting": 0, "Dyeing": 1, "Washing": 2}
		orders = [{"process_name": name} for name in ("Washing", "Knitting", "Cutting", "Dyeing")]
		self.assertEqual(ladder.get_fabric_process(orders, steps), ("Washing", 2))

	def test_processes_outside_the_route_are_ignored(self):
		orders = [{"process_name": "Printing"}, {"process_name": "Cutting"}]
		self.assertEqual(ladder.get_fabric_process(orders, {"Knitting": 0}), ("", 0))

	def test_rank_places_fabric_processes_between_fabric_not_received_and_waiting_for_cutting(self):
		rank = ladder.get_status_rank
		ranks = [
			rank(ladder.NO_WORK_ORDER, 0),
			rank(ladder.PO_CREATED, 0),
			rank(ladder.MATERIAL_RECEIVED, 0),
			rank("Fabric not received", 0),
			rank("Knitting", 0),
			rank("Dyeing", 1),
			rank("Waiting for cutting", 0),
			rank("Dispatched", 0),
		]
		self.assertEqual(ranks, sorted(ranks))
		self.assertEqual(len(set(ranks)), len(ranks))


class TestPurchaseStatus(TestCase):
	def test_no_qualifying_purchase_order_is_empty(self):
		self.assertEqual(ladder.get_purchase_status(0, 0), "")

	def test_below_ninety_percent_received_is_po_created(self):
		self.assertEqual(ladder.get_purchase_status(100, 89.9), ladder.PO_CREATED)

	def test_ninety_percent_received_is_material_received(self):
		self.assertEqual(ladder.get_purchase_status(100, 90), ladder.MATERIAL_RECEIVED)


class TestPoCreatedPieces(TestCase):
	def pieces(self, status="Knitting", purchase_status=ladder.PO_CREATED, moved=1200):
		return ladder.get_po_created_pieces(status, purchase_status, basis=1000, ordered=3000, moved=moved)

	def test_lot_pieces_less_the_share_moved_into_fabric_processes(self):
		self.assertEqual(self.pieces(), 600)

	def test_nothing_left_on_order_once_moved_covers_the_order(self):
		self.assertEqual(self.pieces(moved=3500), 0)

	def test_fabric_not_received_keeps_every_piece_on_order(self):
		self.assertEqual(self.pieces(status="Fabric not received", moved=0), 1000)

	def test_no_split_once_the_lot_reaches_cutting(self):
		self.assertEqual(self.pieces(status="Waiting for cutting"), 0)

	def test_no_split_once_receipts_reach_ninety_percent(self):
		self.assertEqual(self.pieces(purchase_status=ladder.MATERIAL_RECEIVED), 0)

	def test_no_split_for_a_lot_still_without_work_order(self):
		self.assertEqual(self.pieces(status=ladder.PO_CREATED), 0)


class TestCuttingStatus(TestCase):
	def test_highest_ranked_cutting_plan_status_wins(self):
		self.assertEqual(
			ladder.get_best_cutting_status(["Planned", "Completed", "Cutting In Progress"]), "Completed"
		)

	def test_no_cutting_plan_is_empty(self):
		self.assertEqual(ladder.get_best_cutting_status([]), "")


class TestLotQuantities(TestCase):
	sewing = {"Stitching", "Stitching and Packing", "Bottom Fusing and Stitching"}

	def quantities(self, orders, received):
		return ladder.get_lot_quantities(
			orders, lambda chosen: sum(received.get(order["name"], 0) for order in chosen), self.sewing
		)

	def test_cut_stitching_and_packed_from_their_work_orders(self):
		orders = [
			{"name": "WO-1", "process_name": "Cutting", "includes_packing": 0},
			{"name": "WO-2", "process_name": "Stitching", "includes_packing": 0},
			{"name": "WO-3", "process_name": "Ironing and Packing", "includes_packing": 1},
			{"name": "WO-4", "process_name": "Printing", "includes_packing": 0},
		]
		result = self.quantities(orders, {"WO-1": 100, "WO-2": 90, "WO-3": 80, "WO-4": 70})
		self.assertEqual(result, {"cut": 100, "stitch": 90, "packed": 80})

	def test_stitching_and_packing_with_packing_counts_in_both(self):
		orders = [{"name": "WO-1", "process_name": "Stitching and Packing", "includes_packing": 1}]
		self.assertEqual(self.quantities(orders, {"WO-1": 1936}), {"cut": 0, "stitch": 1936, "packed": 1936})

	def test_stitching_and_packing_without_packing_counts_only_in_stitching(self):
		orders = [{"name": "WO-1", "process_name": "Stitching and Packing", "includes_packing": 0}]
		self.assertEqual(self.quantities(orders, {"WO-1": 6616}), {"cut": 0, "stitch": 6616, "packed": 0})

	def test_each_work_order_counts_once(self):
		orders = [{"name": "WO-1", "process_name": "Stitching", "includes_packing": 0}] * 2
		self.assertEqual(self.quantities(orders, {"WO-1": 50})["stitch"], 50)

	def test_balance_is_ppo_share_less_dispatched(self):
		self.assertEqual(ladder.get_balance(ppo_quantity=120, dispatch=50), 70)
		self.assertEqual(ladder.get_balance(ppo_quantity=120, dispatch=150), -30)
		self.assertEqual(ladder.get_balance(ppo_quantity=1000, dispatch=0), 1000)

	def test_balance_does_not_subtract_moved_pieces_again(self):
		# PPO-00039 / F0426-82/1: the 4,095 share already excludes the 4,483 pcs moved to the alternative item.
		self.assertEqual(ladder.get_balance(ppo_quantity=4095, dispatch=4520), -425)


class TestSewingProcesses(TestCase):
	def test_groups_containing_the_setting_count_as_sewing(self):
		details = [
			{"parent": "Stitching and Packing", "process_name": "Stitching"},
			{"parent": "Stitching and Packing", "process_name": "Packing"},
			{"parent": "Bottom Fusing and Stitching", "process_name": "Stitching"},
			{"parent": "Ironing and Packing", "process_name": "Ironing"},
		]
		used = [
			"Stitching",
			"Stitching and Packing",
			"Bottom Fusing and Stitching",
			"Ironing and Packing",
			"Packing",
		]
		self.assertEqual(
			ladder.get_sewing_processes("Stitching", details, used),
			["Bottom Fusing and Stitching", "Stitching", "Stitching and Packing"],
		)

	def test_no_setting_means_no_sewing_process(self):
		self.assertEqual(ladder.get_sewing_processes(None, [], ["Stitching"]), [])


class TestPpoPieces(TestCase):
	def test_packing_combo_when_the_lots_agree_with_it(self):
		self.assertEqual(ladder.get_pieces_per_box(4165, 835, [5, 5, None]), 5)
		self.assertEqual(ladder.get_pieces_per_box(0, 0, [12]), 12)

	def test_lots_own_pieces_per_box_when_the_combo_disagrees(self):
		self.assertEqual(ladder.get_pieces_per_box(2186, 2186, [30]), 1)
		self.assertEqual(ladder.get_pieces_per_box(1000, 100, [6, 12]), 10)

	def test_no_pieces_per_box(self):
		self.assertIsNone(ladder.get_pieces_per_box(0, 0, [None, 0]))
		self.assertEqual(ladder.get_ppo_pieces(554, None, 0), (None, ""))

	def test_pieces_are_boxes_times_pieces_per_box(self):
		self.assertEqual(ladder.get_ppo_pieces(100.5, 12, 1206), (1206, "boxes"))
		self.assertEqual(ladder.get_ppo_pieces(1900, 5, 4165), (9500, "boxes"))

	def test_quantity_already_in_pieces_is_kept(self):
		self.assertEqual(ladder.get_ppo_pieces(1896, 50, 1914), (1896, "pieces"))
		self.assertEqual(ladder.get_ppo_pieces(6000, 206, 6180), (6000, "pieces"))
		self.assertEqual(ladder.get_ppo_pieces(15000, 1, 15000), (15000, "boxes"))

	def test_split_follows_the_boxes_each_lot_took(self):
		self.assertEqual(ladder.split_quantity(1000, {"A": 30, "B": 10}), {"A": 750, "B": 250})
		self.assertEqual(ladder.split_quantity(90, {"A": 0, "B": 0, "C": 0}), {"A": 30, "B": 30, "C": 30})
		self.assertEqual(ladder.split_quantity(90, {}), {})


class TestDispatchMultiplier(TestCase):
	def test_batch_tracked_packing_dispatches_pieces(self):
		self.assertEqual(ladder.get_dispatch_multiplier(True, 12), 1)

	def test_box_packing_dispatches_boxes_times_pieces_per_box(self):
		self.assertEqual(ladder.get_dispatch_multiplier(False, 12), 12)


class TestProcessRows(TestCase):
	def test_kind_by_item_cutting_and_packing(self):
		kind = ladder.get_process_kind
		self.assertEqual(kind("Knitting", [{"item": "Fabric", "includes_packing": 0}], "Vest"), "cloth")
		self.assertEqual(kind("Cutting", [{"item": "Vest", "includes_packing": 0}], "Vest"), "cutting")
		self.assertEqual(
			kind("Ironing and Packing", [{"item": "Vest", "includes_packing": 1}], "Vest"),
			"packing",
		)
		self.assertEqual(kind("Printing", [{"item": "Vest", "includes_packing": 0}], "Vest"), "item")

	def test_status_reason_names_one_work_order_or_counts_done(self):
		self.assertEqual(
			ladder.get_status_reason([{"status": "Partially Received", "docstatus": 1}]),
			"WO Partially Received",
		)
		orders = [
			{"status": "Closed", "docstatus": 1},
			{"status": "Fully Received", "docstatus": 1},
			{"status": "Partially Delivered", "docstatus": 1},
		]
		self.assertEqual(ladder.get_status_reason(orders), "2 of 3 WOs done")

	def test_processes_sort_by_first_dc_with_no_dc_last(self):
		rows = [
			{"name": "C", "first_dc": None},
			{"name": "B", "first_dc": "2026-09-01"},
			{"name": "A", "first_dc": "2026-08-01"},
		]
		self.assertEqual([row["name"] for row in ladder.sort_by_first_dc(rows)], ["A", "B", "C"])


class TestLotSummaryBalance(TestCase):
	"""Cut is what Cutting Work Orders received, never planned pieces."""

	def summary(self, received_cut, dispatch=0.0, moved=0.0):
		metrics = LotMetrics(
			[{"name": "LOT-1", "item": "VEST", "total_order_quantity": 1000}], sewing_processes=[]
		)
		metrics.__dict__.update(
			orders=[],
			sets=SetQuantities({}, []),
			orders_by_lot={
				"LOT-1": [
					{"name": "WO-CUT", "process_name": "Cutting", "is_rework": 0, "includes_packing": 0}
				]
			},
			item_totals={"WO-CUT": {"planned": 1000, "delivered": 1000, "received": received_cut}},
			order_quantities={"LOT-1": (1000, 0)},
			cutting_statuses={"LOT-1": "Cutting In Progress"},
			lay_sheets={"LOT-1": 1},
			cutting_delivered=set(),
			fabric_routes={},
			purchase_lines={},
			dispatch={"LOT-1": dispatch},
			alternatives={"LOT-1": [{"quantity": moved}] if moved else []},
		)
		return metrics.get_summary("LOT-1")

	def test_lot_in_cutting_with_nothing_received_has_no_cut(self):
		summary = self.summary(received_cut=0)
		self.assertEqual(summary["status"], "In cutting")
		self.assertEqual((summary["cut"], summary["total"], summary["qty"]), (0, 1000, 1000))

	def test_cut_is_what_cutting_received(self):
		summary = self.summary(received_cut=800, dispatch=300, moved=100)
		self.assertEqual((summary["cut"], summary["dispatch"], summary["to_alternative"]), (800, 300, 100))


class TestSetCounts(TestCase):
	"""A set item counts complete sets: per major colour and size, the fewest of its parts."""

	ATTRIBUTES = {
		"TOP-RED-S": {"Part": "Top", "Size": "S"},
		"BOTTOM-NAVY-S": {"Part": "Bottom", "Size": "S"},
		"TOP-RED-M": {"Part": "Top", "Size": "M"},
		"BOTTOM-NAVY-M": {"Part": "Bottom", "Size": "M"},
		"SET-RED-S": {"Size": "S"},
	}
	RED = '{"major_colour": "Red", "major_part": "Top"}'

	def count(self, rows, parts=("Bottom", "Top")):
		return count_sets(rows, self.ATTRIBUTES, "Part", "Size", list(parts))

	def test_parts_are_never_added(self):
		rows = [("TOP-RED-S", self.RED, 100), ("BOTTOM-NAVY-S", self.RED, 100)]
		self.assertEqual(self.count(rows), 100)

	def test_a_set_needs_every_part(self):
		rows = [
			("TOP-RED-S", self.RED, 80),
			("BOTTOM-NAVY-S", self.RED, 50),
			("TOP-RED-M", self.RED, 40),
		]
		self.assertEqual(self.count(rows), 50)

	def test_whole_set_variants_count_as_they_are(self):
		self.assertEqual(self.count([("SET-RED-S", self.RED, 30)]), 30)

	def test_no_rows_no_sets(self):
		self.assertEqual(self.count([]), 0)
		self.assertEqual(get_major_colour(""), "")


class TestPpoQuantity(TestCase):
	"""PPO pieces split over its lots by the boxes each took, so lot shares add up to the PPO."""

	def lots(self, *rows):
		return [
			{"name": name, "packing_combo": combo, "total_quantity": boxes} for name, combo, boxes in rows
		]

	def test_boxes_times_combo_split_by_ordered_boxes(self):
		lots = self.lots(("A", 10, 30), ("B", 10, 10))
		result = get_ppo_quantity(50, lots, {"A": 300, "B": 100}, {"A": 30, "B": 10})
		self.assertEqual((result["pieces"], result["conversion"]), (500, "packing combo"))
		self.assertEqual(result["lot_shares"], {"A": 375, "B": 125})

	def test_ppo_stored_in_pieces_keeps_its_quantity(self):
		result = get_ppo_quantity(1896, self.lots(("F0826-19", 50, 41)), {"F0826-19": 1914}, {"F0826-19": 41})
		self.assertEqual((result["pieces"], result["conversion"]), (1896, "stored in pieces"))

	def test_lot_boxes_disagreeing_with_combo_use_the_lots_own_ratio(self):
		result = get_ppo_quantity(2186, self.lots(("F0826-32", 30, 2186)), {"F0826-32": 2186}, {})
		self.assertEqual((result["pieces"], result["conversion"]), (2186, "lots' pieces per box"))
		self.assertEqual(result["lot_shares"], {"F0826-32": 2186})

	def test_no_pieces_per_box_counts_nothing(self):
		result = get_ppo_quantity(11750, self.lots(("A", 0, 0)), {"A": 0}, {})
		self.assertEqual((result["pieces"], result["lot_shares"]), (None, {"A": 0}))
