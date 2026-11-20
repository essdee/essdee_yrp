"""Material Receipt, folding Work Order, Process Cost, DC and GRN for one old Sample DC."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, flt
from yrp.party_addresses import get_party_address
from yrp.stock.save_stock_items import group_items_for_ui
from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant

from essdee_yrp.essdee_yrp.old_dc_grn_migration.documents import find_tagged, get_tag, set_posting

from .data import LOCATION, LOT, PROCESS_COST_TAX_SLAB, PROCESS_RATES

RECEIPT_TIME, DC_TIME, GRN_TIME = "09:00:00", "10:00:00", "18:00:00"


def get_variant(line):
	return get_or_create_variant(line["item"], line["attributes"]) if line["attributes"] else line["item"]


def get_uom(item):
	return frappe.db.get_value("Item", item, "stock_uom")


def insert_and_submit(doc):
	doc.insert()
	doc.submit()
	return doc


def make_material_receipt(document):
	"""The DC's deliverable stock under lot Sample at the store, posted before the DC on its date."""
	received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	items = []
	for line in document["deliverables"]:
		variant = get_variant(line)
		items.append(
			{
				"item": variant,
				"qty": line["qty"],
				"uom": get_uom(variant),
				"rate": line["rate"],
				"lot": LOT,
				"received_type": received_type,
			}
		)
	doc = frappe.new_doc("YRP Stock Entry")
	doc.update(
		{
			"naming_series": "STE-.YYYY.-",
			"purpose": "Material Receipt",
			"to_warehouse": LOCATION,
			"comments": get_tag(f"stock for {document['number']}"),
		}
	)
	doc.item_details = frappe.as_json(group_items_for_ui(items, "YRP Stock Entry"))
	set_posting(doc, document["date"], RECEIPT_TIME)
	return insert_and_submit(doc)


def get_rows(lines):
	rows = []
	for line in lines:
		variant = get_variant(line)
		rows.append({"item_variant": variant, "qty": line["qty"], "uom": get_uom(variant), "lot": LOT})
	return rows


def make_work_order(document):
	"""A folding Work Order with the old DC's manual deliverable and receivable rows."""
	last_date = max([grn["date"] for grn in document.get("grns", [])] + [document["date"]])
	doc = frappe.new_doc("YRP Work Order")
	doc.update(
		{
			"naming_series": "YRP-WO-.YYYY.-",
			"process_name": document["process"],
			"lot": LOT,
			"supplier": document["supplier"],
			"supplier_address": get_party_address(document["supplier"], preferred_type="Billing"),
			"delivery_location": LOCATION,
			"delivery_address": get_party_address(LOCATION, preferred_type="Billing"),
			"edit_wo_date": 1,
			"wo_date": document["date"],
			"planned_start_date": document["date"],
			"planned_end_date": last_date,
			"expected_delivery_date": max(last_date, str(add_days(document["date"], 7))),
			"comments": get_tag(document["number"]),
			"deliverables": get_rows(document["deliverables"]),
			"receivables": get_rows(document["receivables"]),
		}
	)
	doc.insert()
	return doc


def ensure_process_cost(work_order):
	"""An approved flat Process Cost at the user's rate, unless one already applies."""
	if work_order.get_receivable_process_cost():
		return None
	doc = frappe.new_doc("YRP Process Cost")
	doc.update(
		{
			"process_name": work_order.process_name,
			"supplier": work_order.supplier,
			"item": work_order.item,
			"lot": LOT,
			"uom": get_uom(work_order.item),
			"from_date": work_order.wo_date,
			"tax_slab": PROCESS_COST_TAX_SLAB,
		}
	)
	doc.append("process_cost_values", {"price": PROCESS_RATES[work_order.process_name]})
	doc.insert()
	apply_workflow(doc, "Submit")
	doc = apply_workflow(doc, "Approve")
	if doc.docstatus != 1 or doc.workflow_state != "Approved":
		frappe.throw(f"Process Cost {doc.name} is {doc.workflow_state} after approval")
	return doc.name


def set_rolls(items, lines, quantity_field):
	rolls = {get_variant(line): line["rolls"] for line in lines if line["rolls"]}
	for item in items:
		if rolls.get(item["item_variant"]) and flt(item.get(quantity_field)) > 0:
			item["secondary_qty"] = rolls[item["item_variant"]]


