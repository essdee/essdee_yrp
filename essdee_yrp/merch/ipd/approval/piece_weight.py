"""Piece weight for the approval review: the stored cutting grid as keyed, plus weight warnings."""

import statistics

from frappe.utils import flt

GRID_COLUMNS = ("Dia", "Weight")
OUTLIER_RATIO = 1.5


def number(value):
	try:
		return float(value)
	except TypeError, ValueError:
		return None


def is_outlier(weight, median):
	return bool(weight and median and (weight > median * OUTLIER_RATIO or weight < median / OUTLIER_RATIO))


class GridBasis:
	"""Rows of `cutting_items_json` merged where neighbouring sizes or colours carry the same weight."""

	def __init__(self, grid, size_attribute, colour_attribute, sizes):
		self.items = [dict(item) for item in grid.get("items") or []]
		self.basis = [key for key in grid.get("attributes") or [] if key not in GRID_COLUMNS]
		self.size = size_attribute if size_attribute in self.basis else None
		self.colour = colour_attribute if colour_attribute in self.basis else None
		self.others = [key for key in self.basis if key not in (self.size, self.colour)]
		self.size_order = {size: index for index, size in enumerate(sizes)}

	@property
	def columns(self):
		return [key for key in (*self.others, self.colour, self.size) if key]

	def flag_outliers(self):
		peers = {}
		for item in self.items:
			item["outlier_median"] = None
			key = tuple(item.get(attribute) for attribute in self.basis if attribute != self.colour)
			peers.setdefault(key, []).append(item)
		if not self.colour:
			return
		for group in peers.values():
			weights = sorted(item["Weight"] for item in group if item.get("Weight"))
			if len(weights) < 3:
				continue
			median = weights[len(weights) // 2]
			for item in group:
				if is_outlier(item.get("Weight"), median):
					item["outlier_median"] = median

	def size_runs(self):
		groups = {}
		for item in self.items:
			key = tuple(item.get(attribute) for attribute in (*self.others, self.colour) if attribute)
			groups.setdefault(key, []).append(item)
		rows = []
		for key, group in groups.items():
			if self.size:
				group.sort(key=lambda item: self.size_order.get(item.get(self.size), 99))
			for item in group:
				self.add_to_run(rows, key, item)
		return rows

	def add_to_run(self, rows, key, item):
		last = rows[-1] if rows else None
		same = (
			last
			and last["group"] == key
			and (last["dia"], last["weight"], last["outlier_median"])
			== (item.get("Dia"), item.get("Weight"), item["outlier_median"])
		)
		if same and self.size:
			last["sizes"].append(item.get(self.size))
			return
		rows.append(
			{
				"group": key,
				"values": {attribute: item.get(attribute) for attribute in self.others},
				"colours": [item.get(self.colour)] if self.colour else [],
				"sizes": [item.get(self.size)] if self.size else [],
				"dia": item.get("Dia"),
				"weight": item.get("Weight"),
				"outlier_median": item["outlier_median"],
			}
		)

	def merge_colours(self, rows):
		merged = []
		for row in rows:
			row["signature"] = (tuple(row["values"].items()), row["size_label"], row["dia"], row["weight"])
			match = None
			if not row["outlier_median"]:
				match = next(
					(
						seen
						for seen in merged
						if not seen["outlier_median"] and seen["signature"] == row["signature"]
					),
					None,
				)
			if match:
				match["colours"].extend(row["colours"])
			else:
				merged.append(row)
		return merged

	def get_rows(self):
		self.flag_outliers()
		rows = self.size_runs()
		for row in rows:
			sizes = row["sizes"]
			row["size_label"] = f"{sizes[0]} – {sizes[-1]}" if len(sizes) > 1 else (sizes[0] if sizes else "")
		if self.colour:
			rows = self.merge_colours(rows)
		order = list(dict.fromkeys(tuple(row["values"].items()) for row in rows))
		rows.sort(key=lambda row: order.index(tuple(row["values"].items())))
		for row in rows:
			row.pop("group")
			row.pop("signature", None)
		return rows


def get_piece_weight(values, attributes):
	grid = values.get("cutting_items_json") or {}
	basis = GridBasis(grid, attributes["primary"], attributes["packing"], attributes["sizes"])
	return {
		"basis": basis.basis,
		"columns": basis.columns,
		"size_attribute": basis.size,
		"colour_attribute": basis.colour,
		"rows": basis.get_rows(),
		"source_rows": len(basis.items),
		"from_panel_matrix": bool(values.get("enable_panel_wise_consumption_matrix")),
	}


def matrix_groups(matrix):
	groups = []
	for group in matrix.get("panels") or []:
		columns = group.get("packing_values") or []
		rows = [
			{
				"key": row.get("primary_value") or "",
				"cells": {
					column: number(((row.get("values") or {}).get(column) or {}).get("weight"))
					for column in columns
				},
			}
			for row in group.get("rows") or []
		]
		groups.append(
			{
				"label": group.get("panel_value") or "All panels",
				"panels": group.get("panel_values") or [],
				"rows": rows,
			}
		)
	return groups, True


def grid_groups(grid, panel_attribute, packing_attribute):
	keys = [key for key in grid.get("attributes") or [] if key not in GRID_COLUMNS]
	group_by = panel_attribute if panel_attribute in keys else None
	column_by = packing_attribute if packing_attribute in keys else None
	row_by = [key for key in keys if key not in (group_by, column_by)]
	groups = {}
	for item in grid.get("items") or []:
		label = item.get(group_by) if group_by else "All panels"
		group = groups.setdefault(label, {"label": label, "panels": [label] if group_by else [], "rows": {}})
		key = " / ".join(str(item.get(attribute)) for attribute in row_by)
		row = group["rows"].setdefault(key, {"key": key, "cells": {}})
		row["cells"][item.get(column_by) if column_by else "Weight"] = number(item.get("Weight"))
	return [{**group, "rows": list(group["rows"].values())} for group in groups.values()], bool(group_by)


def weight_groups(values, panel_wise, panel_attribute, packing_attribute):
	"""Weights as the cutting floor sees them: the panel-wise matrix when enabled, else the stored grid."""
	matrix = ((panel_wise or {}).get("consumption") or {}).get("matrix")
	if values.get("enable_panel_wise_consumption_matrix") and matrix:
		return matrix_groups(matrix)
	return grid_groups(values.get("cutting_items_json") or {}, panel_attribute, packing_attribute)


def get_weight_span(groups):
	"""Smallest and largest whole-piece weight: panel weights summed per row and column."""
	totals = {}
	for group in groups:
		for row in group["rows"]:
			for column, weight in row["cells"].items():
				key = (row["key"], column)
				totals[key] = flt((totals.get(key) or 0) + (weight or 0), 4)
	weights = [weight for weight in totals.values() if weight]
	return {"min": min(weights), "max": max(weights)} if weights else None


def outlier_warnings(groups):
	found = []
	for group in groups:
		for row in group["rows"]:
			weights = [weight for weight in row["cells"].values() if weight]
			if len(weights) < 3:
				continue
			median = statistics.median(weights)
			odd = [column for column, weight in row["cells"].items() if is_outlier(weight, median)]
			if odd:
				label = group["label"] + (f" · {row['key']}" if row["key"] else "")
				found.append((label, odd, median))
	if len(found) > 2:
		odd = ", ".join(found[0][1])
		return [
			f"{odd} weight differs from the other colours by more than 50% in {len(found)} size rows. Check the entry."
		]
	return [
		f"{label}: {', '.join(odd)} weight differs from the other colours by more than 50% (median {median:g} kg)."
		for label, odd, median in found
	]


def get_weight_warnings(groups, by_panel, panel_names, panel_attribute):
	warnings = []
	if not groups:
		warnings.append(("danger", "No cutting weights entered."))
	weighted = {panel for group in groups for panel in group["panels"]}
	missing = [panel for panel in panel_names if weighted and panel not in weighted]
	if missing and by_panel:
		warnings.append(("danger", f"{panel_attribute}s without weight: {', '.join(missing)}."))
	blank = sum(
		1 for group in groups for row in group["rows"] for weight in row["cells"].values() if not weight
	)
	if blank:
		warnings.append(("danger", f"{blank} weight cell(s) are blank or zero."))
	warnings.extend(("warning", text) for text in outlier_warnings(groups))
	return [{"level": level, "section": "weight", "text": text} for level, text in warnings]
