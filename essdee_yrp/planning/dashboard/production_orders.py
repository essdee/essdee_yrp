from collections import defaultdict

import frappe
from frappe.utils import flt

from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.planning.reports.production_quantities import child_rows

PPO = "YRP Production Order"
OPEN_PPO_FILTERS = {"docstatus": 1, "status": "Open"}
LOT_FIELDS = [
	"name",
	"item",
	"production_order",
	"packing_combo",
	"total_order_quantity",
	"total_quantity",
	"production_detail",
]


def get_iso_date(value):
	return str(value) if value else None


def get_lots(production_orders):
	"""Open SD YRP Lot rows of these PPOs, readable by the user."""
	if not production_orders:
		return []
	return frappe.get_list(
		"SD YRP Lot",
		filters={"production_order": ["in", list(production_orders)], "status": "Open"},
		fields=LOT_FIELDS,
		order_by="production_order asc, name asc",
		limit_page_length=0,
	)


def get_lots_with_work_orders(lot_names):
	if not lot_names:
		return set()
	return set(
		frappe.get_list(
			"YRP Work Order",
			filters={"lot": ["in", list(lot_names)], "docstatus": 1},
			pluck="lot",
			distinct=True,
			limit_page_length=0,
		)
	)


def get_item_names(items):
	if not items:
		return {}
	return dict(
		frappe.get_all(
			"Item",
			filters={"name": ["in", list(items)]},
			fields=["name", "item_name"],
			as_list=True,
			limit_page_length=0,
		)
	)


def get_product_categories(items):
	"""{item: Product Category}; a variant without one takes its template's; items with none are left out."""
	items = list({item for item in items if item})
	if not items:
		return {}
	rows = frappe.db.sql(
		"""select item.name, coalesce(nullif(item.product_category, ''), template.product_category)
		from `tabItem` item left join `tabItem` template on template.name=item.variant_of
		where item.name in %(items)s""",
		{"items": tuple(items)},
	)
	return {name: category for name, category in rows if category}


def get_ppo_items(production_orders):
	"""{PPO: {boxes, item, item_name}} from YRP Production Order Detail; item codes are sorted."""
	boxes, items = defaultdict(float), defaultdict(set)
	for row in child_rows("YRP Production Order Detail", production_orders, ["item", "quantity"], PPO):
		boxes[row["parent"]] += flt(row["quantity"])
		items[row["parent"]].add(row["item"])
	names = get_item_names({item for values in items.values() for item in values})
	result = {}
	for name in production_orders:
		codes = sorted(items[name])
		result[name] = {
			"boxes": flt(boxes[name], 3),
			"item": ", ".join(codes),
			"item_name": ", ".join(names.get(code) or code for code in codes),
		}
	return result


def get_ordered_boxes(production_orders):
	"""{PPO: {lot: boxes}} from YRP Production Ordered Detail, the PPO quantity each lot took."""
	if not production_orders:
		return defaultdict(dict)
	rows = frappe.db.sql(
		"""select parent, ifnull(nullif(lot, ''), reference_name), sum(quantity)
		from `tabYRP Production Ordered Detail`
		where parenttype=%(doctype)s and parent in %(names)s group by 1, 2""",
		{"doctype": PPO, "names": tuple(production_orders)},
	)
	result = defaultdict(dict)
	for ppo, lot, boxes in rows:
		result[ppo][lot] = flt(boxes)
	return result


def get_conversion(unit, pieces_per_box, combos):
	"""How PPO pieces were found: the Packing Combo, the lots' own pieces per box, or the quantity already in pieces."""
	if unit == "pieces":
		return "stored in pieces"
	if not pieces_per_box:
		return ""
	return "packing combo" if combos == {pieces_per_box} else "lots' pieces per box"


def get_ppo_quantity(boxes, lots, lot_quantities, ordered):
	"""{pieces_per_box, pieces, conversion, lot_shares} of one PPO over its open `lots`; pieces None when it cannot be converted."""
	lot_pieces = sum(lot_quantities[lot["name"]] for lot in lots)
	combos = {flt(lot.get("packing_combo")) for lot in lots if flt(lot.get("packing_combo"))}
	pieces_per_box = ladder.get_pieces_per_box(
		lot_pieces, sum(flt(lot.get("total_quantity")) for lot in lots), combos
	)
	pieces, unit = ladder.get_ppo_pieces(boxes, pieces_per_box, lot_pieces)
	weights = {lot["name"]: ordered.get(lot["name"], 0.0) for lot in lots}
	if not any(weights.values()):
		weights = {lot["name"]: lot_quantities[lot["name"]] for lot in lots}
	return {
		"pieces_per_box": flt(pieces_per_box, 3) if pieces_per_box else None,
		"pieces": flt(pieces, 3) if pieces is not None else None,
		"conversion": get_conversion(unit, pieces_per_box, combos),
		"lot_shares": ladder.split_quantity(pieces or 0.0, weights),
	}


def get_ppo_details(production_orders, lots, lot_quantities):
	"""{PPO: {delivery, item, item_name, boxes, pieces_per_box, pieces, conversion, lot_shares}}; `production_orders` are PPO rows.

	`lot_quantities` holds each lot's pieces (sets for set items); every PPO's pieces are split over its open lots.
	"""
	names = [row["name"] for row in production_orders]
	items = get_ppo_items(names)
	ordered_boxes = get_ordered_boxes(names)
	by_ppo = defaultdict(list)
	for lot in lots:
		by_ppo[lot["production_order"]].append(lot)
	result = {}
	for row in production_orders:
		name = row["name"]
		result[name] = {
			"delivery": get_iso_date(row.get("delivery_date")),
			**items[name],
			**get_ppo_quantity(items[name]["boxes"], by_ppo[name], lot_quantities, ordered_boxes[name]),
		}
	return result
