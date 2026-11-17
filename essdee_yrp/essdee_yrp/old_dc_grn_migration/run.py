"""Entry point for `bench --site <site> execute essdee_yrp.essdee_yrp.old_dc_grn_migration.run.execute`."""

import traceback
from dataclasses import dataclass

import frappe

from essdee_yrp.essdee_yrp.old_dc_grn_migration.data import LOTS
from essdee_yrp.essdee_yrp.old_dc_grn_migration.guard import INTEGRATIONS, RunGuard
from essdee_yrp.essdee_yrp.old_dc_grn_migration.lot_migrator import LotMigrator
from essdee_yrp.essdee_yrp.old_dc_grn_migration.masters import MasterCheck, apply_sync
from essdee_yrp.essdee_yrp.old_dc_grn_migration.plan import PlanError, build_lot_plan_from_snapshot
from essdee_yrp.essdee_yrp.old_dc_grn_migration.report import write_reports


@dataclass
class LotInput:
	lot: str
	yarn_colour_map: dict
	plan: object = None
	plan_error: str = ""


def get_lot_inputs(lots):
	inputs = []
	for data in LOTS:
		if lots and data["lot"] not in lots:
			continue
		item = LotInput(data["lot"], data["yarn_colour_map"])
		try:
			item.plan = build_lot_plan_from_snapshot(data)
		except PlanError as error:
			item.plan_error = f"PlanError: {error}"
		inputs.append(item)
	return inputs


def execute(commit=False, sync_masters=False, allow_zero_rate=False, lots=None, placeholder_rates=False):
	"""Dry run by default (everything rolled back). commit=True writes one lot per transaction.

	allow_zero_rate: yarn Material Receipts at rate 0 when YARN_RATES has none.
	placeholder_rates (dry run only): Process Costs at rate 1 when PROCESS_RATES has none, to test the rest.

	sync_masters=True only creates the masters this site lacks (prod lacks the Sri Pavai Knits Warehouse).
	lots: list or comma-separated string of lot names; default all lots in data.LOTS.
	"""
	commit, sync_masters, allow_zero_rate = bool(commit), bool(sync_masters), bool(allow_zero_rate)
	if commit and placeholder_rates:
		frappe.throw("placeholder_rates is only allowed in a dry run")
	lots = set(lots.split(",") if isinstance(lots, str) else lots or [])
	frappe.set_user("Administrator")
	frappe.db.rollback()
	selected = [data for data in LOTS if not lots or data["lot"] in lots]
	check = MasterCheck(selected).run()
	if sync_masters:
		return run_sync_masters(check, commit)
	if check.sync and commit:
		frappe.throw("Masters are missing; run with sync_masters first:<br>" + "<br>".join(check.describe()))
	masters = {"sync": check.describe(), "blocking": check.blocking}
	results = []
	try:
		with RunGuard(dry_run=not commit) as guard:
			if check.sync:
				apply_sync(check.sync)
				masters["sync"] = [
					f"{line} (applied inside the dry-run transaction only)" for line in masters["sync"]
				]
			for index, item in enumerate(get_lot_inputs(lots)):
				results.append(migrate_lot(item, commit, allow_zero_rate, index, placeholder_rates))
	finally:
		if not commit:
			frappe.db.rollback()
	mode = "commit" if commit else ("dry-run-placeholder-rates" if placeholder_rates else "dry-run")
	path, summary = write_reports(mode, results, masters, guard.get_summary(), INTEGRATIONS)
	print(summary)
	print(f"Report: {path}")
	return str(path)


def run_sync_masters(check, commit):
	print("Masters to recreate:", *(check.describe() or ["none"]), sep="\n- ")
	print("Blocking:", *(check.blocking or ["none"]), sep="\n- ")
	try:
		with RunGuard(dry_run=not commit):
			apply_sync(check.sync)
	finally:
		if not commit:
			frappe.db.rollback()
	if commit:
		frappe.db.commit()  # nosemgrep: explicit commit=True
		print("Masters committed.")
	else:
		print("Dry run: rolled back. Run with sync_masters and commit to keep them.")
	return check.describe()


def migrate_lot(item, commit, allow_zero_rate, index, placeholder_rates=False):
	result = {
		"lot": item.lot,
		"status": "FAILED",
		"error": item.plan_error,
		"created": {},
		"skipped": {},
		"yarn_shortfall": {},
		"rates_needed": [],
		"approvals": [],
		"notes": [],
	}
	if item.plan_error:
		print(f"FAILED {item.lot}: {item.plan_error}")
		return result
	savepoint = f"old_dc_grn_lot_{index}"
	frappe.db.savepoint(savepoint)
	migrator = LotMigrator(item, allow_zero_rate, placeholder_rates)
	try:
		migrator.run()
	except Exception as error:
		frappe.db.rollback(save_point=savepoint)
		result.update(
			approvals=[f"{line} (rolled back with the lot)" for line in migrator.approvals],
			error=f"{type(error).__name__}: {error}"[:1000],
			notes=migrator.notes,
			yarn_shortfall=migrator.yarn_shortfall,
			rates_needed=migrator.rates_needed,
		)
		print(f"FAILED {item.lot}: {result['error']}\n{traceback.format_exc()[-1500:]}")
		return result
	if commit:
		frappe.db.commit()  # nosemgrep: one lot per transaction
	result.update(
		status="OK",
		error="",
		created=dict(migrator.created),
		skipped=dict(migrator.skipped),
		yarn_shortfall=migrator.yarn_shortfall,
		rates_needed=migrator.rates_needed,
		approvals=migrator.approvals,
		notes=migrator.notes,
	)
	print(f"OK {item.lot}: {dict(migrator.created)}")
	return result
