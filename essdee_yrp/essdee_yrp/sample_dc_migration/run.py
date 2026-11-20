"""Entry point: `bench --site <site> execute essdee_yrp.essdee_yrp.sample_dc_migration.run.execute`."""

import csv
import traceback
from pathlib import Path

import frappe

from essdee_yrp.essdee_yrp.old_dc_grn_migration.guard import INTEGRATIONS, RunGuard

from .data import DOCUMENTS, LOT, PROCESS_RATES, RATE_SOURCES
from .documents import DocumentMigrator


def check_lot():
	if not frappe.db.get_value("SD YRP Lot", LOT, "is_folding_lot"):
		frappe.throw(f"Lot {LOT} must exist with Folding Lot set")


def execute(commit=False, dcs=None):
	"""Dry run by default (everything rolled back); commit=True writes one old DC per transaction.

	dcs: list or comma-separated string of old DC numbers; default all of data.DOCUMENTS.
	"""
	commit = bool(commit)
	selected = set(dcs.split(",") if isinstance(dcs, str) else dcs or [])
	frappe.set_user("Administrator")
	frappe.db.rollback()
	check_lot()
	results = []
	try:
		with RunGuard(dry_run=not commit) as guard:
			for index, document in enumerate(DOCUMENTS):
				if not selected or document["number"] in selected:
					results.append(migrate(document, commit, index))
	finally:
		if not commit:
			frappe.db.rollback()
	path, summary = write_reports("commit" if commit else "dry_run", results, guard.get_summary())
	print(summary)
	print(f"Report: {path}")
	return str(path)


def migrate(document, commit, index):
	result = {"dc": document["number"], "status": "FAILED", "error": "", "created": {}, "skipped": {}}
	savepoint = f"sample_dc_{index}"
	frappe.db.savepoint(savepoint)
	migrator = DocumentMigrator(document)
	try:
		migrator.run()
	except Exception as error:
		frappe.db.rollback(save_point=savepoint)
		result["error"] = f"{type(error).__name__}: {error}"[:1000]
		print(f"FAILED {document['number']}: {result['error']}\n{traceback.format_exc()[-1500:]}")
		return result
	if commit:
		frappe.db.commit()  # nosemgrep: one old DC per transaction
	result.update(status="OK", created=migrator.created, skipped=migrator.skipped)
	print(f"OK {document['number']}: {migrator.created} skipped {migrator.skipped}")
	return result


def format_names(names_by_doctype):
	return "; ".join(f"{doctype}: {', '.join(names)}" for doctype, names in names_by_doctype.items())


def get_summary(mode, results, guard_summary):
	ok = sum(result["status"] == "OK" for result in results)
	lines = [f"# Sample lot migration: {mode}", "", f"Old DCs: {ok} OK, {len(results) - ok} failed.", ""]
	for result in results:
		lines.append(f"- {result['dc']} {result['status']} {result['error']}")
		lines += [f"  - created {format_names(result['created'])}"] if result["created"] else []
		lines += [f"  - skipped {format_names(result['skipped'])}"] if result["skipped"] else []
	lines += ["", "## Material Receipt rates", ""]
	lines += [f"- {item}: {rate:g} ({source})" for item, (rate, source) in RATE_SOURCES.items()]
	lines += ["", "## Process rates", ""] + [f"- {k}: {v:g}" for k, v in PROCESS_RATES.items()]
	lines += ["", "## Integrations neutralised", ""] + [f"- {line}" for line in INTEGRATIONS]
	lines += ["", "## Guard", ""] + [f"- {key}: {value}" for key, value in guard_summary.items()]
	return "\n".join(lines) + "\n"


def write_reports(mode, results, guard_summary):
	"""Write <site>/private/sample_dc_migration/<mode>_<timestamp>_report.csv and _summary.md."""
	folder = Path(frappe.get_site_path("private", "sample_dc_migration"))
	folder.mkdir(parents=True, exist_ok=True)
	stem = f"{mode}_{frappe.utils.now_datetime():%Y%m%d_%H%M%S}"
	with open(folder / f"{stem}_report.csv", "w", newline="") as handle:
		writer = csv.writer(handle)
		writer.writerow(["old dc", "status", "error", "created", "skipped (already migrated)"])
		for result in results:
			writer.writerow(
				[
					result["dc"],
					result["status"],
					result["error"],
					format_names(result["created"]),
					format_names(result["skipped"]),
				]
			)
	summary = get_summary(mode, results, guard_summary)
	(folder / f"{stem}_summary.md").write_text(summary)
	return folder / f"{stem}_report.csv", summary
