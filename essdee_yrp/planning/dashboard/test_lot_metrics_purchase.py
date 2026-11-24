from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.planning.dashboard.dashboard import get_lot_row
from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics
from essdee_yrp.planning.dashboard.tracking import get_tracked_lots

GROUP = "TDPS Yarn Group"
PREFIX = "TDPS-"


def insert(doctype, **values):
	columns = ", ".join(f"`{column}`" for column in values)
	placeholders = ", ".join(["%s"] * len(values))
	frappe.db.sql(f"insert into `tab{doctype}` ({columns}) values ({placeholders})", tuple(values.values()))


class TestLotMetricsPurchaseStatus(TestCase):
	"""Raw fixture rows, rolled back after each test, so no live lot is read."""

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		groups = patch(
			"essdee_yrp.planning.dashboard.lot_metrics.get_approval_item_groups", return_value={GROUP}
		)
		groups.start()
		self.addCleanup(groups.stop)
		insert("Item", name=f"{PREFIX}Yarn", item_group=GROUP)
		insert("Item", name=f"{PREFIX}Yarn-Red", item_group="Other", variant_of=f"{PREFIX}Yarn")
		insert("Item", name=f"{PREFIX}Button", item_group="Other")

	def lot(self, suffix, planned=1000, folding=0):
		name = f"{PREFIX}{suffix}"
		insert("SD YRP Lot", name=name, is_folding_lot=folding, total_order_quantity=planned, status="Open")
		insert(
			"SD YRP Lot Order Detail",
			name=f"{name}-OD",
			parent=name,
			parenttype="SD YRP Lot",
			parentfield="lot_order_details",
			quantity=planned,
		)
		return name

	def purchase(
		self, lot, qty, received, item=f"{PREFIX}Yarn-Red", development=0, cancelled=0, docstatus=1, uom="Kg"
	):
		order = f"{lot}-PO-{frappe.generate_hash(length=6)}"
		insert("Purchase Order", name=order, docstatus=docstatus, is_development=development)
		insert(
			"Purchase Order Item",
			name=f"{order}-1",
			parent=order,
			parenttype="Purchase Order",
			parentfield="items",
			docstatus=docstatus,
			lot=lot,
			item_code=item,
			qty=qty,
			received_qty=received,
			cancelled_quantity=cancelled,
			uom=uom,
		)
		return order

	def work_order(self, lot, process, delivered, qty=1000):
		order = f"{lot}-WO-{process}"
		insert(
			"YRP Work Order",
			name=order,
			lot=lot,
			process_name=process,
			docstatus=1,
			is_rework=0,
			item="Cloth",
		)
		insert(
			"YRP Work Order Deliverables",
			name=f"{order}-D",
			parent=order,
			parenttype="YRP Work Order",
			parentfield="deliverables",
			qty=qty,
			pending_quantity=qty - delivered,
		)

	def route(self, lot, processes):
		ipd = f"{lot}-IPD"
		insert(
			"SD YRP Lot Fabric Detail",
			name=f"{lot}-FD",
			parent=lot,
			parenttype="SD YRP Lot",
			parentfield="fabric_details",
			production_detail=ipd,
		)
		for index, process in enumerate(processes, start=1):
			insert(
				"SD YRP IPD Fabric Process",
				name=f"{ipd}-{index}",
				parent=ipd,
				parenttype="SD YRP Item Production Detail",
				parentfield="fabric_processes",
				sequence=index,
				idx=index,
				fabric_process=process,
			)

	def summaries(self, *names):
		metrics = LotMetrics(
			[{"name": name, "item": "Vest", "total_order_quantity": 1000} for name in names],
			sewing_processes=[],
		)
		return {name: metrics.get_summary(name) for name in names}

	def test_po_below_ninety_percent_received_is_po_created(self):
		lot = self.lot("A")
		self.purchase(lot, 600, 300)
		self.purchase(lot, 400, 289)
		self.assertEqual(self.summaries(lot)[lot]["status"], ladder.PO_CREATED)

	def test_ninety_percent_received_without_work_order_is_material_received(self):
		lot = self.lot("B")
		self.purchase(lot, 1000, 900)
		self.assertEqual(self.summaries(lot)[lot]["status"], ladder.MATERIAL_RECEIVED)

	def test_cancelled_quantity_is_not_expected(self):
		lot = self.lot("C")
		self.purchase(lot, 1000, 810, cancelled=100)
		self.assertEqual(self.summaries(lot)[lot]["status"], ladder.MATERIAL_RECEIVED)

	def test_development_draft_folding_and_other_groups_stay_no_work_order(self):
		development, draft, folding, other = (
			self.lot("D"),
			self.lot("E"),
			self.lot("F", folding=1),
			self.lot("G"),
		)
		self.purchase(development, 1000, 0, development=1)
		self.purchase(draft, 1000, 0, docstatus=0)
		self.purchase(folding, 1000, 0)
		self.purchase(other, 1000, 0, item=f"{PREFIX}Button")
		statuses = {
			name: row["status"] for name, row in self.summaries(development, draft, folding, other).items()
		}
		self.assertEqual(set(statuses.values()), {ladder.NO_WORK_ORDER})

	def test_knitting_lot_still_on_po_splits_the_unmoved_share(self):
		lot = self.lot("H")
		self.route(lot, ["Knitting", "Dyeing"])
		self.purchase(lot, 1000, 500)
		self.work_order(lot, "Knitting", delivered=400)
		self.work_order(lot, "Dyeing", delivered=300)
		summary = self.summaries(lot)[lot]
		self.assertEqual(summary["status"], "Dyeing")
		self.assertEqual(
			summary["purchase_split"],
			{
				"status": ladder.PO_CREATED,
				"status_rank": ladder.get_status_rank(ladder.PO_CREATED, 0),
				"pieces": 600,
			},
		)

	def test_no_split_once_received_or_without_po(self):
		received, without = self.lot("I"), self.lot("J")
		self.route(received, ["Knitting"])
		self.route(without, ["Knitting"])
		self.purchase(received, 1000, 950)
		self.work_order(received, "Knitting", delivered=100)
		self.work_order(without, "Knitting", delivered=100)
		summaries = self.summaries(received, without)
		self.assertEqual([summaries[name]["purchase_split"] for name in (received, without)], [None, None])

	def test_dashboard_row_carries_the_split(self):
		lot = self.lot("K")
		self.route(lot, ["Knitting"])
		self.purchase(lot, 1000, 100)
		self.work_order(lot, "Knitting", delivered=250)
		lot_row = {"name": lot, "production_order": "PPO", "item": "Vest", "total_order_quantity": 1000}
		metrics = LotMetrics([lot_row], sewing_processes=[])
		row = get_lot_row(lot_row, {"delivery": None, "lot_shares": {lot: 1200}}, metrics, True)
		self.assertEqual(row["purchase_split"]["pieces"], 750)
		self.assertEqual((row["qty"], row["ppo_qty"], row["balance"]), (1000, 1200, 1200))

	def test_purchase_summary_totals_each_unit_over_qualifying_pos(self):
		lot = self.lot("L")
		first = self.purchase(lot, 600, 300)
		second = self.purchase(lot, 400, 100, cancelled=50)
		metres = self.purchase(lot, 200, 200, uom="Meter")
		self.purchase(lot, 2700, 2700, development=1)
		self.purchase(lot, 500, 0, docstatus=0)
		self.purchase(lot, 900, 0, item=f"{PREFIX}Button")
		metrics = LotMetrics([{"name": lot, "item": "Vest"}], sewing_processes=[])
		self.assertEqual(
			metrics.get_purchase_summary(lot),
			{
				"units": [
					{"uom": "Kg", "ordered": 950, "received": 400},
					{"uom": "Meter", "ordered": 200, "received": 200},
				],
				"purchase_orders": sorted([first, second, metres]),
			},
		)
		self.assertEqual(metrics.purchase_totals[lot], (1150, 600))

	def test_purchase_summary_is_empty_without_a_qualifying_po(self):
		lot, folding = self.lot("M"), self.lot("N", folding=1)
		self.purchase(lot, 1000, 0, development=1)
		self.purchase(folding, 1000, 0)
		metrics = LotMetrics([{"name": name, "item": "Vest"} for name in (lot, folding)], sewing_processes=[])
		self.assertEqual([metrics.get_purchase_summary(name) for name in (lot, folding)], [None, None])

	def test_tracking_covers_started_lots_and_lots_with_a_po(self):
		ordered, started, idle = self.lot("O"), self.lot("P"), self.lot("Q")
		self.purchase(ordered, 1000, 950)
		self.purchase(idle, 1000, 0, development=1)
		metrics = LotMetrics(
			[{"name": name, "item": "Vest"} for name in (ordered, started, idle)], sewing_processes=[]
		)
		self.assertEqual(get_tracked_lots(metrics, {started}), {ordered, started})
