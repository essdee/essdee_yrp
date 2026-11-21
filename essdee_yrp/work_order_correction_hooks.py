# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

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
	if doc.get("work_order") and frappe.db.get_value(
		"YRP Work Order", doc.work_order, "fabric_source_process"
	):
		frappe.throw(
			_(
				"Work Order Corrections are not allowed for an exact-source fabric Work "
				"Order. Create a new Work Order from available predecessor GRNs."
			)
		)
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
