"""Approved YRP Process Cost a Work Order needs to submit, at the rate in data.PROCESS_RATES."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days
from yrp import attribute_links
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import get_variant_attributes

from essdee_yrp.essdee_yrp.old_dc_grn_migration.data import PROCESS_COST_TAX_SLAB, PROCESS_RATES

COLOUR_ATTRIBUTE = "Colour"


class ProcessRateMissing(Exception):
	"""A Process Cost is needed but data.PROCESS_RATES has no rate for it (or for one of its colours) yet."""

	def __init__(self, needed):
		super().__init__(f"process rate needed in data.PROCESS_RATES for: {'; '.join(needed)}")
		self.needed = needed


def get_to_date(work_order):
	"""The day before a later approved Process Cost of the same process, item, supplier and lot, if any."""
	next_from = frappe.db.get_value(
		"YRP Process Cost",
		{
			"process_name": work_order.process_name,
			"item": work_order.item,
			"supplier": work_order.supplier,
			"lot": work_order.lot,
			"docstatus": 1,
			"from_date": [">", work_order.wo_date],
		},
		"from_date",
		order_by="from_date asc",
	)
	return add_days(next_from, -1) if next_from else None


def get_rate_key(process, supplier, item):
	return f"{process}|{supplier}|{item}"


PLACEHOLDER_RATE = 1.0


def get_receivable_colours(work_order):
	return sorted(
		{get_variant_attributes(row.item_variant).get(COLOUR_ATTRIBUTE) for row in work_order.receivables}
	)


def get_prices(key, colours):
	"""{colour: rate} for a colour-wise rate, else {None: rate}; a rate not filled yet is None."""
	rate = PROCESS_RATES.get(key)
	if isinstance(rate, dict):
		return {colour: rate.get(colour) for colour in colours}
	return {None: rate}


def get_missing_process_rates(key, prices):
	return [
		key if colour is None else f"{key} [{colour}]" for colour, price in prices.items() if price is None
	]


def ensure_process_cost(work_order, placeholder_rates=False):
	"""Return (process cost name, missing rate keys) for a draft WO; (None, []) when an approved one already applies.

	A {colour: rate} value builds a Colour-wise Process Cost with one price per receivable colour. The app requires
	a price above 0, so a missing rate fails; placeholder_rates (dry run only) uses 1 and returns it as missing.
	"""
	if work_order.get_receivable_process_cost():
		return None, []
	key = get_rate_key(work_order.process_name, work_order.supplier, work_order.item)
	prices = get_prices(key, get_receivable_colours(work_order))
	missing = get_missing_process_rates(key, prices)
	if missing and not placeholder_rates:
		raise ProcessRateMissing(missing)
	doc = frappe.new_doc("YRP Process Cost")
	doc.update(
		{
			"process_name": work_order.process_name,
			"supplier": work_order.supplier,
			"item": work_order.item,
			"lot": work_order.lot,
			"uom": frappe.db.get_value("Item", work_order.item, "stock_uom"),
			"from_date": work_order.wo_date,
			"tax_slab": PROCESS_COST_TAX_SLAB,
		}
	)
	if None not in prices:
		doc.update({"depends_on_attribute": 1, "attribute": COLOUR_ATTRIBUTE})
	doc.to_date = get_to_date(work_order)
	for colour, price in prices.items():
		doc.append(
			"process_cost_values",
			{
				"price": PLACEHOLDER_RATE if price is None else price,
				"attribute_value": attribute_links.link(colour, COLOUR_ATTRIBUTE) if colour else None,
			},
		)
	doc.insert()
	apply_workflow(doc, "Submit")
	doc = apply_workflow(doc, "Approve")
	if doc.docstatus != 1 or doc.workflow_state != "Approved":
		frappe.throw(f"Process Cost {doc.name} is {doc.workflow_state} after approval")
	return doc.name, missing
