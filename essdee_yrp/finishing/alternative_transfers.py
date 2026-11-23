from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt
from yrp.utils import get_variant_attr_details

from essdee_yrp.finishing.parsing import json_object


def get_alternative_transfers(source_lots, per_variant=False):
	"""{source lot: [{lot, item, work_order, quantity, boxes}]}, one row per alternative lot made from a source lot.

	Quantity is the converted pieces on the alternative lot's submitted packing Work Order (first
	conversion plus top-ups), not the source Lot reduction, which is capped at its planned pieces.
	`per_variant` adds `variants`: {alternative item variant: pieces}.
	"""
	lots = list({lot for lot in source_lots or [] if lot})
	if not lots:
		return {}
	rows = frappe.db.sql(
		"""select alternative.transferred_lot, alternative.name, alternative.item, wo.name,
		ifnull(alternative.packing_combo, 0), ci.item_variant, sum(ci.quantity)
		from `tabSD YRP Lot` alternative
		join `tabYRP Work Order` wo on wo.lot=alternative.name and wo.docstatus=1
			and wo.includes_packing=1 and ifnull(wo.is_rework, 0)=0
		join `tabYRP Work Order Calculated Item` ci on ci.parent=wo.name and ci.parenttype='YRP Work Order'
		where alternative.is_transferred=1 and alternative.transferred_lot in %(lots)s
		group by alternative.transferred_lot, alternative.name, alternative.item, wo.name,
			alternative.packing_combo, ci.item_variant
		order by alternative.creation, wo.name""",
		{"lots": tuple(lots)},
	)
	transfers = {}
	for source, lot, item, work_order, combo, variant, quantity in rows:
		row = transfers.setdefault(
			(source, lot, work_order),
			{
				"lot": lot,
				"item": item,
				"work_order": work_order,
				"quantity": 0.0,
				"combo": flt(combo),
				"variants": {},
			},
		)
		row["quantity"] += flt(quantity)
		row["variants"][variant] = row["variants"].get(variant, 0.0) + flt(quantity)
	result = defaultdict(list)
	for (source, _lot, _work_order), row in transfers.items():
		combo = row.pop("combo")
		row["boxes"] = round(row["quantity"] / combo, 3) if combo else None
		if not per_variant:
			row.pop("variants")
		result[source].append(row)
	return dict(result)


def get_alternative_quantities(source_lots):
	"""{source lot: pieces moved to alternative lots}; status rules count these as dispatched."""
	return {
		lot: sum(row["quantity"] for row in rows)
		for lot, rows in get_alternative_transfers(source_lots).items()
	}


def get_transferred_quantities(source_lot, source_keys):
	"""{source Finishing row key: pieces moved to alternative lots}, matched by variant attributes.

	Keys are (item_variant, sorted set_combination items); every converted row must match one.
	"""
	keys_by_attributes = {_attribute_key(*key): key for key in source_keys}
	rows = frappe.db.sql(
		"""select ci.item_variant, ci.set_combination, ci.quantity
		from `tabSD YRP Lot` alternative
		join `tabYRP Work Order` wo on wo.lot=alternative.name and wo.docstatus=1
			and wo.includes_packing=1 and ifnull(wo.is_rework, 0)=0
		join `tabYRP Work Order Calculated Item` ci on ci.parent=wo.name and ci.parenttype='YRP Work Order'
		where alternative.is_transferred=1 and alternative.transferred_lot=%s and ci.quantity > 0""",
		(source_lot,),
		as_dict=True,
	)
	quantities = defaultdict(float)
	for row in rows:
		combination = tuple(sorted(json_object(row.set_combination).items()))
		source_key = keys_by_attributes.get(_attribute_key(row.item_variant, combination))
		if not source_key:
			frappe.throw(
				_("No Finishing row of Lot {0} matches alternative variant {1}").format(
					source_lot, row.item_variant
				)
			)
		quantities[source_key] += flt(row.quantity)
	return dict(quantities)


def _attribute_key(item_variant, combination):
	attributes = get_variant_attr_details(item_variant)
	return tuple(sorted((str(name), str(value)) for name, value in attributes.items())), combination
