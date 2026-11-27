from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp import work_order_cloth_print
from essdee_yrp.print_helpers import prepare_print_document
from essdee_yrp.work_order_cloth_print import (
	ClothRowResolver,
	build_cloth_tables,
	get_work_order_cloth_program,
	is_cloth_work_order,
)

FORMATS = ("Essdee Work Order Deliverables", "Essdee Work Order Receivables")


def entry(dia, colour, qty, fabric_type="Main Fabric", item="Cloth", uom="Kg", secondary=None):
	secondary_qty, secondary_uom = secondary or (0, "")
	return {
		"item": item,
		"uom": uom,
		"fabric_type": fabric_type,
		"dia": dia,
		"colour": colour,
		"qty": qty,
		"secondary_qty": secondary_qty,
		"secondary_uom": secondary_uom,
	}


def table_total(tables):
	return flt(sum(table["total"] for table in tables), 3)


def resolver(fabric_types, variants):
	row_resolver = ClothRowResolver(fabric_types)
	row_resolver.variants.update(variants)
	return row_resolver


class TestBuildClothTables(IntegrationTestCase):
	def test_dias_ascend_with_main_fabric_before_folding(self):
		tables = build_cloth_tables(
			[
				entry("32 Dia", "Navy", 5),
				entry("20 Dia", "Navy", 2, "Folding Fabric"),
				entry("8 Dia", "Black", 1),
				entry("26 Dia", "Black", 3),
			]
		)
		self.assertEqual(len(tables), 1)
		groups = tables[0]["fabric_groups"]
		self.assertEqual([group["fabric_type"] for group in groups], ["Main Fabric", "Folding Fabric"])
		self.assertEqual([route["dia"] for route in groups[0]["routes"]], ["8 Dia", "26 Dia", "32 Dia"])
		self.assertEqual(tables[0]["colours"], ["Black", "Navy"])

	def test_totals_per_colour_fabric_type_and_table(self):
		table = build_cloth_tables(
			[
				entry("26 Dia", "Black", 3),
				entry("26 Dia", "Black", 1.5),
				entry("32 Dia", "Navy", 5),
				entry("20 Dia", "Navy", 2, "Folding Fabric"),
			]
		)[0]
		main, folding = table["fabric_groups"]
		self.assertEqual(main["routes"][0]["quantities"], {"Black": 4.5, "Navy": 0})
		self.assertEqual(main["routes"][0]["total"], 4.5)
		self.assertEqual(main["colour_totals"], {"Black": 4.5, "Navy": 5})
		self.assertEqual(main["total"], 9.5)
		self.assertEqual(folding["colour_totals"], {"Black": 0, "Navy": 2})
		self.assertEqual(table["colour_totals"], {"Black": 4.5, "Navy": 7})
		self.assertEqual(table["total"], 11.5)
		self.assertTrue(table["has_fabric_type"])

	def test_items_and_uoms_print_as_separate_tables(self):
		tables = build_cloth_tables(
			[
				entry("", "Greige", 10, "", item="Yarn"),
				entry("26 Dia", "Greige", 4),
				entry("26 Dia", "Greige", 1, uom="Roll"),
			]
		)
		self.assertEqual(
			[(table["item"], table["uom"]) for table in tables],
			[("Yarn", "Kg"), ("Cloth", "Kg"), ("Cloth", "Roll")],
		)
		self.assertFalse(tables[0]["has_fabric_type"])


