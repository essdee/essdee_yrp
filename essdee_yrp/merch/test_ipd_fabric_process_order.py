import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd_test_support import SAMPLES, make_user, rolled_back, unapprove

SENIOR = "_test_ipd_senior@example.com"
CLOTH = SAMPLES["cloth"]


def wire(value):
	return json.loads(json.dumps(value, default=str))


def modified(name):
	return str(frappe.db.get_value(DOCTYPE, name, "modified"))


def resequence(processes, mappings):
	"""Mirror of the /web clothGrids resequenceProcesses: steps become 10, 20, ... and mappings follow."""
	renumbered = {}
	for index, row in enumerate(processes):
		renumbered.setdefault(row["sequence"], (index + 1) * 10)
		row["sequence"] = (index + 1) * 10
	for row in mappings:
		row["sequence"] = renumbered.get(row["sequence"], row["sequence"])
	mappings.sort(key=lambda row: (row["sequence"], row["mapping_index"]))
	return {"fabric_processes": processes, "fabric_value_mappings": mappings}


def stored(name):
	"""Process order plus each mapping keyed by the process it belongs to."""
	doc = frappe.get_doc(DOCTYPE, name)
	process_of = {row.sequence: row.fabric_process for row in doc.fabric_processes}
	return (
		[(row.sequence, row.fabric_process) for row in doc.fabric_processes],
		sorted(
			{(process_of.get(row.sequence), row.attribute, row.role) for row in doc.fabric_value_mappings}
		),
	)


class TestIpdFabricProcessOrder(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(SENIOR, ["Senior Merch", "Merchandiser"])

	def tearDown(self):
		frappe.set_user("Administrator")

	def editor_rows(self):
		values = workspace.get_ipd_editor(CLOTH)["values"]
		processes = sorted(wire(values["fabric_processes"]), key=lambda row: row["sequence"])
		return processes, wire(values["fabric_value_mappings"])

	def test_reorder_add_and_remove_fabric_processes(self):
		frappe.set_user(SENIOR)
		with rolled_back("fabric_process_order"):
			unapprove(CLOTH)
			processes, mappings = self.editor_rows()
			before = stored(CLOTH)[1]
			last = processes.pop()
			processes.insert(len(processes) - 1, last)
			workspace.save_ipd(resequence(processes, mappings), CLOTH, modified(CLOTH))
			order, saved_mappings = stored(CLOTH)
			self.assertEqual([sequence for sequence, _ in order], [10, 20, 30])
			self.assertEqual(order[1][1], last["fabric_process"])
			self.assertEqual(saved_mappings, before)

			processes, mappings = self.editor_rows()
			used = [row["fabric_process"] for row in processes]
			spare = frappe.get_all(
				"YRP Process",
				filters={"is_cloth_process": 1, "name": ["not in", used]},
				pluck="name",
				limit=1,
			)[0]
			item = processes[-1]["output_item"]
			processes.append(
				{
					"sequence": 40,
					"fabric_process": spare,
					"input_item": item,
					"output_item": item,
					"quantity_ratio": 1,
				}
			)
			workspace.save_ipd({"fabric_processes": processes}, CLOTH, modified(CLOTH))
			self.assertEqual([sequence for sequence, _ in stored(CLOTH)[0]], [10, 20, 30, 40])

			processes, mappings = self.editor_rows()
			removed = processes.pop(1)
			mappings = [row for row in mappings if row["sequence"] != removed["sequence"]]
			workspace.save_ipd(resequence(processes, mappings), CLOTH, modified(CLOTH))
			order, saved_mappings = stored(CLOTH)
			self.assertEqual([sequence for sequence, _ in order], [10, 20, 30])
			self.assertNotIn(removed["fabric_process"], [process for _, process in order[:2]])
			self.assertNotIn(None, {process for process, _, _ in saved_mappings})

	def test_approved_cloth_ipd_refuses_fabric_process_changes(self):
		frappe.set_user(SENIOR)
		with rolled_back("fabric_process_order_approved"):
			frappe.db.set_value(DOCTYPE, CLOTH, "approval_status", "Approved", update_modified=False)
			processes, mappings = self.editor_rows()
			processes.reverse()
			with self.assertRaisesRegex(frappe.ValidationError, "Approved IPDs are read only"):
				workspace.save_ipd(resequence(processes, mappings), CLOTH, modified(CLOTH))
