import frappe
from frappe.utils import flt, today

from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics, get_sewing_processes
from essdee_yrp.planning.dashboard.production_orders import (
	OPEN_PPO_FILTERS,
	PPO,
	get_lots,
	get_lots_with_work_orders,
	get_ppo_details,
	get_product_categories,
)

ZERO_FIGURES = ("planned", "cut", "stitch", "packed", "total", "dispatch", "to_alternative", "balance")


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
	ppos = get_ppo_details(production_orders, lots)
	started = get_lots_with_work_orders([row["name"] for row in lots])
	sewing = get_sewing_processes()
	metrics = LotMetrics(lots, sewing)
	categories = get_product_categories(lot["item"] for lot in lots)
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
		],
	}


def get_lot_row(lot, ppo, metrics, has_work_order):
	row = {
		"lot": lot["name"],
		"ppo": lot["production_order"],
		"item": lot["item"],
		"delivery": ppo["delivery"],
		"qty": flt(lot["total_order_quantity"]),
		"has_work_order": has_work_order,
	}
	summary = metrics.get_summary(lot["name"])
	figures = (
		{key: summary[key] for key in ZERO_FIGURES} if has_work_order else dict.fromkeys(ZERO_FIGURES, 0.0)
	)
	return {
		**row,
		"status": summary["status"],
		"status_rank": summary["status_rank"],
		"purchase_split": summary["purchase_split"],
		**figures,
	}
