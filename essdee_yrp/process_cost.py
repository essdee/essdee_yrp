"""Essdee Lot/IPD adapters for the base YRP Process Cost DocType."""

import frappe
from frappe import _
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value
from yrp.attribute_values import get_mapping_document
from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.yrp_process_cost import yrp_process_cost as base_process_cost

from essdee_yrp.folding_lot import is_folding_lot


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_attributes(doctype, txt, searchfield, start, page_len, filters):
	if doctype != "Item Attribute":
		return []
	filters = frappe._dict(filters or {})
	if not filters.item or not filters.lot or not filters.process:
		return []
	_check_process_cost_permissions(
		item=filters.item,
		lot=filters.lot,
		process_name=filters.process,
	)

	ipd_name = _resolve_ipd_name(filters.item, filters.lot, filters.process)
	if not ipd_name and is_folding_lot(filters.lot):
		return base_process_cost.get_item_attributes(doctype, txt, searchfield, start, page_len, filters)
	if not ipd_name:
		return []
	frappe.has_permission("YRP Item Production Detail", "read", doc=ipd_name, throw=True)
	ipd = frappe.get_cached_doc("YRP Item Production Detail", ipd_name)
	process_name = filters.process
	attributes = []
	if ipd.get("is_cloth_item"):
		attributes = [row.attribute for row in ipd.get("item_attributes") or []]
	elif ipd.cutting_process == process_name:
		attributes = [ipd.stiching_attribute, ipd.packing_attribute]
	elif ipd.stiching_process == process_name:
		attributes = [ipd.packing_attribute, ipd.primary_item_attribute]
		if ipd.is_set_item:
			attributes.append(ipd.set_item_attribute)
	elif ipd.packing_process == process_name:
		attributes = [ipd.primary_item_attribute]
	elif not frappe.db.get_value("YRP Process", process_name, "is_group"):
		for row in ipd.get("ipd_processes") or []:
			if row.process_name != process_name:
				continue
			stage = _attribute_value(row.get("in_stage")) or row.get("stage")
			if stage == _attribute_value(ipd.stiching_in_stage):
				attributes = [ipd.stiching_attribute, ipd.packing_attribute]
			elif stage == _attribute_value(ipd.stiching_out_stage):
				attributes = [ipd.packing_attribute, ipd.primary_item_attribute]
			else:
				attributes = [ipd.primary_item_attribute]
			break
	else:
		item = frappe.get_cached_doc("Item", filters.item)
		attributes = [row.attribute for row in item.get("attributes") or []]

	seen = {ipd.get("dependent_attribute")}
	return [
		[attribute]
		for attribute in attributes
		if attribute
		and attribute not in seen
		and not seen.add(attribute)
		and (not txt or txt.lower() in attribute.lower())
	]


@frappe.whitelist()
def get_pc_attribute_values(
	item=None,
	attribute=None,
	lot=None,
	process_name=None,
	for_link=0,
):
	"""Return IPD-mapped values for the selected Lot and process.

	Base YRP also invokes this endpoint from its generic form handler with only
	``item`` and ``attribute``. Returning ``None`` for that generic invocation
	prevents it from racing and replacing the Lot-specific rows populated by the
	Essdee Desk handler.
	"""
	if not lot:
		return None
	if not attribute:
		return []
	_check_process_cost_permissions(item=item, lot=lot, process_name=process_name)

	ipd_name = _resolve_ipd_name(item, lot, process_name)
	if not ipd_name and is_folding_lot(lot):
		return base_process_cost.get_pc_attribute_values(item, attribute, for_link)
	if not ipd_name:
		frappe.throw(_("Item {0} has no Item Production Detail in Lot {1}.").format(item, lot))
	frappe.has_permission("YRP Item Production Detail", "read", doc=ipd_name, throw=True)
	ipd = frappe.get_cached_doc("YRP Item Production Detail", ipd_name)
	mapping = next(
		(
			row.mapping
			for row in (ipd.get("item_attributes") or [])
			if row.attribute == attribute and row.mapping
		),
		None,
	)
	if not mapping:
		mapping = frappe.db.get_value(
			"YRP Item Item Attribute",
			{
				"parent": ipd_name,
				"parenttype": "YRP Item Production Detail",
				"attribute": attribute,
			},
			"mapping",
		)
	if not mapping:
		return []

	values = []
	if attribute == ipd.stiching_attribute and process_name != ipd.cutting_process:
		embellishments = update_if_string_instance(ipd.get("emblishment_details_json")) or {}
		for panel in embellishments.get(process_name, {}) or {}:
			values.append(panel)
	else:
		mapping_doc = get_mapping_document(mapping, cached=True)
		values = [_attribute_value(row.attribute_value) for row in mapping_doc.get("values") or []]

	return [
		{
			"attribute_value": attribute_db.link(value, attribute) if frappe.utils.cint(for_link) else value,
			"price": 0,
			"min_order_qty": 0,
		}
		for value in dict.fromkeys(value for value in values if value)
	]


