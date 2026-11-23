from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.planning import dashboard_workspace
from essdee_yrp.planning.dashboard import process_status
from essdee_yrp.planning.dashboard.process_status import LotProcessStatus, get_cell


def order(name, process, status="Submitted", docstatus=1, open_status="Open", lot="L-1", item="SHIRT"):
	return {
		"name": name,
		"lot": lot,
		"item": item,
		"process_name": process,
		"status": status,
		"docstatus": docstatus,
		"open_status": open_status,
	}


class TestProcessCell(TestCase):
	def status(self, *orders):
		return get_cell(list(orders), {})["status"]

	def test_no_orders_is_no_work_order(self):
		self.assertEqual(self.status(), "No Work Order")

	def test_only_drafts_is_draft(self):
		self.assertEqual(self.status(order("WO-1", "Cutting", "Draft", 0)), "Draft")

	def test_submitted_without_movement_is_not_started(self):
		self.assertEqual(
			self.status(order("WO-1", "Cutting"), order("WO-2", "Cutting", "Draft", 0)), "Not Started"
		)

	def test_any_movement_is_in_progress(self):
		self.assertEqual(
			self.status(
				order("WO-1", "Cutting", "Fully Received"), order("WO-2", "Cutting", "Partially Delivered")
			),
			"In Progress",
		)

	def test_all_received_billed_or_closed_is_completed(self):
		self.assertEqual(
			self.status(
				order("WO-1", "Cutting", "Fully Received"),
				order("WO-2", "Cutting", "Fully Billed"),
				order("WO-3", "Cutting", "Partially Received", open_status="Close"),
			),
			"Completed",
		)

	def test_a_draft_beside_completed_orders_keeps_the_process_in_progress(self):
		self.assertEqual(
			self.status(order("WO-1", "Cutting", "Fully Received"), order("WO-2", "Cutting", "Draft", 0)),
			"In Progress",
		)

	def test_cell_carries_the_tracking_step_rows_of_its_submitted_processes(self):
		step = {"name": "Ironing and Packing", "kind": "packing", "work_orders": [{"name": "WO-1"}]}
		cell = get_cell(
			[
				order("WO-1", "Ironing and Packing", "Partially Received"),
				order("WO-2", "Packing", "Draft", 0),
			],
			{"Ironing and Packing": step, "Stitching": {"name": "Stitching"}},
		)
		self.assertEqual(cell["steps"], [step])
		self.assertEqual((cell["work_orders"], cell["drafts"]), (2, 1))


class TestLotProcessStatus(TestCase):
	def make(self):
		status = LotProcessStatus(
			[
				{"name": "L-1", "item": "SHIRT", "production_detail": "IPD-1"},
				{"name": "L-2", "item": "SHIRT", "production_detail": "IPD-2"},
				{"name": "L-3", "item": "SHIRT", "production_detail": None},
			]
		)
		status.item_steps = {
			"IPD-1": [
				("Cutting", 0, 0),
				("Printing", 1, 0),
				("Stitching", 2, 0),
				("Ironing", 3, 0),
				("Packing", 4, 0),
			],
			"IPD-2": [("Cutting", 0, 0), ("Stitching", 2, 0), ("Packing", 4, 0)],
		}
		status.fabric_steps = {"L-1": [("Dyeing", 20), ("Knitting", 10)]}
		status.groups = {"Ironing and Packing": ["Ironing", "Packing"]}
		status.steps = {"L-1": {"Ironing and Packing": {"name": "Ironing and Packing"}}}
		status.orders = [
			order("WO-1", "Knitting", "Fully Received", item="CLOTH"),
			order("WO-2", "Cutting", "Fully Received"),
			order("WO-3", "Ironing and Packing", "Partially Received"),
			order("WO-4", "Printing", "Fully Received", lot="L-2"),
		]
		return status

	def test_columns_put_fabric_processes_first_then_garment_stages(self):
		self.assertEqual(
			[column["name"] for column in self.make().columns],
			["Knitting", "Dyeing", "Cutting", "Printing", "Stitching", "Ironing", "Packing"],
		)
		self.assertEqual(self.make().columns[0]["kind"], "fabric")

	def test_cells_cover_only_the_lot_ipd_processes(self):
		cells = self.make().get_cells("L-1")
		self.assertEqual(cells["Knitting"]["status"], "Completed")
		self.assertEqual(cells["Dyeing"]["status"], "No Work Order")
		self.assertEqual(cells["Stitching"]["status"], "No Work Order")
		self.assertEqual(cells["Ironing"]["status"], "In Progress")
		self.assertEqual(cells["Packing"]["steps"], [{"name": "Ironing and Packing"}])

	def test_process_outside_the_ipd_has_no_cell(self):
		cells = self.make().get_cells("L-2")
		self.assertNotIn("Printing", cells)
		self.assertNotIn("Knitting", cells)
		self.assertEqual(self.make().get_cells("L-3"), {})


class TestProcessStatusEndpoint(TestCase):
	def test_requires_dashboard_read(self):
		with patch.object(dashboard_workspace, "can_read", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				dashboard_workspace.get_process_status()

	def test_reads_open_ppos_and_open_lots_only(self):
		seen = {}

		def fake_get_list(doctype, filters=None, **kwargs):
			seen.setdefault(doctype, filters)
			return ["PPO-1"] if kwargs.get("pluck") else []

		with patch("frappe.get_list", side_effect=fake_get_list):
			self.assertEqual(process_status.get_process_status_data(), {"processes": [], "lots": {}})
		self.assertEqual(seen["YRP Production Order"], {"docstatus": 1, "status": "Open"})
		self.assertEqual(seen["SD YRP Lot"]["status"], "Open")
