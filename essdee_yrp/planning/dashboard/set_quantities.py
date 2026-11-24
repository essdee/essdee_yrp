import json
from collections import defaultdict
from functools import cached_property

import frappe
from frappe.utils import flt


def get_set_attributes(production_details):
	"""{IPD: (part attribute, size attribute)} of the set-item IPDs among `production_details`."""
	names = list({name for name in production_details if name})
	if not names:
		return {}
	rows = frappe.get_all(
		"YRP Item Production Detail",
		filters={"name": ["in", names], "is_set_item": 1},
		fields=["name", "set_item_attribute", "primary_item_attribute"],
		limit_page_length=0,
	)
	return {row["name"]: (row["set_item_attribute"], row["primary_item_attribute"]) for row in rows}


def get_variant_attributes(variants):
	"""{variant: {attribute: value}}."""
	variants = list({variant for variant in variants if variant})
	if not variants:
		return {}
	rows = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", variants], "parenttype": "Item"},
		fields=["parent", "attribute", "attribute_value"],
		limit_page_length=0,
	)
	result = defaultdict(dict)
	for row in rows:
		result[row["parent"]][row["attribute"]] = row["attribute_value"]
	return result


def get_major_colour(set_combination):
	return (json.loads(set_combination) if set_combination else {}).get("major_colour") or ""


def count_sets(rows, attributes, part_attribute, size_attribute, parts):
	"""Complete sets in `rows` of (variant, set combination, quantity).

	Per major colour and size a set needs every one of `parts`, so it counts the fewest of them;
	a row whose variant has no part is already a whole set.
	"""
	whole = 0.0
	by_key = defaultdict(lambda: defaultdict(float))
	for variant, combination, quantity in rows:
		values = attributes.get(variant, {})
		part = values.get(part_attribute)
		if not part:
			whole += flt(quantity)
			continue
		by_key[(get_major_colour(combination), values.get(size_attribute))][part] += flt(quantity)
	parts = parts or sorted({part for quantities in by_key.values() for part in quantities})
	return whole + sum(min(quantities.get(part, 0.0) for part in parts) for quantities in by_key.values())


class SetQuantities:
	"""Lot and Work Order quantities of set-item lots counted in sets; `lots` are SD YRP Lot rows."""

	def __init__(self, lots, orders):
		self.lots = lots
		self.orders = orders

	@cached_property
	def attributes_by_lot(self):
		by_ipd = get_set_attributes(row.get("production_detail") for row in self.lots.values())
		return {
			name: by_ipd[row["production_detail"]]
			for name, row in self.lots.items()
			if row.get("production_detail") in by_ipd
		}

	def is_set(self, lot):
		return lot in self.attributes_by_lot

	@cached_property
	def order_rows(self):
		"""{lot: [(variant, set combination, pieces)]} of the set lots' Lot Order Details."""
		names = list(self.attributes_by_lot)
		if not names:
			return {}
		rows = frappe.get_all(
			"SD YRP Lot Order Detail",
			filters={"parent": ["in", names], "parenttype": "SD YRP Lot"},
			fields=["parent", "item_variant", "set_combination", "quantity"],
			limit_page_length=0,
		)
		result = defaultdict(list)
		for row in rows:
			result[row["parent"]].append((row["item_variant"], row["set_combination"], row["quantity"]))
		return result

	@cached_property
	def received_rows(self):
		"""{work order: [(variant, set combination, received)]} of the set lots' Work Orders."""
		names = [order["name"] for order in self.orders if self.is_set(order["lot"])]
		if not names:
			return {}
		rows = frappe.get_all(
			"YRP Work Order Calculated Item",
			filters={"parent": ["in", names], "parenttype": "YRP Work Order"},
			fields=["parent", "item_variant", "set_combination", "received_qty"],
			limit_page_length=0,
		)
		result = defaultdict(list)
		for row in rows:
			result[row["parent"]].append((row["item_variant"], row["set_combination"], row["received_qty"]))
		return result

	@cached_property
	def variant_attributes(self):
		rows = [row for rows in self.order_rows.values() for row in rows]
		rows += [row for rows in self.received_rows.values() for row in rows]
		return get_variant_attributes(row[0] for row in rows)

	def get_parts(self, lot):
		part_attribute = self.attributes_by_lot[lot][0]
		return sorted(
			{
				self.variant_attributes.get(row[0], {}).get(part_attribute)
				for row in self.order_rows.get(lot, [])
			}
			- {None}
		)

	def count(self, lot, rows):
		part_attribute, size_attribute = self.attributes_by_lot[lot]
		return count_sets(rows, self.variant_attributes, part_attribute, size_attribute, self.get_parts(lot))

	def get_lot_sets(self, lot):
		return self.count(lot, self.order_rows.get(lot, []))

	def get_received_sets(self, lot, orders):
		return self.count(lot, [row for order in orders for row in self.received_rows.get(order["name"], [])])
