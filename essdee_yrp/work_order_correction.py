import frappe
from frappe import _
from frappe.utils import cint, flt, today
from yrp.stock.shortage import get_stock_qty_precision

from essdee_yrp.work_order_correction_hooks import (
	get_correction_deliverable_items,
	get_exact_source_cloth_item,
)

CORRECTION_DOCTYPE = "YRP Work Order Correction"
WORK_ORDER_HEADER_FIELDS = (
	"process_name",
	"item",
	"production_detail",
	"supplier",
	"delivery_location",
	"wo_date",
	"supplier_address",
	"delivery_address",
)


def is_correction_supported(work_order) -> bool:
	"""Corrections need a submitted, open Work Order."""
	return cint(work_order.docstatus) == 1 and work_order.get("open_status") == "Open"


def can_create_correction(work_order) -> bool:
	return bool(
		is_correction_supported(work_order)
		and frappe.has_permission("YRP Work Order", "write", doc=work_order)
		and frappe.has_permission(CORRECTION_DOCTYPE, "create")
		and frappe.has_permission(CORRECTION_DOCTYPE, "submit")
	)


@frappe.whitelist()
def get_work_order_correction_context(work_order: str) -> dict:
	"""Popup context: whether a correction can be created and which deliverable Items are allowed."""
	doc = frappe.get_doc("YRP Work Order", work_order)
	doc.check_permission("read")
	items = get_correction_deliverable_items(doc.production_detail) if doc.get("production_detail") else []
	cloth_item = get_exact_source_cloth_item(doc.name)
	return {
		"can_create": can_create_correction(doc),
		"deliverable_items": [item for item in items if item != cloth_item],
	}


@frappe.whitelist(methods=["POST"])
def create_work_order_correction(
	work_order: str,
	deliverable_details=None,
	receivable_details=None,
	reason: str | None = None,
) -> str:
	"""Create and submit a Work Order Correction from grouped deliverable/receivable rows."""
	doc = frappe.get_doc("YRP Work Order", work_order)
	doc.check_permission("write")
	if not is_correction_supported(doc):
		frappe.throw(
			_("Work Order {0} must be submitted and open.").format(frappe.bold(doc.name))
		)
	correction = frappe.new_doc(CORRECTION_DOCTYPE)
	correction.update({fieldname: doc.get(fieldname) for fieldname in WORK_ORDER_HEADER_FIELDS})
	correction.update({"work_order": doc.name, "correction_date": today(), "reason": reason})
	correction.deliverable_details = frappe.as_json(_grouped_rows(deliverable_details))
	correction.receivable_details = frappe.as_json(_grouped_rows(receivable_details))
	correction.insert()
	correction.submit()
	return correction.name


def _grouped_rows(value) -> list:
	groups = frappe.parse_json(value) if isinstance(value, str) else value
	if groups is None:
		return []
	if not isinstance(groups, list):
		frappe.throw(_("Correction rows must be a grouped item list."))
	return groups


def write_off_correction_stock(doc):
	"""Called by Work Order close: remove correction-delivered stock still at the supplier (no valuation transfer)."""
	if doc.get("open_status") != "Close":
		return
	from frappe.utils import nowdate, nowtime
	from yrp.stock.stock_ledger import make_sl_entries
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _get_warehouse_for_supplier

	warehouse = _get_warehouse_for_supplier(doc.supplier)
	rows = _delivered_correction_rows(doc.name)
	if not warehouse or not rows:
		return
	entries = _correction_write_off_entries(doc, rows, warehouse, nowdate(), nowtime())
	if entries:
		make_sl_entries(entries, force_inline=True)


def _delivered_correction_rows(work_order):
	from essdee_yrp.work_order_reopen import get_unreversed_close_entries

	precision = get_stock_qty_precision()
	written_off = {}
	for entry in get_unreversed_close_entries(work_order):
		written_off[entry.voucher_detail_no] = written_off.get(entry.voucher_detail_no, 0) + abs(entry.qty)
	rows = []
	for name in frappe.get_all(
		CORRECTION_DOCTYPE, filters={"work_order": work_order, "docstatus": 1}, pluck="name"
	):
		for row in frappe.get_doc(CORRECTION_DOCTYPE, name).get("deliverables") or []:
			row.outstanding_qty = flt(
				row.qty - row.pending_quantity - written_off.get(row.name, 0), precision
			)
			if row.outstanding_qty > 0:
				rows.append(row)
	return rows


def _correction_write_off_entries(doc, rows, warehouse, posting_date, posting_time):
	from yrp.stock.dimensions import get_dimension_fieldnames
	from yrp.stock.utils import get_conversion_factor, get_stock_balance

	balances = {}
	entries = []
	for row in rows:
		conversion = get_conversion_factor(row.item_variant, row.uom)
		stock_qty = row.outstanding_qty * (conversion.get("conversion_factor") or 1)
		dimensions = {
			fieldname: row.get(fieldname) for fieldname in get_dimension_fieldnames() if row.get(fieldname)
		}
		bucket = (row.item_variant, tuple(sorted(dimensions.items())))
		if bucket not in balances:
			balances[bucket] = max(
				get_stock_balance(
					row.item_variant,
					warehouse,
					posting_date=posting_date,
					posting_time=posting_time,
					**dimensions,
				)
				or 0,
				0,
			)
		stock_qty = min(stock_qty, balances[bucket])
		if stock_qty <= 0:
			continue
		balances[bucket] -= stock_qty
		entries.append(
			{
				"item": row.item_variant,
				"warehouse": warehouse,
				"uom": conversion.get("stock_uom") or row.uom,
				"voucher_type": doc.doctype,
				"voucher_no": doc.name,
				"voucher_detail_no": row.name,
				"posting_date": posting_date,
				"posting_time": posting_time,
				"qty": -stock_qty,
				"rate": 0,
				"is_cancelled": 0,
				**dimensions,
			}
		)
	return entries
