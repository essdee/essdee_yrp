"""Item controller mixin for Essdee's Maintain Stock rules."""


class EssdeeItemMixin:
	"""Never block switching Maintain Stock on; switching it off keeps every lock."""

	@property
	def is_enabling_maintain_stock(self):
		before = self.get_doc_before_save()
		return bool(before and not before.is_stock_item and self.is_stock_item)

	def _get_linked_submitted_documents(self, changed_fields):
		if self.is_enabling_maintain_stock:
			changed_fields = [field for field in changed_fields if field != "is_stock_item"]
			if not changed_fields:
				return None
		return super()._get_linked_submitted_documents(changed_fields)

	def _validate_yrp_stock_mutation(self):
		if not self.is_enabling_maintain_stock:
			return super()._validate_yrp_stock_mutation()
		before = self.get_doc_before_save()
		before.is_stock_item = 1
		try:
			super()._validate_yrp_stock_mutation()
		finally:
			before.is_stock_item = 0