class TestClothSecondaryQuantities(IntegrationTestCase):
	def test_secondary_qty_sums_per_colour_cell_and_totals(self):
		table = build_cloth_tables(
			[
				entry("26 Dia", "Black", 3, secondary=(2, "Roll")),
				entry("26 Dia", "Black", 1.5, secondary=(1, "Roll")),
				entry("32 Dia", "Navy", 5),
			]
		)[0]
		routes = table["fabric_groups"][0]["routes"]
		self.assertTrue(table["has_secondary"])
		self.assertEqual(routes[0]["secondary"], {"Black": {"Roll": 3}, "Navy": {}})
		self.assertEqual(routes[0]["secondary_total"], {"Roll": 3})
		self.assertEqual(routes[1]["secondary"], {"Black": {}, "Navy": {}})
		self.assertEqual(table["colour_secondary"], {"Black": {"Roll": 3}, "Navy": {}})
		self.assertEqual(table["secondary_total"], {"Roll": 3})

	def test_blank_secondary_qty_keeps_primary_only(self):
		table = build_cloth_tables([entry("26 Dia", "Black", 3)])[0]
		self.assertFalse(table["has_secondary"])
		self.assertEqual(table["secondary_total"], {})

	def test_entries_carry_row_secondary_qty(self):
		row_resolver = resolver({}, {"Cloth-26-Navy": ("Cloth", "26 Dia", "Navy")})
		entries = row_resolver.get_entries(
			[
				frappe._dict(
					item_variant="Cloth-26-Navy", qty=4, uom="Kg", secondary_qty=6, secondary_uom="Roll"
				)
			]
		)
		self.assertEqual([(row["secondary_qty"], row["secondary_uom"]) for row in entries], [(6, "Roll")])


class TestClothRowResolver(IntegrationTestCase):
	fabric_types = {
		("Cloth", "26 Dia", "Navy"): {"Folding Fabric": {"weight": 0}},
		("Cloth", "32 Dia", "Navy"): {"Main Fabric": {"weight": 10}},
		("Cloth", "30 Dia", "Black"): {"Main Fabric": {"weight": 30}, "Folding Fabric": {"weight": 10}},
	}
	variants = {
		"Cloth-26-Greige": ("Cloth", "26 Dia", "Greige"),
		"Cloth-26-Navy": ("Cloth", "26 Dia", "Navy"),
		"Cloth-32-Navy": ("Cloth", "32 Dia", "Navy"),
		"Cloth-30-Black": ("Cloth", "30 Dia", "Black"),
		"Cloth-22-Greige": ("Cloth", "22 Dia", "Greige"),
		"Yarn-Greige": ("Yarn", "", "Greige"),
	}

	def entries(self, row):
		return resolver(self.fabric_types, self.variants).get_entries([frappe._dict(row)])

	def test_greige_row_takes_the_fabric_type_of_its_reference_routes(self):
		entries = self.entries(
			{
				"item_variant": "Cloth-26-Greige",
				"qty": 4,
				"uom": "Kg",
				"fabric_reference_allocations": '{"Cloth-26-Navy": 1, "Cloth-32-Navy": 3}',
			}
		)
		self.assertEqual(
			[(row["fabric_type"], row["dia"], row["colour"], row["qty"]) for row in entries],
			[("Folding Fabric", "26 Dia", "Greige", 1), ("Main Fabric", "26 Dia", "Greige", 3)],
		)

	def test_route_with_several_fabric_types_splits_pro_rata(self):
		entries = self.entries({"item_variant": "Cloth-30-Black", "qty": 8, "uom": "Kg"})
		self.assertEqual(
			{row["fabric_type"]: row["qty"] for row in entries}, {"Main Fabric": 6, "Folding Fabric": 2}
		)

	def test_unreferenced_greige_dia_uses_the_dia_fabric_type(self):
		entries = self.entries({"item_variant": "Cloth-26-Greige", "qty": 2, "uom": "Kg"})
		self.assertEqual([row["fabric_type"] for row in entries], ["Folding Fabric"])

	def test_unknown_route_is_main_fabric_and_yarn_has_none(self):
		self.assertEqual(
			self.entries({"item_variant": "Cloth-22-Greige", "qty": 2})[0]["fabric_type"], "Main Fabric"
		)
		yarn = self.entries({"item_variant": "Yarn-Greige", "qty": 9, "uom": "Kg"})
		self.assertEqual([(row["fabric_type"], row["dia"], row["qty"]) for row in yarn], [("", "", 9)])


