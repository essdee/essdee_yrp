"""Neutralise outside-system side effects for the run and keep a dry run inside one transaction."""

import traceback
from unittest import mock

import frappe
import frappe.realtime
import frappe.utils.background_jobs as background_jobs
import requests
from frappe.database.database import IMPLICIT_COMMIT_QUERY_TYPES

BLOCKED_QUERY_TYPES = IMPLICIT_COMMIT_QUERY_TYPES | {"commit"}
# Background jobs that reach outside systems; in a commit run every other (local) job, such as stock reposting, still queues.
EXTERNAL_JOB_MARKERS = (
	"telegram",
	"revert_alert",
	"gstin",
	"spine",
	"kafka",
	"sms",
	"whatsapp",
	"notification",
	"email",
	"fcm",
	"essdee_yrp.erp",
)
INTEGRATIONS = [
	"india_compliance GSTIN lookup (live GST API over HTTP): fires only on Supplier/Address save, which this migration does only when a masters.SUPPLIERS supplier is missing (not on prod); outbound requests HTTP is blocked in-process",
	"spine Kafka events (Supplier/Address): no kafka config on this site; outbound HTTP blocked and enqueue intercepted",
	"essdee_yrp Telegram approvals ('*' on_update): only a Purchase Order route is enabled; enqueue intercepted",
	"Notifications / SMS / email: frappe.flags.mute_emails, no enabled Notification for these doctypes",
	"Webhooks / Server Scripts: none on this site for these doctypes",
	"Background jobs: none queued in a dry run; in a commit run jobs naming telegram/gstin/spine/sms/whatsapp/notification/email/fcm/erp are dropped, local ones (stock repost) queue",
	"Realtime (socket.io) events: intercepted, never sent",
	"yrp partner sync ('*' on_update): frappe.flags.defer_partner_generation",
	"Item search index and sqlite search index (not rolled back): reindex calls patched to no-ops",
]


class GuardViolation(Exception):
	"""Something tried to leave the transaction or reach an outside system."""


class RunGuard:
	"""Blocks HTTP, background jobs, realtime and email for the whole run; in a dry run also blocks commits."""

	def __init__(self, dry_run):
		self.dry_run = dry_run
		self.jobs, self.realtime, self.http, self.commits = [], [], [], []
		self.patches = []

	def __enter__(self):
		self.enqueue = background_jobs.enqueue
		self.flags = {key: frappe.flags.get(key) for key in ("mute_emails", "defer_partner_generation")}
		frappe.flags.mute_emails = True
		frappe.flags.defer_partner_generation = True
		self.patches = [
			mock.patch.object(background_jobs, "enqueue", self.record_job),
			mock.patch.object(frappe, "enqueue", self.record_job),
			mock.patch.object(frappe.realtime, "emit_via_redis", self.record_realtime),
			mock.patch.object(requests.Session, "request", self.block_http),
			mock.patch("erpnext.stock.doctype.item.item_search.reindex_item", lambda *args, **kwargs: None),
			mock.patch("frappe.search.sqlite_search.update_doc_index", lambda *args, **kwargs: None),
		]
		db = frappe.local.db
		self.patches.append(mock.patch.object(db, "rollback", self.get_guarded_rollback(db.rollback)))
		if self.dry_run:
			self.patches += [
				mock.patch.object(db, "commit", self.skip_commit),
				mock.patch.object(db, "check_implicit_commit", self.block_query),
			]
		for patch in self.patches:
			patch.start()
		return self

	def __exit__(self, *exc_info):
		for patch in reversed(self.patches):
			patch.stop()
		frappe.flags.update(self.flags)
		return False

	def record_job(self, method, *args, **kwargs):
		"""Dry run: queue nothing. Commit run: drop jobs that reach outside systems, queue local ones."""
		name = method if isinstance(method, str) else f"{method.__module__}.{method.__qualname__}"
		if self.dry_run or any(marker in name.lower() for marker in EXTERNAL_JOB_MARKERS):
			self.jobs.append(name)
			return None
		return self.enqueue(method, *args, **kwargs)

	def record_realtime(self, event, message, room):
		self.realtime.append(event)

	def block_http(self, session, method, url, *args, **kwargs):
		self.http.append(f"{method} {url}")
		raise GuardViolation(f"Outbound HTTP blocked during migration: {method} {url}")

	@staticmethod
	def get_guarded_rollback(rollback):
		"""Savepoint rollbacks pass; a full rollback from app code would drop the run's other lots."""

		def guarded_rollback(*, save_point=None, chain=False):
			if save_point:
				return rollback(save_point=save_point)
			raise GuardViolation(f"Full rollback requested by {get_caller()}")

		return guarded_rollback

	def skip_commit(self, *args, **kwargs):
		self.commits.append(get_caller())

	def block_query(self, query, query_type):
		if query_type in BLOCKED_QUERY_TYPES:
			raise GuardViolation(f"Dry run blocked a {query_type} statement: {query[:120]}")

	def get_summary(self):
		return {
			"background jobs intercepted": len(self.jobs),
			"realtime events intercepted": len(self.realtime),
			"HTTP calls blocked": self.http,
			"commit calls skipped (dry run)": len(self.commits),
		}


def get_caller():
	for frame in reversed(traceback.extract_stack()[:-2]):
		if "/migration/" not in frame.filename and "/frappe/database/" not in frame.filename:
			return f"{frame.filename.split('/apps/')[-1]}:{frame.lineno} {frame.name}"
	return "unknown"
