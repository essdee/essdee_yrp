from unittest import TestCase

import frappe

from essdee_yrp.valuation_tree.rates import RateBuildUp

GRN = "YRP Goods Received Note"
ISSUES = {
	"I-yarn": ("Yarn", "Kg"),
	"I-cloth": ("VEST-Cloth", "Kg"),
	"I-panel": ("VEST-Panel", "Pieces"),
	"I-sticker": ("Sticker", "Nos"),
	"I-rib": ("VEST-Rib", "Kg"),
	"I-loose": ("VEST-Loose Piece-M", "Pieces"),
	"I-box": ("Box", "Nos"),
}


def node(key, kind, item, stage, voucher, qty, value, own, children=(), uom="Pieces", posting="01"):
	return {
		"id": key,
		"kind": kind,
		"item": item,
		"item_group": "M_Purchase - Yarn" if item == "Yarn" else "",
		"stage": stage,
		"voucher_type": GRN,
		"voucher_no": voucher,
		"against": "",
		"against_id": "",
		"uom": uom,
		"posting": f"2026-11-{posting} 10:00:00",
		"qty": qty,
		"value": value,
		"own": own,
		"info": {},
		"children": list(children),
	}


def edge(key, fraction, issue, link="production", via=()):
	return {"id": key, "fraction": fraction, "link": link, "issue": issue, "via": list(via)}


class FakeReader:
	def sle(self, name):
		if name == "piece":
			return frappe._dict(name=name, item="VEST-M", uom="Pieces", qty=15)
		item, uom = ISSUES[name]
		return frappe._dict(name=name, item=item, uom=uom)

	def outputs_of(self, issue):
		return ["piece"]

	def voucher(self, voucher_type, voucher_no):
		return frappe._dict()


class FakeGraph:
	"""Yarn → knitting → cutting (panels + rib) → stitching (rib absorbed at WO close) → packing per box of 5."""

	def __init__(self):
		self.reader = FakeReader()
		self.is_accessory = lambda item: item in ("Sticker", "Box")
		dc = {"voucher_type": "YRP Delivery Challan", "voucher_no": "DC-1", "from": "S", "to": "P"}
		nodes = [
			node(
				"yarn",
				"purchase",
				"Yarn",
				"Purchase",
				"GRN-Y",
				10,
				3200,
				{"material": 3000, "pi": 200},
				uom="Kg",
			),
			node(
				"sticker",
				"purchase",
				"Sticker",
				"Purchase",
				"GRN-S",
				100,
				50,
				{"accessories": 40, "pi": 10},
				uom="Nos",
			),
			node("box", "purchase", "Box", "Purchase", "GRN-B", 3, 30, {"accessories": 30}, uom="Nos"),
			node(
				"cloth",
				"production",
				"VEST-Cloth",
				"Knitting",
				"GRN-K",
				10,
				3400,
				{"process": 200},
				[edge("yarn", 1, "I-yarn")],
				"Kg",
				"02",
			),
			node(
				"panel",
				"production",
				"VEST-Panel",
				"Cutting",
				"GRN-C",
				30,
				3120,
				{"process": 60},
				[edge("cloth", 0.9, "I-cloth")],
				posting="03",
			),
			node(
				"rib",
				"production",
				"VEST-Rib",
				"Cutting",
				"GRN-C",
				1,
				342,
				{"process": 2},
				[edge("cloth", 0.1, "I-cloth")],
				"Kg",
				"03",
			),
			node(
				"piece",
				"production",
				"VEST-M",
				"Stitching",
				"GRN-ST",
				15,
				3627,
				{"process": 150},
				[
					edge("panel", 1, "I-panel"),
					edge("sticker", 0.3, "I-sticker"),
					edge("rib", 1, "I-rib", "wo_close"),
				],
				posting="04",
			),
			node(
				"pack",
				"production",
				"VEST-M",
				"Ironing and Packing",
				"GRN-P",
				15,
				3702,
				{"process": 45},
				[edge("piece", 1, "I-loose", via=[dc]), edge("box", 1, "I-box")],
				posting="05",
			),
		]
		self.nodes = {item["id"]: item for item in nodes}

	def edges_for_issue(self, sle, share, link):
		return [edge("rib", 1, sle.name, link)]


