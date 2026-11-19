import frappe

from essdee_yrp.accounts import web_capabilities as accounts
from essdee_yrp.cut_panel_store import web_workspace as cut_panel_store
from essdee_yrp.cutting import reports as cutting_reports
from essdee_yrp.cutting import web_capabilities as cutting
from essdee_yrp.fabric_store import web_workspace as fabric_store
from essdee_yrp.finishing import web_workspace as finishing
from essdee_yrp.hr import web_workspace as hr
from essdee_yrp.merch import web_workspace as merch
from essdee_yrp.merch_pd import web_workspace as merch_pd
from essdee_yrp.merch_purchase import web_workspace as merch_purchase
from essdee_yrp.planning import web_workspace as planning
from essdee_yrp.product_development import web_workspace as product_development
from essdee_yrp.purchase import web_capabilities as purchase
from essdee_yrp.quality import web_workspace as quality
from essdee_yrp.sales import web_workspace as sales
from essdee_yrp.sewing import web_workspace as sewing
from essdee_yrp.web_common import report_access_scope

CAPABILITY_SOURCES = {
	"cutting": cutting.get_capabilities,
	"cutting_reports": cutting_reports.get_report_permissions,
	"fabric_store": fabric_store.get_capabilities,
	"cut_panel_store": cut_panel_store.get_capabilities,
	"sewing": sewing.get_capabilities,
	"finishing": finishing.get_capabilities,
	"quality": quality.get_capabilities,
	"merch": merch.get_capabilities,
	"purchase": purchase.get_capabilities,
	"merch_purchase": merch_purchase.get_capabilities,
	"merch_pd": merch_pd.get_capabilities,
	"sales": sales.get_capabilities,
	"planning": planning.get_capabilities,
	"pd": product_development.get_capabilities,
	"accounts": accounts.get_capabilities,
	"hr": hr.get_capabilities,
}


@frappe.whitelist()
@report_access_scope()
def get_department_capabilities() -> dict:
	"""Every department's /web capability payload in one call, for the cross-department card search."""
	return {key: get_capabilities() for key, get_capabilities in CAPABILITY_SOURCES.items()}