def make_delivery_challan(work_order, document):
	"""Deliver every pending deliverable from the store, as the DC form prefills it."""
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import get_work_order_defaults

	defaults = get_work_order_defaults(work_order, posting_date=document["date"], posting_time=DC_TIME)
	items = [item for item in defaults["items"] if flt(item.get("qty")) > 0]
	set_rolls(items, document["deliverables"], "qty")
	doc = frappe.new_doc("YRP Delivery Challan")
	doc.update(
		{
			k: v
			for k, v in defaults.items()
			if k not in ("items", "correction_items", "correction_item_details")
		}
	)
	doc.update(
		{
			"naming_series": "DC-.YYYY.-",
			"work_order": work_order,
			"from_location": LOCATION,
			"from_address": get_party_address(LOCATION, preferred_type="Billing"),
			"supplier_address": get_party_address(document["supplier"], preferred_type="Billing"),
			"comments": get_tag(document["number"]),
			"supplier_document_no": document["number"],
		}
	)
	doc.item_details = frappe.as_json(group_items_for_ui(items, "YRP Delivery Challan"))
	set_posting(doc, document["date"], DC_TIME)
	return insert_and_submit(doc)


def make_goods_received_note(work_order, delivery_challan, grn):
	"""Receive the old GRN's lines on the Work Order's receivable rows of the same variant."""
	from essdee_yrp.overrides.goods_received_note import get_work_order_defaults

	defaults = get_work_order_defaults(work_order, delivery_challan)
	quantities = {get_variant(line): line["qty"] for line in grn["lines"]}
	items = []
	for item in defaults["items"]:
		item["quantity"] = quantities.pop(item["item_variant"], 0)
		if item["quantity"]:
			items.append(item)
	if quantities:
		frappe.throw(f"{grn['number']}: no receivable for {', '.join(quantities)}")
	set_rolls(items, grn["lines"], "quantity")
	doc = frappe.new_doc("YRP Goods Received Note")
	doc.update(
		{
			k: v
			for k, v in defaults.items()
			if k not in ("items", "correction_items", "correction_item_details")
		}
	)
	doc.update(
		{
			"naming_series": "YRP-GRN-.YYYY.-",
			"against": "YRP Work Order",
			"against_id": work_order,
			"delivery_challan": delivery_challan,
			"supplier_address": get_party_address(defaults["supplier"], preferred_type="Billing"),
			"delivery_address": get_party_address(defaults["delivery_location"], preferred_type="Billing"),
			"comments": get_tag(grn["number"]),
			"supplier_document_no": grn["number"],
			"delivery_date": grn["date"],
		}
	)
	doc.item_details = frappe.as_json(group_items_for_ui(items, "YRP Goods Received Note"))
	set_posting(doc, grn["date"], GRN_TIME)
	return insert_and_submit(doc)


class DocumentMigrator:
	"""Creates one old DC's documents in order, skipping any that an earlier run already tagged."""

	def __init__(self, document):
		self.document = document
		self.created, self.skipped = {}, {}

	def record(self, doctype, name, created):
		(self.created if created else self.skipped).setdefault(doctype, []).append(name)

	def get_or_make(self, doctype, number, make):
		existing = find_tagged(doctype, {"comments": get_tag(number)})
		if existing:
			self.record(doctype, existing, False)
			return existing
		name = make().name
		self.record(doctype, name, True)
		return name

	def run(self):
		document, number = self.document, self.document["number"]
		self.get_or_make("YRP Stock Entry", f"stock for {number}", lambda: make_material_receipt(document))
		work_order = find_tagged("YRP Work Order", {"comments": get_tag(number)})
		if work_order:
			self.record("YRP Work Order", work_order, False)
		else:
			doc = make_work_order(document)
			process_cost = ensure_process_cost(doc)
			if process_cost:
				self.record("YRP Process Cost", process_cost, True)
			doc.reload()
			doc.submit()
			work_order = doc.name
			self.record("YRP Work Order", work_order, True)
		dc = self.get_or_make(
			"YRP Delivery Challan", number, lambda: make_delivery_challan(work_order, document)
		)
		for grn in document.get("grns", []):
			self.get_or_make(
				"YRP Goods Received Note",
				grn["number"],
				lambda grn=grn: make_goods_received_note(work_order, dc, grn),
			)
