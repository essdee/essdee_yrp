# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

from essdee_yrp.delivery_challan_hooks import requires_exact_source_lifecycle
from essdee_yrp.fabric_ipd import get_yarn_ratio_inputs


def get_correction_deliverable_items(production_detail):
	"""Items an IPD sanctions as correction deliverables: its own item, yarn inputs and Item BOM items."""
	ipd = frappe.get_cached_doc("YRP Item Production Detail", production_detail)
	allowed = {ipd.get("item")}
	allowed.update(row.item for row in get_yarn_ratio_inputs(ipd))
	allowed.update(row.item for row in ipd.get("item_bom") or [])
	return sorted(item for item in allowed if item)


def validate_correction_ipd_items(doc, method=None):
	"""Every Work Order Correction deliverable must be sanctioned by the WO's
	Item Production Detail (see get_correction_deliverable_items)."""
	validate_exact_source_cloth_rows(doc)
	ipd_name = doc.get("production_detail")
	if not ipd_name:
		return
	allowed = set(get_correction_deliverable_items(ipd_name))
	for row in doc.get("deliverables") or []:
		if not row.item_variant:
			continue
		template = get_parent_item(row.item_variant)
		if template not in allowed:
			frappe.throw(
				_(
					"Deliverable {0} (item {1}) is not sanctioned by Item Production Detail {2}: "
					"it is not the IPD item, its yarn item or an Item BOM item."
				).format(row.item_variant, template, ipd_name)
			)


def get_exact_source_cloth_item(work_order):
	"""The cloth template an exact-source Work Order tracks by GRN lineage, else None."""
	probe = frappe._dict(doctype="YRP Delivery Challan", work_order=work_order, items=[])
	if not requires_exact_source_lifecycle(probe):
		return None
	return frappe.db.get_value("YRP Work Order", work_order, "item")


def validate_exact_source_cloth_rows(doc):
	"""Exact-source cloth moves only through GRN-lineage WO rows; correction rows cannot carry it."""
	rows = (doc.get("deliverables") or []) + (doc.get("receivables") or [])
	if not rows or not doc.get("work_order"):
		return
	cloth_item = get_exact_source_cloth_item(doc.work_order)
	if not cloth_item:
		return
	for row in rows:
		if row.item_variant and get_parent_item(row.item_variant) == cloth_item:
			frappe.throw(
				_(
					"Work Order {0} tracks {1} by exact source GRN lineage. Correct cloth "
					"{2} with a new Work Order; corrections can add dyes, chemicals, yarn and "
					"other non-cloth rows."
				).format(doc.work_order, cloth_item, row.item_variant)
			)
