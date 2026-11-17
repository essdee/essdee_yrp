# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class SDYRPAction(Document):
	def validate(self):
		if cint(self.lead_time) < 1:
			frappe.throw(_("Lead Time must be at least 1."))


Action = SDYRPAction
