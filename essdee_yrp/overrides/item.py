"""Item controller mixin for Essdee's Maintain Stock rules."""

import frappe


class EssdeeItemMixin:
	"""Never block switching Maintain Stock on; only real stock blocks switching it off."""

	@property
	def is_enabling_maintain_stock(self):
		before = self.get_doc_before_save()
		return bool(before and not before.is_stock_item and self.is_stock_item)

	def _get_linked_submitted_documents(self, changed_fields):
		if "is_stock_item" in changed_fields and not self.is_stock_item:
			if stock_ledger_entry := self.get_stock_ledger_entry():
				return stock_ledger_entry
		other_fields = [field for field in changed_fields if field != "is_stock_item"]
		if not other_fields:
			return None
		return super()._get_linked_submitted_documents(other_fields)

	def get_stock_ledger_entry(self):
		return frappe.db.get_value(
			"Stock Ledger Entry",
			{"item_code": self.name, "is_cancelled": 0},
			["voucher_no as docname", "voucher_type as doctype"],
			as_dict=True,
		)

	def _validate_yrp_stock_mutation(self):
		if not self.is_enabling_maintain_stock:
			return super()._validate_yrp_stock_mutation()
		before = self.get_doc_before_save()
		before.is_stock_item = 1
		try:
			super()._validate_yrp_stock_mutation()
		finally:
			before.is_stock_item = 0
