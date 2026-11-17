"""Yarn for the Knitting DCs: reuse the lot's received yarn, Material Receipt only the shortfall at the configured rate."""

from collections import defaultdict

import frappe
from frappe.utils import flt
from yrp.stock.save_stock_items import group_items_for_ui

from essdee_yrp.essdee_yrp.old_dc_grn_migration.data import YARN_RATES
from essdee_yrp.essdee_yrp.old_dc_grn_migration.documents import FABRIC_STORE, get_tag, set_posting
from essdee_yrp.essdee_yrp.old_dc_grn_migration.plan import get_missing_rates, get_yarn_shortfall

RECEIPT_TIME = "22:59:59"


class YarnRateMissing(Exception):
	"""A Material Receipt needs a yarn rate that data.YARN_RATES does not have yet."""


def get_needed_yarn(work_orders):
	needed = defaultdict(float)
	for name in work_orders:
		for row in frappe.get_doc("YRP Work Order", name).deliverables:
			needed[row.item_variant] += flt(row.pending_quantity or row.qty)
	return dict(needed)


def get_stock_ready_date(lot, items):
	"""ISO date of the last receipt of these yarn items for the lot in the fabric store, or None."""
	date = frappe.db.sql(
		"""select max(posting_date) from `tabYRP Stock Ledger Entry`
		where is_cancelled = 0 and qty > 0 and lot = %s and warehouse = %s and item in %s""",
		(lot, FABRIC_STORE, list(items) or [""]),
	)[0][0]
	return str(date) if date else None


def get_lot_stock(lot, items):
	rows = frappe.db.sql(
		"""select item, sum(qty) from `tabYRP Stock Ledger Entry`
        where is_cancelled = 0 and lot = %s and warehouse = %s and item in %s group by item""",
		(lot, FABRIC_STORE, list(items) or [""]),
	)
	return {item: flt(qty) for item, qty in rows}


def make_material_receipt(lot, shortfall, date, number, allow_zero_rate):
	"""Receive the yarn shortfall into the fabric store; returns (doc, rates used)."""
	rates = YARN_RATES.get(lot, {})
	missing = get_missing_rates(shortfall, rates)
	if missing and not allow_zero_rate:
		raise YarnRateMissing(f"yarn rate needed in data.YARN_RATES[{lot!r}] for: {', '.join(missing)}")
	received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	items = [
		{
			"item": item,
			"qty": qty,
			"uom": frappe.db.get_value("Item", item, "stock_uom"),
			"rate": flt(rates.get(item)),
			"allow_zero_valuation_rate": int(not rates.get(item)),
			"lot": lot,
			"received_type": received_type,
		}
		for item, qty in sorted(shortfall.items())
	]
	doc = frappe.new_doc("YRP Stock Entry")
	doc.update(
		{
			"naming_series": "STE-.YYYY.-",
			"purpose": "Material Receipt",
			"to_warehouse": FABRIC_STORE,
			"comments": get_tag(number),
		}
	)
	doc.item_details = frappe.as_json(group_items_for_ui(items, "YRP Stock Entry"))
	set_posting(doc, date, RECEIPT_TIME)
	doc.insert()
	doc.submit()
	return doc


def get_excess_yarn(work_order, cloth_kg):
	"""{yarn item: qty} a delivered Knitting WO lacks for cloth_kg of cloth, split like its deliverables."""
	doc = frappe.get_doc("YRP Work Order", work_order)
	delivered = {}
	for row in doc.deliverables:
		delivered[row.item_variant] = (
			delivered.get(row.item_variant, 0) + flt(row.qty) - flt(row.pending_quantity)
		)
	total = sum(delivered.values())
	missing = round(cloth_kg - total, 3)
	if missing <= 0 or not total:
		return {}
	return {item: round(missing * qty / total, 3) for item, qty in delivered.items() if qty}


def get_shortfall(lot, work_orders, extra_needs=()):
	"""{yarn item: qty} the new Knitting DCs (and extra_needs) deliver beyond the lot's yarn in the fabric store."""
	needed = get_needed_yarn(work_orders)
	for extra in extra_needs:
		for item, qty in extra.items():
			needed[item] = needed.get(item, 0) + qty
	return get_yarn_shortfall(needed, get_lot_stock(lot, needed))


def ensure_receipt(lot, shortfall, date, allow_zero_rate):
	"""Return the Material Receipt for the shortfall, creating it unless an earlier run already did.

	It is posted no earlier than the lot's last yrp receipt or reconciliation of those yarns (a reconciliation
	would reset an earlier receipt), late in the day before the migrated DCs.
	"""
	date = max(filter(None, [date, get_stock_ready_date(lot, shortfall)]))
	number = f"yarn shortfall for {lot}"
	existing = frappe.db.get_value("YRP Stock Entry", {"comments": get_tag(number), "docstatus": 1}, "name")
	return existing or make_material_receipt(lot, shortfall, date, number, allow_zero_rate).name
