"""Pre-check the masters the lots need and recreate the missing ones from the prod values in data.MASTERS."""

import frappe
from yrp.party_addresses import get_party_address

from essdee_yrp.essdee_yrp.old_dc_grn_migration.data import MASTERS

ATTRIBUTES = ("Colour", "Dia")

# Suppliers the lots need with a Supplier, Billing Address and Warehouse (user decision 16-11-2026); values copied from prod.
SUPPLIERS = {
	"Sri Pavai Knits": {
		"supplier": {
			"supplier_name": "Sri Pavai Knits",
			"supplier_group": "Knitting",
			"supplier_type": "Individual",
			"country": "India",
			"gstin": "33BJIPV1566L1ZP",
			"gst_category": "Registered Regular",
		},
		"address": {
			"address_title": "Sri Pavai Knits",
			"address_type": "Billing",
			"address_line1": "1/641a, Ground, Pavai Knit",
			"address_line2": "Palavanjipalayam Road, Veerapondi Post,",
			"city": "Tiruppur",
			"state": "Tamil Nadu",
			"country": "India",
			"pincode": "641604",
			"gstin": "33BJIPV1566L1ZP",
			"gst_category": "Registered Regular",
			"is_primary_address": 1,
			"is_shipping_address": 1,
		},
		"warehouse_company": "Essdee Knitting Mills Private Limited",
	},
}

# Cloth Item yarn recipes the user added on prod (13-11-2026; 30'S OE BLACK 05-11-2026); values copied from prod.
CLOTH_YARN_RECIPES = {
	"25's OE Cloth": [{"yarn_item": "Yarn 25's OE", "ratio": 100.0}],
	"30'S OE BLACK": [{"yarn_item": "Yarn 30's OE", "ratio": 100.0}],
	"40's VL Interlock Cloth": [{"yarn_item": "Yarn 40's VL", "ratio": 100.0}],
}

# Garment IPD cloth rows the user re-pointed on prod (16-11-2026): IPD -> {cloth type: cloth Item}.
IPD_CLOTHS = {
	"Solid Gym Vest (Assorted)-1": {"Dyed Fabric": "36's GL Dyed Cloth"},
}

# Lot cloth programs the user built on prod (16-11-2026), rebuilt with Build Cloth Programs where the lot has none:
# lot -> cloth Item -> [(finished colour, Dias, knitting output colour, use dyed yarn, yarn colour)]; values copied from
# the prod cloth IPDs (knitting Dia = finished Dia). GY0926-10: 36's GL Dyed Cloth-8 and 30's OE Cloth-10.
# GY0926-25: 36's GL Dyed Cloth-9 (Knitting -> Dyeing), 36's GL White Fabric-2 and 30's OE Cloth-12 (Knitting ->
# Washing; the run adds the Washing step).
LOT_CLOTH_PROGRAMS = {
	"GY0926-10": {
		"36's GL Dyed Cloth": [
			("Red", (24, 26, 28, 30, 32), "Greige", 0, "Greige"),
			("Khaki", (26, 28, 30, 32), "Greige", 0, "Greige"),
		],
		"30's OE Cloth": [
			("Black", (20, 22, 24, 26), "Black", 1, "Black"),
			("Navy", (28, 30, 32), "Navy", 1, "Navy"),
			("Grey Melange", (20,), "Grey Melange", 0, "Greige"),
			("Andhra Melange", (20, 22, 24, 26), "Andhra Melange", 0, "Greige"),
		],
	},
	"GY0926-25": {
		"36's GL Dyed Cloth": [
			("Maroon", (24, 26, 28, 30, 32), "Greige", 0, "Greige"),
			("Navy", (24, 26, 28, 30, 32), "Greige", 0, "Greige"),
		],
		"36's GL White Fabric": [("White", (24, 26, 28, 30, 32), "White", 1, "White")],
		"30's OE Cloth": [
			("Black", (20, 22, 24, 26), "Black", 1, "Black"),
			("Andhra Melange", (20, 22, 24, 26), "Andhra Melange", 0, "Greige"),
		],
	},
}


def get_local_process(name):
	if not frappe.db.exists("YRP Process", name):
		return None
	doc = frappe.get_doc("YRP Process", name)
	return {
		"is_cloth_process": int(doc.is_cloth_process or 0),
		"value_change_attributes": sorted(row.attribute for row in doc.get("value_change_attributes") or []),
	}


def is_same_process(local, prod):
	return bool(local) and local == {
		"is_cloth_process": int(prod["is_cloth_process"]),
		"value_change_attributes": sorted(prod["value_change_attributes"]),
	}


def has_yarn_recipe(item):
	doc = frappe.get_doc("Item", item)
	return (
		bool(doc.is_cloth_item)
		and [
			{"yarn_item": row.yarn_item, "ratio": float(row.ratio)}
			for row in doc.get("yarn_ratio_details") or []
		]
		== CLOTH_YARN_RECIPES[item]
	)