class TestWorkOrderClothPrint(IntegrationTestCase):
	def work_order(self, is_cloth_process):
		name = frappe.db.sql(
			"""select wo.name from `tabYRP Work Order` wo
			join `tabYRP Process` process on process.name = wo.process_name
			where wo.docstatus = 1 and process.is_cloth_process = %s
				and exists (select 1 from `tabYRP Work Order Deliverables` d where d.parent = wo.name)
				and exists (select 1 from `tabYRP Work Order Receivables` r where r.parent = wo.name)
			order by wo.modified desc limit 1""",
			is_cloth_process,
		)
		if not name:
			self.skipTest("Needs submitted cloth and non-cloth Work Orders")
		doc = frappe.get_doc("YRP Work Order", name[0][0])
		prepare_print_document(doc)
		return doc

	def test_cloth_tables_keep_every_row_quantity(self):
		doc = self.work_order(1)
		self.assertTrue(is_cloth_work_order(doc))
		for table in ("deliverables", "receivables"):
			with self.subTest(table=table):
				program = get_work_order_cloth_program(doc, table)
				self.assertAlmostEqual(
					table_total(program["tables"]), sum(flt(row.qty) for row in doc.get(table)), 3
				)

	def test_correction_rows_print_in_their_own_tables(self):
		doc = self.work_order(1)
		correction = frappe._dict(doc.receivables[0].as_dict(), qty=7, parent="WOC-TEST")
		with patch.object(
			work_order_cloth_print, "get_work_order_correction_rows", return_value=[correction]
		):
			program = get_work_order_cloth_program(doc, "receivables")
			html = frappe.get_print("YRP Work Order", doc.name, FORMATS[1], no_letterhead=1)
		self.assertAlmostEqual(
			table_total(program["tables"]), sum(flt(row.qty) for row in doc.receivables), 3
		)
		self.assertEqual(table_total(program["correction_tables"]), 7)
		self.assertNotIn("Correction", html)
		self.assertNotIn("WOC-TEST", html)
		self.assertEqual(html.count('class="wo-cloth-program"'), 2)

	def test_cloth_work_order_prints_the_cloth_program_layout(self):
		doc = self.work_order(1)
		for print_format in FORMATS:
			with self.subTest(print_format=print_format):
				html = frappe.get_print("YRP Work Order", doc.name, print_format, no_letterhead=1)
				self.assertIn('class="wo-cloth-program"', html)
				self.assertNotIn("S.No.", html)

	def test_cloth_print_shows_primary_and_secondary_qty_in_colour_cells(self):
		doc = self.work_order(1)
		row = doc.receivables[0]
		row.secondary_qty, row.secondary_uom = 45, "Roll"
		html = frappe.get_print("YRP Work Order", doc.name, FORMATS[1], doc=doc, no_letterhead=1)
		self.assertIn('class="wo-cloth-secondary"', html)
		self.assertIn("45 Roll", html)
		self.assertIn(f"{row.uom}</span>", html)

	def test_cloth_print_without_secondary_qty_shows_primary_only(self):
		doc = self.work_order(1)
		for row in doc.receivables:
			row.secondary_qty = 0
		html = frappe.get_print("YRP Work Order", doc.name, FORMATS[1], doc=doc, no_letterhead=1)
		self.assertNotIn('class="wo-cloth-secondary"', html)

	def test_non_cloth_work_order_keeps_the_challan_layout(self):
		doc = self.work_order(0)
		self.assertFalse(is_cloth_work_order(doc))
		for print_format in FORMATS:
			with self.subTest(print_format=print_format):
				html = frappe.get_print("YRP Work Order", doc.name, print_format, no_letterhead=1)
				self.assertIn("S.No.", html)
				self.assertNotIn("wo-cloth-program", html)
