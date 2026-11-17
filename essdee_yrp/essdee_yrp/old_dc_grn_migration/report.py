"""dry_run_report.csv / commit_report.csv and a short Markdown summary."""

import csv
from collections import Counter
from pathlib import Path

import frappe

from essdee_yrp.essdee_yrp.old_dc_grn_migration.data import YARN_RATES


def format_date(iso):
	"""YYYY-MM-DD -> DD-MM-YYYY for every human-facing output."""
	return f"{iso[8:10]}-{iso[5:7]}-{iso[:4]}" if iso and len(iso) >= 10 else iso


def write_csv(path, results):
	doctypes = sorted({doctype for result in results for doctype in result["created"]})
	with open(path, "w", newline="") as handle:
		writer = csv.writer(handle)
		writer.writerow(
			[
				"lot",
				"status",
				"error",
				*doctypes,
				"skipped (already migrated)",
				"yarn shortfall kg",
				"process rates needed",
				"IPD approvals",
				"notes",
			]
		)
		for result in results:
			writer.writerow(
				[
					result["lot"],
					result["status"],
					result["error"],
					*[result["created"].get(doctype, 0) for doctype in doctypes],
					"; ".join(f"{k} {v}" for k, v in result["skipped"].items()),
					"; ".join(f"{item} {qty:g}" for item, qty in result["yarn_shortfall"].items()),
					"; ".join(dict.fromkeys(result["rates_needed"])),
					"; ".join(result["approvals"]),
					" | ".join(result["notes"]),
				]
			)


def get_summary(mode, results, masters, guard_summary, integrations):
	ok = [r for r in results if r["status"] == "OK"]
	totals = Counter()
	for result in ok:
		totals.update(result["created"])
	lines = [
		f"# Old DC/GRN migration: {mode}",
		"",
		f"Lots: {len(ok)} OK, {len(results) - len(ok)} failed (of {len(results)}).",
		"",
	]
	lines += (
		["## Documents per doctype (OK lots)", ""]
		+ [f"- {doctype}: {count}" for doctype, count in sorted(totals.items())]
		+ [""]
	)
	lines += (
		["## Failed lots", ""]
		+ [f"- {r['lot']}: {r['error']}" for r in results if r["status"] != "OK"]
		+ [""]
	)
	lines += (
		["## Masters", ""]
		+ [f"- sync: {line}" for line in masters["sync"]]
		+ [f"- blocking: {line}" for line in masters["blocking"]]
		+ [""]
	)
	approvals = [f"- {r['lot']}: {line}" for r in results for line in r["approvals"]]
	lines += ["## IPD approvals reverted and re-approved", ""] + (approvals or ["- none"]) + [""]
	lines += ["## Yarn shortfall (Material Receipt kg; rate from data.YARN_RATES)", ""]
	lines += [
		f"- {r['lot']} {item}: {qty:g} kg, rate {YARN_RATES.get(r['lot'], {}).get(item)}"
		for r in results
		for item, qty in sorted(r["yarn_shortfall"].items())
	] + [""]
	needed = sorted({key for r in results for key in r["rates_needed"]})
	lines += (
		["## Process rates needed (data.PROCESS_RATES)", ""]
		+ ([f"- {key}" for key in needed] or ["- none"])
		+ [""]
	)
	lines += ["## Integrations neutralised", ""] + [f"- {line}" for line in integrations] + [""]
	lines += ["## Guard", ""] + [f"- {key}: {value}" for key, value in guard_summary.items()] + [""]
	return "\n".join(lines)


def write_reports(mode, results, masters, guard_summary, integrations):
	"""Write <site>/private/old_dc_grn_migration/<mode>_<timestamp>_report.csv and _summary.md."""
	folder = Path(frappe.get_site_path("private", "old_dc_grn_migration"))
	folder.mkdir(parents=True, exist_ok=True)
	stem = f"{mode.replace('-', '_')}_{frappe.utils.now_datetime():%Y%m%d_%H%M%S}"
	write_csv(folder / f"{stem}_report.csv", results)
	summary = get_summary(mode, results, masters, guard_summary, integrations)
	(folder / f"{stem}_summary.md").write_text(summary)
	return folder / f"{stem}_report.csv", summary