def get_ipd_cloths(ipd):
	"""{cloth type: cloth Item} of the listed cloth types on the garment IPD."""
	rows = frappe.get_all(
		"SD YRP Item Production Detail Cloth Detail",
		filters={"parent": ipd, "parentfield": "cloth_detail", "name1": ["in", list(IPD_CLOTHS[ipd])]},
		fields=["name1", "cloth"],
	)
	return {row.name1: row.cloth for row in rows}


def get_lot_cloths(lot):
	"""Cloth Items that have a cloth IPD on the lot's fabric rows."""
	rows = frappe.get_all(
		"SD YRP Lot Fabric Detail",
		filters={"parent": lot, "parenttype": "SD YRP Lot", "production_detail": ["is", "set"]},
		pluck="cloth_item",
	)
	return set(rows)


def has_attribute_value(attribute, value):
	return frappe.db.exists(
		"YRP Item Attribute Value", {"attribute_name": attribute, "attribute_value": value}
	)


class MasterCheck:
	"""sync = prod masters this site lacks or configures differently (empty on prod); blocking = needed but not syncable."""

	def __init__(self, lots):
		self.lots = lots
		self.sync, self.blocking = [], []

	def run(self):
		for name, values in sorted(MASTERS["YRP Process"].items()):
			local = get_local_process(name)
			if not is_same_process(local, values):
				self.sync.append(
					{"kind": "YRP Process", "name": name, "action": "update" if local else "create"}
				)
		for attribute in ATTRIBUTES:
			for value in sorted(MASTERS[attribute]):
				if not has_attribute_value(attribute, value):
					self.sync.append({"kind": attribute, "name": value, "action": "create"})
		self.check_suppliers()
		self.check_cloths()
		self.check_existence()
		return self

	def check_suppliers(self):
		for name in sorted(SUPPLIERS):
			if not frappe.db.exists("Supplier", name):
				self.sync.append({"kind": "Supplier", "name": name, "action": "create"})
			if not frappe.db.exists("Warehouse", {"supplier": name}):
				self.sync.append({"kind": "Warehouse", "name": name, "action": "create"})

	def check_cloths(self):
		for item in sorted(CLOTH_YARN_RECIPES):
			if not has_yarn_recipe(item):
				self.sync.append({"kind": "Cloth Yarn Recipe", "name": item, "action": "update"})
		for ipd, cloths in sorted(IPD_CLOTHS.items()):
			if get_ipd_cloths(ipd) != cloths:
				self.sync.append({"kind": "IPD Cloth", "name": ipd, "action": "update"})
		for lot, programs in sorted(LOT_CLOTH_PROGRAMS.items()):
			if not set(programs) <= get_lot_cloths(lot):
				self.sync.append({"kind": "Lot Cloth Programs", "name": lot, "action": "create"})

	def check_existence(self):
		needed = {"Supplier": set(), "Item": set(), "SD YRP Lot": set()}
		for lot in self.lots:
			needed["SD YRP Lot"].add(lot["lot"])
			needed["Supplier"].update(lot["mappings"]["suppliers"].values())
			needed["Item"].update(lot["mappings"]["cloth_by_old_colour"].values())
		for doctype, names in needed.items():
			self.blocking += [
				f"{doctype} '{name}' is missing"
				for name in sorted(names)
				if not frappe.db.exists(doctype, name) and not (doctype == "Supplier" and name in SUPPLIERS)
			]
		for supplier in sorted(needed["Supplier"]):
			if frappe.db.exists("Supplier", supplier) and not get_party_address(
				supplier, preferred_type="Billing"
			):
				self.blocking.append(f"Supplier '{supplier}' has no Address")

	def describe(self):
		lines = []
		for row in self.sync:
			if row["kind"] == "YRP Process":
				values = MASTERS["YRP Process"][row["name"]]
				lines.append(
					f"{row['action']} YRP Process '{row['name']}' (is_cloth_process={values['is_cloth_process']}, "
					f"value change={values['value_change_attributes']})"
				)
			elif row["kind"] == "Supplier":
				lines.append(f"create Supplier '{row['name']}' with its Billing Address")
			elif row["kind"] == "Warehouse":
				lines.append(f"create Warehouse '{row['name']}' for Supplier '{row['name']}'")
			elif row["kind"] == "Cloth Yarn Recipe":
				lines.append(
					f"set Yarn Ratio {CLOTH_YARN_RECIPES[row['name']]} on cloth Item '{row['name']}'"
				)
			elif row["kind"] == "IPD Cloth":
				lines.append(f"set cloths {IPD_CLOTHS[row['name']]} on IPD '{row['name']}'")
			elif row["kind"] == "Lot Cloth Programs":
				cloths = ", ".join(LOT_CLOTH_PROGRAMS[row["name"]])
				lines.append(f"build Lot '{row['name']}' cloth programs ({cloths}) with the prod routes")
			else:
				lines.append(f"create {row['kind']} '{row['name']}' on Item Attribute {row['kind']}")
		return lines