def _check_process_cost_permissions(*, item=None, lot=None, process_name=None):
	frappe.has_permission("YRP Process Cost", "read", throw=True)
	for doctype, name in (
		("Item", item),
		("SD YRP Lot", lot),
		("YRP Process", process_name),
	):
		if name:
			frappe.has_permission(doctype, "read", doc=name, throw=True)


def _resolve_ipd_name(item, lot, process_name=None):
	"""IPD of the chosen (else the Lot) Item: the Lot IPD for the Lot Item, else its Lot fabric IPD."""
	if not lot:
		return None
	lot_item = attribute_db.get_value("SD YRP Lot", lot, "item")
	if not item or item == lot_item:
		return attribute_db.get_value("SD YRP Lot", lot, "production_detail")
	fabric_ipds = set(
		frappe.get_all(
			"SD YRP Lot Fabric Detail",
			filters={"parent": lot, "parenttype": "SD YRP Lot", "cloth_item": item},
			pluck="production_detail",
		)
	) - {None, ""}
	if len(fabric_ipds) > 1 and process_name:
		from essdee_yrp.api.work_order import _get_work_order_selection_context

		context = _get_work_order_selection_context(lot, process_name, check_permission=False)
		fabric_ipds = {row["production_detail"] for row in context["options"] if row["item"] == item}
	return fabric_ipds.pop() if len(fabric_ipds) == 1 else None


def validate_enabled_item(item):
	"""A Process Cost accepts any enabled Item, template or variant."""
	if item and frappe.db.get_value("Item", item, "disabled") != 0:
		frappe.throw(_("Select an enabled Item."))


def before_validate(doc, method=None):
	if not doc.get("lot") or not doc.get("process_name"):
		return
	if not doc.item:
		doc.item = attribute_db.get_value("SD YRP Lot", doc.lot, "item")
	validate_enabled_item(doc.item)
	if doc.item:
		doc.uom = frappe.db.get_value("Item", doc.item, "stock_uom")
	validate_attribute(doc)


def validate_attribute(doc):
	"""Attributes come from the Item's IPD; billing has no price for its dependent attribute (Stage)."""
	if not doc.get("depends_on_attribute") or not doc.get("attribute"):
		return
	ipd_name = _resolve_ipd_name(doc.item, doc.lot, doc.process_name)
	if not ipd_name and is_folding_lot(doc.lot):
		return
	if not ipd_name:
		frappe.throw(
			_(
				"Item {0} has no Item Production Detail in Lot {1}. Remove the Attribute for a flat cost."
			).format(doc.item, doc.lot)
		)
	dependent_attribute = frappe.db.get_value("YRP Item Production Detail", ipd_name, "dependent_attribute")
	if doc.attribute == dependent_attribute:
		frappe.throw(
			_(
				"Process Cost cannot depend on {0}, the item's dependent attribute. "
				"Choose another attribute or none."
			).format(dependent_attribute)
		)
