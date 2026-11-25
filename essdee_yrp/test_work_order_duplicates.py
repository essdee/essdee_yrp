import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.work_order_duplicates import get_duplicate_work_orders

MATCH = {
	"lot": "_DUP-TEST-LOT",
	"item": "_DUP-TEST-ITEM",
	"supplier": "_DUP-TEST-SUPPLIER",
	"process_name": "_DUP-TEST-PROCESS",
}


def _insert_work_order(name: str, docstatus: int = 1, **overrides) -> str:
	doc = frappe.new_doc("YRP Work Order")
	doc.update({**MATCH, **overrides})
	doc.update(
		{
			"name": name,
			"docstatus": docstatus,
			"wo_date": "2026-11-20",
			"status": "Submitted",
			"planned_quantity": 100,
			"total_no_of_pieces_delivered": 40,
			"total_no_of_pieces_received": 10,
		}
	)
	doc.db_insert()
	return name


class TestWorkOrderDuplicates(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _duplicate_names(self, work_order: str) -> list[str]:
		return [row["name"] for row in get_duplicate_work_orders(work_order)]

	def test_matches_submitted_work_order_with_same_lot_item_supplier_process(self):
		existing = _insert_work_order("_DUP-TEST-WO-1")
		current = _insert_work_order("_DUP-TEST-WO-2")

		rows = get_duplicate_work_orders(current)

		self.assertEqual([row["name"] for row in rows], [existing])
		row = rows[0]
		self.assertEqual(str(row["wo_date"]), "2026-11-20")
		self.assertEqual(row["status"], "Submitted")
		self.assertEqual(row["planned_quantity"], 100)
		self.assertEqual(row["total_no_of_pieces_delivered"], 40)
		self.assertEqual(row["total_no_of_pieces_received"], 10)
		self.assertEqual(row["created_by"], frappe.utils.get_fullname(frappe.session.user))

	def test_any_differing_field_is_not_matched(self):
		current = _insert_work_order("_DUP-TEST-WO-CURRENT")
		for fieldname in MATCH:
			_insert_work_order(f"_DUP-TEST-WO-{fieldname}", **{fieldname: f"_OTHER-{fieldname}"})

		self.assertEqual(self._duplicate_names(current), [])

	def test_excludes_itself_drafts_and_cancelled(self):
		current = _insert_work_order("_DUP-TEST-WO-SELF")
		_insert_work_order("_DUP-TEST-WO-DRAFT", docstatus=0)
		_insert_work_order("_DUP-TEST-WO-CANCELLED", docstatus=2)

		self.assertEqual(self._duplicate_names(current), [])

	def test_work_order_without_lot_has_no_duplicates(self):
		_insert_work_order("_DUP-TEST-WO-NOLOT-1", lot=None)
		current = _insert_work_order("_DUP-TEST-WO-NOLOT-2", lot=None)

		self.assertEqual(self._duplicate_names(current), [])
