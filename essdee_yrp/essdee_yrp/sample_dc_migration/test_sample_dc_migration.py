import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.old_dc_grn_migration.documents import get_tag

from .data import DOCUMENTS, LOT, PROCESS_RATES
from .documents import DocumentMigrator, get_variant


def get_document(number):
	return next(document for document in DOCUMENTS if document["number"] == number)


class TestSampleData(IntegrationTestCase):
	def test_only_the_approved_dcs(self):
		self.assertEqual(
			[document["number"] for document in DOCUMENTS],
			[
				"PG-2526-1333",
				"DC-2526-10412",
				"DC-2526-10637",
				"DC-2526-11073",
				"DC-2526-11231",
				"DC-2526-11238",
				"DC-2526-11268",
				"DC-2526-11376",
			],
		)

	def test_user_process_rates(self):
		self.assertEqual(PROCESS_RATES, {"Knitting": 13, "Dyeing": 50, "Heat Setting": 10, "Washing": 8})

	def test_every_deliverable_has_a_rate_and_output_matches_input(self):
		for document in DOCUMENTS:
			self.assertTrue(all(line["rate"] for line in document["deliverables"]), document["number"])
			delivered = sum(line["qty"] for line in document["deliverables"])
			received = sum(line["qty"] for line in document["receivables"])
			self.assertAlmostEqual(delivered, received, places=2, msg=document["number"])

	def test_only_the_knitting_dc_has_grns(self):
		knitting = get_document("PG-2526-1333")
		self.assertEqual([grn["number"] for grn in knitting["grns"]], ["GRN-2526-9784", "GRN-2526-9844"])
		self.assertAlmostEqual(sum(line["qty"] for grn in knitting["grns"] for line in grn["lines"]), 34.9)
		self.assertEqual([d["number"] for d in DOCUMENTS if d.get("grns")], ["PG-2526-1333"])

	def test_dyeing_changes_only_the_colour(self):
		for document in DOCUMENTS:
			if document["process"] != "Dyeing":
				continue
			source, output = document["deliverables"][0], document["receivables"][0]
			self.assertEqual(source["item"], output["item"])
			self.assertEqual(source["attributes"].get("Dia"), output["attributes"].get("Dia"))


class TestSampleMigration(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.get_value("SD YRP Lot", LOT, "is_folding_lot"):
			self.skipTest(f"Folding lot {LOT} is missing on this site")
		frappe.set_user("Administrator")
		frappe.flags.mute_emails = True

	def get_migrated(self, number):
		return frappe.db.get_value("YRP Work Order", {"comments": get_tag(number), "docstatus": 1}, "name")

	def test_knitting_dc_creates_its_documents_and_is_idempotent(self):
		number = "PG-2526-1333"
		if self.get_migrated(number):
			self.skipTest(f"{number} is already migrated on this site")
		first = DocumentMigrator(get_document(number))
		first.run()
		self.assertEqual(
			{doctype: len(names) for doctype, names in first.created.items()},
			{
				"YRP Stock Entry": 1,
				"YRP Process Cost": 1,
				"YRP Work Order": 1,
				"YRP Delivery Challan": 1,
				"YRP Goods Received Note": 2,
			},
		)
		work_order = frappe.get_doc("YRP Work Order", first.created["YRP Work Order"][0])
		self.assertEqual((work_order.lot, str(work_order.wo_date)), (LOT, "2026-09-15"))
		self.assertFalse(work_order.production_detail)
		received = {row.item_variant: row.qty - row.pending_quantity for row in work_order.receivables}
		greige_36 = get_variant(get_document(number)["grns"][0]["lines"][0])
		self.assertAlmostEqual(received[greige_36], 13.5)
		dc = frappe.get_doc("YRP Delivery Challan", first.created["YRP Delivery Challan"][0])
		self.assertEqual((dc.supplier_document_no, str(dc.posting_date)), (number, "2026-09-15"))

		second = DocumentMigrator(get_document(number))
		second.run()
		self.assertEqual(second.created, {})
		self.assertEqual(sum(len(names) for names in second.skipped.values()), 5)
