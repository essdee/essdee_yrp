# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

DAY_FIELDS = ("update_last_n_dates", "update_future_n_dates", "revising_days_limit")


class SDYRPTandASettings(Document):
	def validate(self):
		for fieldname in DAY_FIELDS:
			if cint(self.get(fieldname)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(fieldname))))


TandASettings = SDYRPTandASettings
