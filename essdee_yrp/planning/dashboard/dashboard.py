import frappe
from frappe.utils import flt, today

from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics, get_sewing_processes
from essdee_yrp.planning.dashboard.production_orders import (
	OPEN_PPO_FILTERS,
	PPO,
	get_linked_lots,
	get_lots,
	get_lots_with_work_orders,
	get_ppo_details,
	get_product_categories,
)

ZERO_FIGURES = ("planned", "cut", "stitch", "packed", "total", "dispatch", "to_alternative")


def get_dashboard_data():
	"""Every submitted Open PPO and its open lots with status and quantities, for the factory-wide Dashboard."""
	production_orders = frappe.get_list(
		PPO,
		filters=OPEN_PPO_FILTERS,
		fields=["name", "delivery_date"],
		order_by="name asc",
		limit_page_length=0,
	)
	lots = get_lots([row["name"] for row in production_orders])
	started = get_lots_with_work_orders([row["name"] for row in lots])
	sewing = get_sewing_processes()
	metrics = LotMetrics(lots, sewing)
	ppos = get_ppo_details(
		production_orders, lots, {lot["name"]: metrics.get_lot_quantity(lot["name"]) for lot in lots}
	)
	ppo_only_rows = get_ppo_only_rows(production_orders, lots, ppos)
	categories = get_product_categories(
		[*(lot["item"] for lot in lots), *(row["item"] for row in ppo_only_rows)]
	)
	return {
		"as_of": today(),
		"sewing_processes": sewing,
		"ppos": ppos,
		"lots": [
			{
				**get_lot_row(lot, ppos[lot["production_order"]], metrics, lot["name"] in started),
				"product_category": categories.get(lot["item"]),
			}
			for lot in lots
		]
		+ [{**row, "product_category": categories.get(row["item"])} for row in ppo_only_rows],
	}


def get_ppo_only_rows(production_orders, lots, ppos):
	"""Rows for Open PPOs with no open lot row: Lot not linked with no lot at all, Lots closed when every lot is closed."""
	names = [row["name"] for row in production_orders]
	with_lot_rows = {lot["production_order"] for lot in lots}
	linked = get_linked_lots(names)
	rows = []
	for name in names:
		if name in with_lot_rows:
			continue
		if name not in linked:
			rows.append(get_ppo_only_row(name, ppos[name], ladder.LOT_NOT_LINKED))
		elif "Open" not in linked[name].values():
			closed = ", ".join(f"{lot} ({status})" for lot, status in sorted(linked[name].items()))
			rows.append(get_ppo_only_row(name, ppos[name], ladder.LOTS_CLOSED, closed))
	return rows


def get_ppo_only_row(name, ppo, status, closed_lots=None):
	"""An Open PPO row without a lot: PPO item and quantity only, lot figures left empty."""
	return {
		"lot": None,
		"closed_lots": closed_lots,
		"ppo": name,
		"item": ppo["item"],
		"delivery": ppo["delivery"],
		"ppo_qty": ppo["pieces"],
		"has_work_order": False,
		"status": status,
		"status_rank": ladder.get_status_rank(status, 0),
	}


def get_lot_row(lot, ppo, metrics, has_work_order):
	"""One Dashboard lot: pieces (sets for set items) with its share of the PPO and Balance = that share − dispatched."""
	summary = metrics.get_summary(lot["name"])
	figures = (
		{key: summary[key] for key in ZERO_FIGURES} if has_work_order else dict.fromkeys(ZERO_FIGURES, 0.0)
	)
	ppo_quantity = flt(ppo["lot_shares"].get(lot["name"]), 3)
	return {
		"lot": lot["name"],
		"ppo": lot["production_order"],
		"item": lot["item"],
		"delivery": ppo["delivery"],
		"qty": summary["qty"],
		"is_set": summary["is_set"],
		"ppo_qty": ppo_quantity,
		"has_work_order": has_work_order,
		"status": summary["status"],
		"status_rank": summary["status_rank"],
		"purchase_split": summary["purchase_split"],
		**figures,
		"balance": ladder.get_balance(ppo_quantity, figures["dispatch"], figures["to_alternative"]),
	}
