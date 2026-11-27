from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_item_master import sd_yrp_fg_item_master

MODULE = "essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_item_master.sd_yrp_fg_item_master"


class TestSDYRPFGItemMaster(FrappeTestCase):
	def test_new_item_has_hsn_before_insert(self):
		fg_item = frappe._dict(name1="_Test FG", brand=None, template="Single Item", hsn="61091000")
		template = MagicMock(uom_conversion_details=[], attributes=[], additional_parameters=[])
		item = MagicMock()
		hsn_at_insert = []
		item.insert.side_effect = lambda: hsn_at_insert.append(item.gst_hsn_code)
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=template),
			patch(f"{MODULE}.frappe.new_doc", return_value=item),
		):
			sd_yrp_fg_item_master.create_item(fg_item)
		self.assertEqual(hsn_at_insert, ["61091000"])
