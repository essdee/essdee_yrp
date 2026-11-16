# Copyright (c) 2024, Essdee and contributors
# For license information, please see license.txt
from frappe.model.document import Document

from essdee_yrp.time_and_action.create import set_against_details, set_rows_from_master, validate_can_create
from essdee_yrp.time_and_action.derived import apply_schedule


class SDYRPTimeandAction(Document):
	"""One T&A per Lot or Production Order; rows are a snapshot of one Action Master."""

	def before_validate(self):
		if self.is_new():
			set_against_details(self)
			if not self.details:
				set_rows_from_master(self)

	def validate(self):
		if self.is_new():
			validate_can_create(self.against, self.against_id)
		apply_schedule(self)


TimeandAction = SDYRPTimeandAction
