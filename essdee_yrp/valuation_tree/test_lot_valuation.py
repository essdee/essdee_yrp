from unittest import skipUnless
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt
from yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.test_yrp_stock_valuation_adjustment import (
	_stock_context,
	_stock_entry,
	_warehouse,
)
from yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment import (
	create_adjustment,
	process_adjustment,
	register_production_links,
)

from essdee_yrp.valuation_tree import api
from essdee_yrp.valuation_tree.graph import CATEGORIES, ValuationGraph
from essdee_yrp.valuation_tree.ledger import LedgerReader
from essdee_yrp.valuation_tree.lot import LotValuation
from essdee_yrp.valuation_tree.rates import RateBuildUp

REAL_LOTS = ("VALTEST3-2111-01", "VALTEST4-2311-01", "VALTEST5-2311-01")


class TestValuationGraph(FrappeTestCase):
	"""Yarn 1.5 kg @200 + 1.5 kg @250 issued into a 3 kg knitting receipt @238 (13 process)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.item, cls.uom, cls.dimensions = _stock_context()

	def setUp(self):
		super().setUp()
		for target in (
			"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.is_stock_adjustment_enabled",
		):
			patcher = patch(target, return_value=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		commit = patch.object(frappe.db, "commit")
		commit.start()
		self.addCleanup(commit.stop)
		self.addCleanup(frappe.db.rollback)

	def entry(self, purpose, qty, rate, time, **warehouses):
		return _stock_entry(
			self.item, self.uom, self.dimensions, purpose, qty, rate, posting_time=time, **warehouses
		)

	def sle(self, voucher, positive=True):
		return frappe.db.get_value(
			"YRP Stock Ledger Entry",
			{"voucher_no": voucher.name, "qty": [">", 0] if positive else ["<", 0], "is_cancelled": 0},
			["name", "item", "qty", "rate"],
			as_dict=True,
		)

	def build_chain(self):
		store, mill = _warehouse("Tree Store"), _warehouse("Tree Mill")
		first = self.entry("Material Receipt", 1.5, 200, "07:00:00", to_warehouse=store)
		self.entry("Material Receipt", 1.5, 250, "07:01:00", to_warehouse=store)
		issue = self.entry("Material Issue", 3, 0, "07:02:00", from_warehouse=store)
		receipt = self.entry("Material Receipt", 3, 238, "07:03:00", to_warehouse=mill)
		output = self.sle(receipt)
		register_production_links(
			issue.doctype,
			issue.name,
			[
				{
					"consumption_sle": self.sle(issue, False).name,
					"output_receipt_sle": output.name,
					"source_row": issue.items[0].name,
					"input_quantity": 3,
					"allocation_weight": 3,
					"stock_dimensions": frappe.as_json(self.dimensions),
				}
			],
		)
		return first, output

	def apply_pi(self, receipt, difference):
		target = self.sle(receipt)
		adjustment = create_adjustment(
			adjustment_type="Purchase Invoice Rate Difference",
			source_doctype=receipt.doctype,
			source_name=receipt.name,
			effective_date=receipt.posting_date,
			allocations=[
				{
					"target_sle": target.name,
					"item": target.item,
					"quantity": target.qty,
					"old_rate": target.rate,
					"new_rate": flt(target.rate) + difference / flt(target.qty),
					"difference": difference,
					"allocation_weight": target.qty,
					"stock_dimensions": frappe.as_json(self.dimensions),
				}
			],
			idempotency_key=f"valuation-tree-test:{receipt.name}:{difference}",
			enqueue=False,
		)
		process_adjustment(adjustment)

	def graph(self):
		return ValuationGraph(LedgerReader())

	def assert_reconciles(self, node):
		self.assertAlmostEqual(sum(node["categories"].values()), node["value"], places=6)
		self.assertNotIn("unexplained", node["own"])

	def test_production_node_reconciles_to_inputs_plus_process(self):
		_first, output = self.build_chain()
		node = self.graph().node(output.name)
		self.assertAlmostEqual(node["value"], 714)
		self.assertEqual(len(node["children"]), 2)
		self.assertAlmostEqual(node["categories"]["material"], 675, places=6)
		self.assertAlmostEqual(node["categories"]["process"], 39, places=6)
		self.assertTrue(node["info"]["process_cost_derived"])
		self.assert_reconciles(node)

	def test_purchase_invoice_is_own_on_receipt_and_inherited_downstream(self):
		first, output = self.build_chain()
		self.apply_pi(first, 75)
		graph = self.graph()
		node = graph.node(output.name)
		leaf = graph.nodes[self.sle(first).name]
		self.assertAlmostEqual(leaf["own"]["pi"], 75, places=6)
		self.assertAlmostEqual(node["info"]["inherited_pi"], 75, places=6)
		self.assertNotIn("pi", node["own"])
		self.assertAlmostEqual(node["value"], 789, places=6)
		self.assertAlmostEqual(node["categories"]["pi"], 75, places=6)
		self.assertAlmostEqual(node["categories"]["material"], 675, places=6)
		self.assert_reconciles(node)

	def test_rate_build_up_of_a_ledger_chain_reconciles(self):
		_first, output = self.build_chain()
		graph = self.graph()
		graph.node(output.name)
		result = RateBuildUp(graph, graph.reader, self.item, [output.name]).build()
		root = result["sections"][-1]["rows"][0]
		self.assertEqual([line["rate"] for line in root["inputs"]], [200, 250])
		self.assertAlmostEqual(root["rate_in"], 225, places=6)
		self.assertAlmostEqual(root["process"], 13, places=6)
		self.assertAlmostEqual(root["rate_out"], 238, places=6)
		self.assertAlmostEqual(result["root_total"], 714, places=6)


class TestRealLotValuation(FrappeTestCase):
	"""Reconciliation invariant on locally built valuation lots: tree value equals ledger value to the paisa."""

	def check_lot(self, lot):
		result = LotValuation(lot).build()
		summary = result["summary"]
		roots = [sle for group in result["roots"] for sle in group["sles"]]
		ledger = sum(
			flt(row.qty) * flt(row.rate) + flt(row.valuation_adjustment_value)
			for row in frappe.get_all(
				"YRP Stock Ledger Entry",
				filters={"name": ["in", roots]},
				fields=["qty", "rate", "valuation_adjustment_value"],
			)
		)
		self.assertAlmostEqual(summary["ledger_value"], ledger, places=6)
		self.assertAlmostEqual(sum(summary["categories"][key] for key in CATEGORIES), ledger, places=4)
		self.assertAlmostEqual(summary["checks"]["unexplained_value"], 0, places=6)
		self.assertAlmostEqual(sum(row["value"] for row in summary["waterfall"]), ledger, places=4)
		self.check_rates(result["rate_sections"], ledger)
		return result

	def check_rates(self, rates, ledger):
		self.assertAlmostEqual(rates["root_total"], ledger, places=4)
		for section in rates["sections"]:
			for row in section["rows"]:
				adds = row["process"] + row["accessories"] + row["pi"] + row["wo_close"] + row["unattributed"]
				self.assertAlmostEqual(row["rate_in"] + adds, row["rate_out"], places=6)
				inputs = row["purchase_rate"] + sum(line["amount"] for line in row["inputs"])
				self.assertAlmostEqual(inputs, row["rate_in"], places=6)

	@skipUnless(frappe.db.exists("SD YRP Lot", REAL_LOTS[0]), "local valuation lot missing")
	def test_valtest3_reconciles(self):
		result = self.check_lot(REAL_LOTS[0])
		self.assertTrue(result["root_is_packing"])
		boxes = result["rate_sections"]["sections"][-1]["rows"]
		self.assertEqual(
			[(row["item"], row["qty"], round(row["rate_out"], 2)) for row in boxes],
			[("L", 6, 496.70), ("M", 5, 511.03)],
		)
		self.assertEqual(boxes[0]["inputs"][0]["item"], "Loose Piece-L")

	@skipUnless(frappe.db.exists("SD YRP Lot", REAL_LOTS[1]), "local valuation lot missing")
	def test_valtest4_reconciles(self):
		self.check_lot(REAL_LOTS[1])

	@skipUnless(frappe.db.exists("SD YRP Lot", REAL_LOTS[2]), "local valuation lot missing")
	def test_valtest5_cutting_spreads_each_colour_only_over_its_panels(self):
		result = self.check_lot(REAL_LOTS[2])
		self.assertEqual(result["root_stage"], "Stitching")
		cutting = next(
			section for section in result["rate_sections"]["sections"] if section["title"] == "Cutting"
		)
		for row in cutting["rows"]:
			if row["uom"] == "Pieces":
				colour = row["item"].split("-")[1]
				self.assertTrue(all(line["item"].endswith(f"-{colour}") for line in row["inputs"]), row)

	@skipUnless(frappe.db.exists("SD YRP Lot", "C0426-33"), "local legacy lot missing")
	def test_legacy_lot_renders_lineage_missing_leaves(self):
		result = self.check_lot("C0426-33")
		self.assertGreater(result["summary"]["checks"].get("missing", 0), 0)


class TestLotValuationApi(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.lot = frappe.db.get_value("SD YRP Lot", {}, "name")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)

	def test_non_system_manager_is_refused(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"valuation-tree-{frappe.generate_hash(length=6)}@example.com",
				"first_name": "Valuation",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			api.get_lot_valuation(self.lot)
		with self.assertRaises(frappe.PermissionError):
			api.enqueue_lot_valuation(self.lot)

	def test_reading_never_computes(self):
		frappe.db.delete(api.CACHE_DOCTYPE, {"lot": self.lot})
		with (
			patch.object(LotValuation, "build", side_effect=AssertionError("computed")),
			patch("frappe.enqueue") as enqueue,
		):
			state = api.get_lot_valuation(self.lot)
		self.assertEqual(state["status"], "Not Calculated")
		enqueue.assert_not_called()

	def test_second_request_reuses_the_queued_job(self):
		frappe.db.delete(api.CACHE_DOCTYPE, {"lot": self.lot})
		with patch("frappe.enqueue") as enqueue, patch.object(api, "is_job_enqueued", return_value=True):
			api.enqueue_lot_valuation(self.lot)
			state = api.enqueue_lot_valuation(self.lot)
		self.assertEqual(enqueue.call_count, 1)
		self.assertEqual(enqueue.call_args.kwargs["job_id"], api.job_id_for(self.lot))
		self.assertTrue(enqueue.call_args.kwargs["deduplicate"])
		self.assertEqual(state["status"], "Queued")

	def test_job_stores_result_and_keeps_it_for_reopen(self):
		frappe.db.delete(api.CACHE_DOCTYPE, {"lot": self.lot})
		with patch("frappe.enqueue"):
			api.enqueue_lot_valuation(self.lot)
		with (
			patch.object(LotValuation, "build", return_value={"summary": {"ledger_value": 1}}),
			patch.object(frappe.db, "commit"),
		):
			api.run_lot_valuation(self.lot)
		state = api.get_lot_valuation(self.lot)
		self.assertEqual(state["status"], "Completed")
		self.assertEqual(state["result"], {"summary": {"ledger_value": 1}})
		self.assertTrue(state["computed_at"])
