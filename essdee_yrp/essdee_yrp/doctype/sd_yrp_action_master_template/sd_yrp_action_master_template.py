# Copyright (c) 2024, Essdee and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from yrp.utils import update_if_string_instance

from essdee_yrp.time_and_action.create import get_master_lead_time, validate_master_steps


class SDYRPActionMasterTemplate(Document):
	def autoname(self):
		self.naming_series = "Master Template-"

	def onload(self):
		d = {}
		previous_action = []
		for row in self.details:
			previous_action.append({"option": row.action, "id": row.action})
			d[row.action] = {
				"action": row.action,
				"lead_time": row.lead_time,
				"department": row.department,
				"dependent_action": [],
			}

		for row in self.action_master_dependent_details:
			if row.action in d:
				d[row.action]["dependent_action"].append(row.dependent_action)

		list_data = [d[key] for key in d]
		self.set_onload(
			"action_data",
			{
				"data": list_data,
				"previous": previous_action,
			},
		)

	def before_validate(self):
		self.quantity = str(self.min_qty) + " - " + str(self.max_qty)
		if self.get("action_details"):
			action_details = update_if_string_instance(self.action_details)
			details = []
			dependent_details = []
			for row in action_details:
				details.append(
					{
						"action": row["action"],
						"lead_time": row["lead_time"],
						"department": row["department"],
						"target": 0,
					}
				)
				if len(row["dependent_action"]) > 0:
					for act in row["dependent_action"]:
						dependent_details.append(
							{
								"action": row["action"],
								"dependent_action": act,
							}
						)

			self.set("details", details)
			self.set("action_master_dependent_details", dependent_details)

	def validate(self):
		validate_master_steps(self)

	def before_save(self):
		self.lead_time = get_master_lead_time(self)


@frappe.whitelist()
def get_work_station(action):
	rows = frappe.get_list(
		"YRP Work Station",
		filters={"action": action, "default": 1},
		pluck="name",
		limit=1,
	)
	return rows[0] if rows else None


ActionMasterTemplate = SDYRPActionMasterTemplate