def apply_sync(rows):
	"""Recreate the listed records through their normal doctype saves."""
	for row in rows:
		if row["kind"] == "YRP Process":
			sync_process(row)
		elif row["kind"] == "Supplier":
			create_supplier(row["name"])
		elif row["kind"] == "Warehouse":
			create_warehouse(row["name"])
		elif row["kind"] == "Cloth Yarn Recipe":
			set_yarn_recipe(row["name"])
		elif row["kind"] == "IPD Cloth":
			set_ipd_cloths(row["name"])
		elif row["kind"] == "Lot Cloth Programs":
			build_lot_cloth_programs(row["name"])
		else:
			attribute = frappe.get_doc("Item Attribute", row["kind"])
			attribute.append(
				"item_attribute_values",
				{"attribute_value": row["name"], "abbr": MASTERS[row["kind"]][row["name"]]},
			)
			attribute.save()


def sync_process(row):
	values = MASTERS["YRP Process"][row["name"]]
	if row["action"] == "update":
		doc = frappe.get_doc("YRP Process", row["name"])
	else:
		doc = frappe.new_doc("YRP Process")
		doc.process_name = row["name"]
	doc.update(
		{key: values[key] for key in ("is_cloth_process", "is_item_conversion", "is_manual_entry_in_grn")}
	)
	doc.set(
		"value_change_attributes",
		[{"attribute": attribute} for attribute in values["value_change_attributes"]],
	)
	if row["action"] == "create":
		doc.insert(set_name=row["name"])
	else:
		doc.save()


def create_supplier(name):
	values = SUPPLIERS[name]
	supplier = frappe.new_doc("Supplier")
	supplier.update(values["supplier"])
	supplier.insert(set_name=name)
	address = frappe.new_doc("Address")
	address.update(values["address"])
	address.append("links", {"link_doctype": "Supplier", "link_name": name})
	address.insert()


def create_warehouse(name):
	warehouse = frappe.new_doc("Warehouse")
	warehouse.update(
		{"warehouse_name": name, "supplier": name, "company": SUPPLIERS[name]["warehouse_company"]}
	)
	warehouse.insert()


def set_yarn_recipe(item):
	doc = frappe.get_doc("Item", item)
	doc.is_cloth_item = 1
	doc.set("yarn_ratio_details", CLOTH_YARN_RECIPES[item])
	doc.save()


def set_ipd_cloths(ipd):
	doc = frappe.get_doc("YRP Item Production Detail", ipd)
	for row in doc.cloth_detail:
		row.cloth = IPD_CLOTHS[ipd].get(row.name1, row.cloth)
	doc.save()


def get_cloth_program_selection(cloth, routes):
	"""Build Cloth Programs selection for one cloth from its prod routes; yarns follow the cloth Item recipe."""
	yarns = frappe.get_doc("Item", cloth).get("yarn_ratio_details")
	yarns = [{"yarn_item": row.yarn_item, "ratio": row.ratio} for row in yarns]
	return {
		"cloth_item": cloth,
		"colour_yarn_recipes": [
			{
				"colour": colour,
				"yarn_item": yarn["yarn_item"],
				"yarn_colour": yarn_colour,
				"ratio": yarn["ratio"],
			}
			for colour, _dias, _knit, _dyed, yarn_colour in routes
			for yarn in yarns
		],
		"fabric_routes": [
			{
				"finished_dia": f"{dia} Dia",
				"finished_colour": colour,
				"knitting_output_dia": f"{dia} Dia",
				"knitting_output_colour": knit_colour,
				"use_dyed_yarn": use_dyed_yarn,
			}
			for colour, dias, knit_colour, use_dyed_yarn, _yarn in routes
			for dia in dias
		],
		"yarns": yarns,
		"yarn_item": yarns[0]["yarn_item"],
		"knitting_process": "Knitting",
		"dyeing_process": "Dyeing",
		"compacting_process": None,
		"cloth_per_kg_yarn": 1.0,
	}


def build_lot_cloth_programs(lot):
	from essdee_yrp.api.cloth_program import build_cloth_programs

	selections = [
		get_cloth_program_selection(cloth, routes) for cloth, routes in LOT_CLOTH_PROGRAMS[lot].items()
	]
	excess = frappe.db.get_value("SD YRP Lot", lot, "cloth_excess_percentage")
	build_cloth_programs(lot, frappe.as_json(selections), excess_percentage=excess)
