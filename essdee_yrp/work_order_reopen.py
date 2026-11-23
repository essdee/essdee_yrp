import frappe
from frappe import _
from frappe.utils import escape_html, flt
from yrp.stock.dimensions import get_dimension_fieldnames
from yrp.stock.shortage import get_stock_qty_precision
from yrp.stock.utils import get_conversion_factor

from essdee_yrp.work_order_close import has_close_valuation

CLOSE_FIELDS = ("closed_by", "sd_close_reason", "close_reason", "close_other_reason", "close_remarks")


@frappe.whitelist(methods=["POST"])
def reopen_work_order(work_order):
	"""Receive a close write-off back at the supplier and mark the Work Order Open; close valuation stays."""
	frappe.only_for("System Manager")
	frappe.db.sql("SELECT name FROM `tabYRP Work Order` WHERE name=%s FOR UPDATE", (work_order,))
	doc = frappe.get_doc("YRP Work Order", work_order)
	if doc.docstatus != 1 or doc.open_status != "Close":
		frappe.throw(_("Only a closed Work Order can be reopened. {0} is not closed.").format(doc.name))

	close_entries = get_unreversed_close_entries(doc.name)
	precision = get_stock_qty_precision()
	if not close_entries and any(
		flt(row.stock_update, precision) > 0 for row in doc.get("deliverables") or []
	):
		frappe.throw(
			_(
				"Cannot reopen Work Order {0}: its deliverables show stock written off on close, "
				"but no active close stock ledger entries were found to reverse."
			).format(doc.name)
		)

	stock_entry = make_reopen_receipt(doc, close_entries) if close_entries else None
	restore_deliverable_stock_update(doc, close_entries)
	for fieldname in CLOSE_FIELDS:
		if doc.meta.get_field(fieldname):
			doc.set(fieldname, None)
	doc.open_status = "Open"
	doc.set_total_quantity()
	doc.save(ignore_permissions=True)

	restored_qty = round(sum(abs(flt(entry.qty)) for entry in close_entries), 3)
	doc.add_comment("Comment", get_reopen_comment(stock_entry, close_entries))
	return {"status": "Open", "stock_entry": stock_entry, "restored_qty": restored_qty}


def get_unreversed_close_entries(work_order):
	"""Close write-off SLEs of this Work Order not yet received back by a reopen."""
	dimension_columns = "".join(f", sle.`{fieldname}`" for fieldname in get_dimension_fieldnames())
	return frappe.db.sql(
		f"""
		SELECT sle.name, sle.item, sle.warehouse, sle.uom, sle.qty, sle.voucher_detail_no,
		       sle.stock_value_difference, sle.outgoing_rate, sle.valuation_rate{dimension_columns}
		FROM `tabYRP Stock Ledger Entry` sle
		WHERE sle.voucher_type = 'YRP Work Order'
		  AND sle.voucher_no = %(work_order)s
		  AND sle.is_cancelled = 0
		  AND sle.qty < 0
		  AND NOT EXISTS (
			SELECT 1
			FROM `tabYRP Stock Entry Detail` detail
			INNER JOIN `tabYRP Stock Entry` entry ON entry.name = detail.parent
			WHERE entry.docstatus = 1
			  AND entry.against = 'YRP Work Order'
			  AND entry.against_id = %(work_order)s
			  AND detail.against = 'YRP Stock Ledger Entry'
			  AND detail.against_id_detail = sle.name
		  )
		ORDER BY sle.posting_datetime, sle.creation
		""",
		{"work_order": work_order},
		as_dict=True,
	)


def make_reopen_receipt(doc, close_entries):
	"""Submit a Material Receipt putting each close SLE's qty back in its own bucket.

	The value comes back only when no close valuation moved it into the outputs already.
	"""
	warehouses = {entry.warehouse for entry in close_entries}
	if len(warehouses) != 1:
		frappe.throw(
			_("Close ledger of {0} spans several warehouses: {1}").format(doc.name, ", ".join(warehouses))
		)
	receipt = frappe.new_doc("YRP Stock Entry")
	receipt.update(
		{
			"purpose": "Material Receipt",
			"to_warehouse": warehouses.pop(),
			"against": "YRP Work Order",
			"against_id": doc.name,
			"comments": _("Reopen of Work Order {0}").format(doc.name),
		}
	)
	restores_value = not has_close_valuation(doc.name)
	for entry in close_entries:
		qty = abs(flt(entry.qty))
		rate = (
			abs(flt(entry.stock_value_difference)) / qty or flt(entry.outgoing_rate or entry.valuation_rate)
			if restores_value
			else 0
		)
		receipt.append(
			"items",
			{
				"item": entry.item,
				"qty": qty,
				"uom": entry.uom,
				"rate": rate,
				"allow_zero_valuation_rate": int(not rate),
				"against": "YRP Stock Ledger Entry",
				"against_id_detail": entry.name,
				**{fieldname: entry.get(fieldname) for fieldname in get_dimension_fieldnames()},
			},
		)
	receipt.insert(ignore_permissions=True)
	receipt.submit()
	return receipt.name


def restore_deliverable_stock_update(doc, close_entries):
	precision = get_stock_qty_precision()
	rows = {row.name: row for row in doc.get("deliverables") or []}
	for entry in close_entries:
		row = rows.get(entry.voucher_detail_no)
		if not row:
			continue
		factor = flt(get_conversion_factor(row.item_variant, row.uom).get("conversion_factor")) or 1
		row.stock_update = max(flt(flt(row.stock_update) - abs(flt(entry.qty)) / factor, precision), 0)


def get_reopen_comment(stock_entry, close_entries):
	if not stock_entry:
		return _("Work Order reopened. Close had no stock write-off to restore.")
	lines = [
		_("{0} {1} {2}").format(escape_html(entry.item), f"{abs(flt(entry.qty)):g}", entry.uom)
		for entry in close_entries
	]
	header = _("Work Order reopened. Close write-off received back via Material Receipt {0}:").format(
		frappe.utils.get_link_to_form("YRP Stock Entry", stock_entry)
	)
	return "<br>".join([header, *lines])
