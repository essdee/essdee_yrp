import frappe
from frappe import _
from frappe.utils import flt
from yrp.attribute_links import value as _attribute_value

from essdee_yrp.fabric_requirement import _as_json

MAX_PIECE_WEIGHT_KG = 1.0
PRECISION = 4


class MarkerPieceWeightError(frappe.ValidationError):
	pass


def get_marker_piece_weight(ipd_doc, panels, ratio_rows):
	"""Ratio-weighted kg per garment for the selected panels, from IPD cutting consumption.

	``ratio_rows`` are ``{size, panel, ratio}``; a row without a panel applies to every panel.
	"""
	return IPDCuttingWeights(ipd_doc).get_piece_weight(panels, ratio_rows)


class IPDCuttingWeights:
	"""Cutting consumption rows of one IPD, read the way Lot fabric demand reads them."""

	def __init__(self, ipd_doc):
		self.ipd_name = ipd_doc.name
		self.attributes = [row.attribute for row in ipd_doc.cutting_attributes]
		self.rows = _as_json(ipd_doc.get("cutting_items_json")).get("items") or []
		self.size_attribute = self._attribute_if_used(ipd_doc.primary_item_attribute)
		self.panel_attribute = self._attribute_if_used(ipd_doc.stiching_attribute)
		self.part_attribute = (
			self._attribute_if_used(ipd_doc.set_item_attribute) if ipd_doc.is_set_item else None
		)
		self.panel_quantity = {}
		self.panel_part = {}
		for row in ipd_doc.stiching_item_details:
			panel = _attribute_value(row.stiching_attribute_value)
			self.panel_quantity[panel] = flt(row.quantity) or 1
			self.panel_part[panel] = (
				_attribute_value(row.set_item_attribute_value) if ipd_doc.is_set_item else None
			)

	def _attribute_if_used(self, attribute):
		return attribute if attribute and attribute in self.attributes else None

	def get_piece_weight(self, panels, ratio_rows):
		if not self.rows:
			self.fail(_("IPD {0} has no cutting consumption weights.").format(self.ipd_name))
		total = sum(
			group["quantity"] * self.get_group_weight(group, ratio_rows) for group in self.get_groups(panels)
		)
		return flt(total, PRECISION)

	def get_groups(self, panels):
		"""Weight groups: one per panel, or one per Part / whole garment averaged over its pieces."""
		if self.panel_attribute:
			return [
				{
					"label": panel,
					"attribute": self.panel_attribute,
					"value": panel,
					"panels": [panel],
					"quantity": self.panel_quantity.get(panel, 1),
				}
				for panel in panels
			]
		if self.part_attribute:
			return [
				self.get_part_group(part, panels)
				for part in dict.fromkeys(self.panel_part.get(panel) for panel in panels)
			]
		return [
			{
				"label": _("whole garment"),
				"attribute": None,
				"value": None,
				"panels": panels,
				"quantity": self.get_piece_share(panels, list(self.panel_quantity)),
			}
		]

	def get_part_group(self, part, panels):
		part_panels = [panel for panel, panel_part in self.panel_part.items() if panel_part == part]
		selected = [panel for panel in panels if panel in part_panels]
		return {
			"label": part,
			"attribute": self.part_attribute,
			"value": part,
			"panels": selected,
			"quantity": self.get_piece_share(selected, part_panels),
		}

	def get_piece_share(self, selected, all_panels):
		"""Share of pieces selected, so one stored weight is split evenly per piece."""
		total = sum(self.panel_quantity[panel] for panel in all_panels)
		if not total:
			self.fail(_("IPD {0} has no stitching panels to split the cutting weight.").format(self.ipd_name))
		return sum(self.panel_quantity.get(panel, 1) for panel in selected) / total

	def get_group_weight(self, group, ratio_rows):
		size_ratios = get_size_ratios(ratio_rows, group["panels"])
		if not self.size_attribute:
			return self.get_weight(group, None)
		weighted_sizes = {size: ratio for size, ratio in size_ratios.items() if ratio > 0}
		if not weighted_sizes:
			weighted_sizes = dict.fromkeys(size_ratios, 1)
		if not weighted_sizes:
			self.fail(_("Build the size ratios before the piece weight can be calculated."))
		total_ratio = sum(weighted_sizes.values())
		return (
			sum(ratio * self.get_weight(group, size) for size, ratio in weighted_sizes.items()) / total_ratio
		)

	def get_weight(self, group, size):
		"""Average weight across colours and dias for one group and size."""
		weights = [
			flt(row.get("Weight"))
			for row in self.rows
			if (not group["attribute"] or row.get(group["attribute"]) == group["value"])
			and (size is None or row.get(self.size_attribute) == size)
		]
		label = group["label"] if size is None else f"{group['label']} / {size}"
		if not weights or any(weight <= 0 for weight in weights):
			self.fail(_("IPD {0} has no cutting weight for {1}.").format(self.ipd_name, label))
		if any(weight > MAX_PIECE_WEIGHT_KG for weight in weights):
			self.fail(
				_("IPD {0} cutting weight for {1} is above {2} kg; it looks like grams. Fix the IPD.").format(
					self.ipd_name, label, MAX_PIECE_WEIGHT_KG
				)
			)
		return sum(weights) / len(weights)

	def fail(self, message):
		raise MarkerPieceWeightError(message)


def get_size_ratios(ratio_rows, panels):
	"""Mean ratio per size across the given panels."""
	ratios = {}
	for row in ratio_rows:
		panel = _attribute_value(row.get("panel")) if row.get("panel") else None
		if panel and panel not in panels:
			continue
		ratios.setdefault(_attribute_value(row.get("size")), []).append(flt(row.get("ratio")))
	return {size: sum(values) / len(values) for size, values in ratios.items()}
