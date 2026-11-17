from essdee_yrp.patches import seed_role_settings
from essdee_yrp.setup import ensure_mrp_schema_roles


def execute():
	"""Create the Folding Lot Manager role before fixtures sync and seed MRP Settings with it."""
	ensure_mrp_schema_roles()
	seed_role_settings.execute()
