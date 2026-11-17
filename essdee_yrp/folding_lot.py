"""Folding Lot rules: role-gated Lots whose Work Orders carry manual rows without an IPD."""

import frappe
from frappe import _
from frappe.utils import flt
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

FOLDING_LOT_ROLE = "Folding Lot Manager"
QTY_TOLERANCE = 1e-6


def get_folding_lot_role() -> str | None:
	return frappe.db.get_single_value("SD YRP MRP Settings", "folding_lot_role")


def has_folding_lot_role(user: str | None = None) -> bool:
	role = get_folding_lot_role()
	return bool(role and role in frappe.get_roles(user or frappe.session.user))


def is_folding_lot(lot: str | None) -> bool:
	return bool(lot and frappe.db.get_value("SD YRP Lot", lot, "is_folding_lot"))


def check_folding_lot_role(message: str) -> None:
	if not has_folding_lot_role():
		role = get_folding_lot_role() or _("(not configured in MRP Settings)")
		frappe.throw(_("{0} Required role: {1}.").format(message, role), frappe.PermissionError)


def validate_lot(doc) -> None:
	"""Only the configured role may set or clear the Folding Lot flag."""
	changed = bool(doc.get("is_folding_lot")) if doc.is_new() else doc.has_value_changed("is_folding_lot")
	if changed:
		check_folding_lot_role(_("You are not allowed to change Folding Lot."))


def validate_work_order(doc) -> None:
	"""Folding Work Orders keep the user's manual rows and never link an IPD."""
	if not is_folding_lot(doc.get("lot")):
		return
	doc.production_detail = None
	if not doc.get("item"):
		doc.item = get_work_order_item(doc)


def validate_work_order_submit(doc) -> None:
	if is_folding_lot(doc.get("lot")):
		check_folding_lot_role(
			_("Only Folding Lot users can submit Work Orders for Folding Lot {0}.").format(doc.lot)
		)


def get_work_order_item(doc) -> str | None:
	"""The parent Item of the first receivable (or deliverable) row."""
	for row in (doc.get("receivables") or []) + (doc.get("deliverables") or []):
		if row.get("item_variant"):
			return get_parent_item(row.item_variant) or row.item_variant
	return None


def calculate_folding_consumption_plan(grn) -> list[dict]:
	"""Consume each delivered input in proportion to the received share of the Work Order output."""
	work_order = frappe.get_doc("YRP Work Order", grn.against_id)
	total_output = sum(flt(row.qty) for row in work_order.get("receivables") or [])
	if total_output <= 0:
		return []
	available = {
		row.name: max(flt(row.qty) - flt(row.pending_quantity) - flt(row.stock_update), 0)
		for row in work_order.get("deliverables") or []
	}
	plan = []
	for received in grn.get("items") or []:
		share = flt(received.get("quantity")) / total_output
		if share <= 0:
			continue
		for source in work_order.get("deliverables") or []:
			quantity = flt(flt(source.qty) * share, 6)
			if quantity > available[source.name] + QTY_TOLERANCE:
				frappe.throw(
					_(
						"Work Order {0} has only {1} of {2} delivered and not yet consumed, but this receipt needs {3}."
					).format(work_order.name, flt(available[source.name], 6), source.item_variant, quantity)
				)
			available[source.name] -= quantity
			plan.append(get_consumption_row(grn, work_order, received, source, quantity))
	return plan


def get_consumption_row(grn, work_order, received, source, quantity) -> dict:
	from yrp.stock.utils import get_conversion_factor, get_stock_balance
	from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

	conversion = get_conversion_factor(source.item_variant, source.uom)
	factor = flt(conversion.get("conversion_factor")) or 1
	dimensions = _stock_dimension_values(work_order, source)
	_balance, balance_rate = get_stock_balance(
		source.item_variant,
		grn.from_warehouse,
		posting_date=grn.posting_date,
		posting_time=grn.posting_time,
		with_valuation_rate=True,
		**dimensions,
	)
	return {
		"goods_received_note_item": received.name,
		"received_item_variant": received.item_variant,
		"item_variant": source.item_variant,
		"quantity": quantity,
		"stock_qty": flt(quantity * factor, 6),
		"uom": source.uom,
		"stock_uom": conversion.get("stock_uom") or source.uom,
		"conversion_factor": factor,
		"work_order_deliverable": source.name,
		"valuation_rate": flt(source.get("valuation_rate") or source.get("rate") or balance_rate),
		"dimensions": dimensions,
		"set_combination": received.get("set_combination") or {},
	}
