from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, today

from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics
from essdee_yrp.planning.dashboard.processes import LotProcesses
from essdee_yrp.planning.dashboard.production_orders import (
	OPEN_PPO_FILTERS,
	PPO,
	get_iso_date,
	get_lots,
	get_lots_with_work_orders,
	get_ppo_details,
	get_ppo_items,
	get_product_categories,
)
from essdee_yrp.planning.reports.production_quantities import authorize_filter_values


def get_tracking_options():
	"""Open PPO options (with item, for search by item) and open Lot options (lots with a submitted Work Order)."""
	production_orders = frappe.get_list(
		PPO,
		filters=OPEN_PPO_FILTERS,
		fields=["name", "status", "delivery_date"],
		order_by="name asc",
		limit_page_length=0,
	)
	items = get_ppo_items([row["name"] for row in production_orders])
	lots = get_lots([row["name"] for row in production_orders])
	started = get_lots_with_work_orders([row["name"] for row in lots])
	tracked = get_tracked_lots(LotMetrics(lots, sewing_processes=[]), started)
	categories = get_product_categories(row["item"] for row in lots)
	ppo_categories = defaultdict(set)
	for row in lots:
		if categories.get(row["item"]):
			ppo_categories[row["production_order"]].add(categories[row["item"]])
	return {
		"ppos": [
			{
				"name": row["name"],
				"item": items[row["name"]]["item"],
				"item_name": items[row["name"]]["item_name"],
				"status": row["status"],
				"delivery": get_iso_date(row["delivery_date"]),
				"product_categories": sorted(ppo_categories[row["name"]]),
			}
			for row in production_orders
		],
		"lots": [
			{
				"name": row["name"],
				"item": row["item"],
				"ppo": row["production_order"],
				"product_category": categories.get(row["item"]),
			}
			for row in lots
			if row["name"] in tracked
		],
	}


def get_tracked_lots(metrics, started):
	"""Lots PPO Tracking shows: those with a submitted Work Order or a yarn / fabric PO."""
	return started | set(metrics.purchase_totals)


def get_category_values(values):
	"""Product Category names of a filter; an empty list when none."""
	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not values:
		return []
	if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
		frappe.throw(_("Product Category filter values must be a list of names."))
	return list(dict.fromkeys(values))


def get_category_production_orders(categories):
	"""Open PPOs with an open lot whose item is in one of the Product Categories."""
	lots = get_lots(frappe.get_list(PPO, filters=OPEN_PPO_FILTERS, pluck="name", limit_page_length=0))
	by_item = get_product_categories(row["item"] for row in lots)
	return [row["production_order"] for row in lots if by_item.get(row["item"]) in categories]


def get_scope_production_orders(ppos, lots, categories=None):
	"""Selected open PPOs, else the open PPOs of the selected lots, else those with a lot in the categories."""
	if ppos:
		names = ppos
	elif not lots:
		names = get_category_production_orders(categories or [])
	else:
		names = frappe.get_list(
			"SD YRP Lot",
			filters={"name": ["in", lots]},
			pluck="production_order",
			limit_page_length=0,
		)
	return frappe.get_list(
		PPO,
		filters={"name": ["in", list({name for name in names if name})], **OPEN_PPO_FILTERS},
		fields=["name", "delivery_date"],
		order_by="name asc",
		limit_page_length=0,
	)


def get_tracking_data(ppos=None, lots=None, product_categories=None):
	"""Lots of the selected PPOs, Lots or Product Categories with status, quantities and processes; one is required."""
	ppos = authorize_filter_values(PPO, ppos)
	lots = authorize_filter_values("SD YRP Lot", lots)
	categories = get_category_values(product_categories)
	if not ppos and not lots and not categories:
		frappe.throw(_("Select a PPO, Lot or Product Category to begin."))
	production_orders = get_scope_production_orders(ppos, lots, categories)
	ppo_lots = get_lots([row["name"] for row in production_orders])
	item_categories = get_product_categories(row["item"] for row in ppo_lots)
	started = get_lots_with_work_orders([row["name"] for row in ppo_lots])
	metrics = LotMetrics(ppo_lots)
	tracked = get_tracked_lots(metrics, started)
	summaries = {name: metrics.get_summary(name) for name in tracked}
	quantities = {row["name"]: metrics.get_lot_quantity(row["name"]) for row in ppo_lots}
	details = get_ppo_details(production_orders, ppo_lots, quantities)
	for name, info in details.items():
		info["lots"] = [
			{
				**get_ppo_lot(row, quantities[row["name"]], row["name"] in started),
				"product_category": item_categories.get(row["item"]),
			}
			for row in ppo_lots
			if row["production_order"] == name
		]
		info["work_order_lots"] = [
			get_work_order_lot(row, summaries[row["name"]])
			for row in ppo_lots
			if row["production_order"] == name and row["name"] in started
		]
	scope = [
		row
		for row in ppo_lots
		if row["name"] in tracked
		and (not lots or row["name"] in lots)
		and (not categories or item_categories.get(row["item"]) in categories)
	]
	processes = LotProcesses(metrics)
	return {
		"as_of": today(),
		"ppos": details,
		"lots": [
			{
				**get_lot_row(row, details, summaries[row["name"]], processes),
				"has_work_order": row["name"] in started,
				"purchase": metrics.get_purchase_summary(row["name"]),
				"product_category": item_categories.get(row["item"]),
			}
			for row in scope
		],
	}


def get_ppo_lot(row, quantity, has_work_order):
	return {
		"lot": row["name"],
		"item": row["item"],
		"planned": quantity,
		"has_work_order": has_work_order,
	}


def get_work_order_lot(row, summary):
	return {
		"lot": row["name"],
		"status": summary["status"],
		"qty": summary["qty"],
		"cut_pcs": summary["cut"],
		"dispatch": summary["dispatch"],
		"to_alternative": summary["to_alternative"],
	}


def get_lot_row(row, details, summary, processes):
	ppo_quantity = flt(details[row["production_order"]]["lot_shares"].get(row["name"]), 3)
	return {
		"lot": row["name"],
		"ppo": row["production_order"],
		"item": row["item"],
		"delivery": details[row["production_order"]]["delivery"],
		"qty": summary["qty"],
		"is_set": summary["is_set"],
		"ppo_qty": ppo_quantity,
		"status": summary["status"],
		"planned": summary["planned"],
		"cut": summary["order_cut"],
		"cut_pcs": summary["cut"],
		"total": summary["total"],
		"dispatch": summary["dispatch"],
		"to_alternative": summary["to_alternative"],
		"alternatives": summary["alternatives"],
		"balance": ladder.get_balance(ppo_quantity, summary["dispatch"], summary["to_alternative"]),
		"processes": processes.get_processes(row["name"]),
	}