class TestRateBuildUp(TestCase):
	@classmethod
	def setUpClass(cls):
		cls.result = RateBuildUp(FakeGraph(), FakeGraph().reader, "VEST", ["pack"], pieces_per_box=5).build()
		cls.sections = {section["title"]: section for section in cls.result["sections"]}

	def row(self, section, item):
		return next(row for row in self.sections[section]["rows"] if row["item"] == item)

	def test_sections_follow_the_flow_and_skip_accessory_purchases(self):
		self.assertEqual(
			[section["title"] for section in self.result["sections"]],
			["Yarn purchase", "Knitting", "Cutting", "Stitching", "Ironing and Packing"],
		)

	def test_every_row_builds_up_to_its_rate_out(self):
		for section in self.result["sections"]:
			for row in section["rows"]:
				adds = row["process"] + row["accessories"] + row["pi"] + row["wo_close"] + row["unattributed"]
				self.assertAlmostEqual(row["rate_in"] + adds, row["rate_out"], places=9)
				self.assertAlmostEqual(
					row["purchase_rate"] + sum(line["amount"] for line in row["inputs"]),
					row["rate_in"],
					places=9,
				)
				self.assertAlmostEqual(row["qty"] * row["rate_out"], row["total"], places=9)

	def test_purchase_rate_and_pi_are_per_kg(self):
		yarn = self.row("Yarn purchase", "Yarn")
		self.assertEqual((yarn["rate_in"], yarn["pi"], yarn["rate_out"]), (300, 20, 320))
		self.assertIn("₹20.00/kg higher", self.sections["Yarn purchase"]["notes"][0])

	def test_wo_close_input_is_a_column_not_an_input(self):
		piece = self.row("Stitching", "M")
		self.assertEqual([line["item"] for line in piece["inputs"]], ["Panel"])
		self.assertAlmostEqual(piece["inputs"][0]["qty"], 2)
		self.assertAlmostEqual(piece["rate_in"], 208)
		self.assertAlmostEqual(piece["wo_close"], 342 / 15)
		self.assertAlmostEqual(piece["accessories"], 1)
		self.assertEqual(self.row("Cutting", "Rib")["to"], [{"stage": "Stitching", "wo_close": True}])
		note = " ".join(self.sections["Stitching"]["notes"])
		self.assertIn("Rib 1 kg = ₹342.00 ÷ 15 pc = ₹22.80/pc", note)

	def test_packing_is_valued_per_box_from_the_loose_piece_transfer(self):
		section = self.sections["Ironing and Packing"]
		box = section["rows"][0]
		self.assertEqual((box["qty"], box["uom_label"], box["pieces"]), (3, "box (5 pcs)", 15))
		self.assertAlmostEqual(box["rate_in"], 5 * 3627 / 15)
		self.assertAlmostEqual(box["process"], 15)
		self.assertAlmostEqual(box["accessories"], 10)
		self.assertAlmostEqual(box["rate_out"], 1234)
		self.assertAlmostEqual(box["rate_out_piece"], 1234 / 5)
		loose = box["inputs"][0]
		self.assertEqual((loose["item"], loose["voucher"], loose["qty"]), ("Loose Piece-M", "DC-1", 5))
		self.assertEqual([source["item"] for source in loose["sources"]], ["M"])
		self.assertEqual(section["accessories"][0]["per_unit"], 1)
		self.assertIn("box of 5 pieces", " ".join(section["notes"]))

	def test_root_total_equals_root_ledger_value(self):
		self.assertAlmostEqual(self.result["root_total"], 3702, places=9)
		self.assertFalse(self.result["has_unattributed"])

	def test_cutting_note_converts_kg_to_panels(self):
		self.assertIn(
			"₹340.00/kg × 0.3 kg per pc = ₹102.00 per pc", " ".join(self.sections["Cutting"]["notes"])
		)
