"""Migrate one lot: cloth programs, process chain, Knitting WOs, yarn, then DCs and GRNs stage by stage in date order."""

from collections import Counter
from dataclasses import replace

import frappe

from essdee_yrp.essdee_yrp.old_dc_grn_migration import cloth, documents, process_cost, yarn
from essdee_yrp.essdee_yrp.old_dc_grn_migration.data import GREIGE_COLOUR
from essdee_yrp.essdee_yrp.old_dc_grn_migration.documents import (
	MigrationError,
	WorkOrderBuilder,
	find_tagged,
	get_receipt_comments,
	get_tag,
)
from essdee_yrp.essdee_yrp.old_dc_grn_migration.plan import COLOUR_STEPS, KNITTING, get_effective_dates
from essdee_yrp.essdee_yrp.old_dc_grn_migration.report import format_date

DAY_START_SECONDS = 23 * 3600
REUSE_TOLERANCE = 0.02


class LotMigrator:
	"""Creates (or finds, by tag) every document for one lot; counts what it created per doctype."""

	def __init__(self, item, allow_zero_rate, placeholder_rates=False):
		self.item = item
		self.placeholder_rates = placeholder_rates
		self.plan = item.plan
		self.allow_zero_rate = allow_zero_rate
		self.created = Counter()
		self.skipped = Counter()
		self.notes = []
		self.approvals = []
		self.yarn_shortfall = {}
		self.rates_needed = []
		self.work_orders = {}
		self.delivery_challans = {}
		self.reused = set()
		self.excess_yarn = {}
		self.knit_routes = {}
		self.dia_remaps = {}
		self.sequence = 0
		self.dates = get_effective_dates(self.plan)

	def run(self):
		lot_doc = frappe.get_doc("SD YRP Lot", self.plan.lot)
		change, approval_log = cloth.ensure_accessory_dias(lot_doc)
		self.approvals += approval_log
		if change:
			self.notes.append(change)
			self.count("Accessory Dia changed (YRP Item Production Detail)")
		built = cloth.ensure_cloth_programs(lot_doc, self.plan, self.item.yarn_colour_map, GREIGE_COLOUR)
		self.count("Cloth program built (YRP Item Production Detail)", len(built))
		lot_doc.reload()
		self.fabric_rows = cloth.get_fabric_rows(lot_doc)
		self.ensure_chains()
		knitting = [plan for plan in self.plan.work_orders if plan.process == KNITTING]
		names = [self.ensure_work_order(plan) for plan in knitting]
		self.ensure_yarn(knitting, [name for name in dict.fromkeys(names) if name not in self.reused])
		self.dates = get_effective_dates(self.plan, self.get_yarn_ready_dates(knitting))
		for _stage, _date, _kind, plan, grn in self.get_events():
			step = f"{plan.process} {grn.number if grn else plan.dc.number} ({plan.supplier}, {plan.cloth})"
			try:
				if grn is None:
					self.ensure_delivery(plan)
				else:
					self.ensure_receipt(plan, grn)
			except MigrationError:
				raise
			except Exception as error:
				raise MigrationError(f"{step}: {type(error).__name__}: {error}") from error
		return self

	def count(self, doctype, number=1):
		if number:
			self.created[doctype] += number

	def next_time(self):
		self.sequence += 1
		seconds = DAY_START_SECONDS + self.sequence
		return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"

	def get_dc_date(self, plan):
		date = self.dates[("DC", plan.dc.number, plan.cloth)]
		if date != plan.dc.date:
			self.notes.append(
				f"{plan.dc.number} posted on {format_date(date)} (old date {format_date(plan.dc.date)}): "
				"its source fabric was received later"
			)
		return date

	def ensure_chains(self):
		for cloth_item in dict.fromkeys(plan.cloth for plan in self.plan.work_orders):
			row = self.fabric_rows.get(cloth_item)
			if not row:
				raise MigrationError(
					f"cloth {cloth_item} has no Lot fabric row / cloth IPD after Build Cloth Program"
				)
			processes = self.plan.get_stages(cloth_item)
			colour_process = COLOUR_STEPS.get(self.plan.lot, {}).get("process")
			changes, approval_log = cloth.ensure_process_chain(
				row.production_detail, processes, colour_process
			)
			self.approvals += approval_log
			if changes:
				self.notes.append(f"{row.production_detail}: Fabric Processes {', '.join(changes)}")
				self.count("Fabric Processes steps added (YRP Item Production Detail)")
			self.set_cloth_processes(cloth_item, row.production_detail, processes)

	def set_cloth_processes(self, cloth_item, ipd, processes):
		"""The cloth's stages follow its IPD's Fabric Processes order."""
		chain = cloth.get_process_chain(ipd)
		ordered = [process for process in chain if process in processes]
		if set(ordered) != set(processes):
			raise MigrationError(
				f"{ipd}: Fabric Processes {chain} lack {sorted(set(processes) - set(ordered))}"
			)
		if ordered != processes:
			self.notes.append(
				f"{ipd}: process order {ordered} from its Fabric Processes (lot order {processes})"
			)
		self.plan.cloth_processes[cloth_item] = ordered

	def get_events(self):
		"""Chain stage first, then posting date; a DC goes before the GRNs posted on the same day."""
		events = []
		for plan in self.plan.work_orders:
			stage = self.plan.get_stages(plan.cloth).index(plan.process)
			events.append((stage, self.dates[("DC", plan.dc.number, plan.cloth)], 0, plan, None))
			events += [
				(stage, self.dates[("GRN", grn.number, plan.dc.number, plan.cloth)], 1, plan, grn)
				for grn in plan.grns
			]
		return sorted(events, key=lambda event: (event[0], event[1], event[2], event[3].dc.number))

	def get_key(self, plan):
		return (plan.dc.number, plan.cloth)

	def find_existing_knitting(self, plan):
		"""A real (not migrated) submitted Knitting WO of the lot for the same supplier and cloth, with the
		old DC's quantity (within 2%), is the same job; each one is reused for one old DC only."""
		rows = frappe.get_all(
			"YRP Work Order",
			filters={
				"lot": self.plan.lot,
				"process_name": KNITTING,
				"supplier": plan.supplier,
				"item": plan.cloth,
				"docstatus": 1,
			},
			fields=["name", "comments", "total_quantity"],
			order_by="creation",
		)
		for row in rows:
			if (row.comments or "").startswith(get_tag("")) or row.name in self.reused:
				continue
			if abs((row.total_quantity or 0) - plan.kg) <= plan.kg * REUSE_TOLERANCE:
				return row.name
		return None

	def ensure_work_order(self, plan):
		"""Return the WO name: an earlier migrated one, a reused real Knitting WO, or a new one."""
		key = self.get_key(plan)
		tag = get_tag(plan.dc.number, plan.cloth)
		name = find_tagged(
			"YRP Work Order", {"lot": self.plan.lot, "process_name": plan.process, "comments": tag}
		)
		if name:
			self.skipped["YRP Work Order"] += 1
		elif plan.process == KNITTING and (name := self.find_existing_knitting(plan)):
			self.notes.append(
				f"{plan.dc.number}: reused existing Knitting WO {name} (yarn already delivered in yrp)"
			)
			self.reused.add(name)
			self.delivery_challans[key] = frappe.db.get_value(
				"YRP Delivery Challan", {"work_order": name, "docstatus": 1}, "name"
			)
		else:
			name = self.create_work_order(plan)
		self.work_orders[key] = name
		return name

	def create_work_order(self, plan):
		builder = WorkOrderBuilder(self.plan.lot, plan, self.fabric_rows[plan.cloth], GREIGE_COLOUR)
		doc = builder.insert_draft(self.get_dc_date(plan))
		source = builder.calculate(doc)
		self.notes += builder.notes
		self.knit_routes[doc.name] = builder.knit_routes
		doc.reload()
		try:
			cost, missing = process_cost.ensure_process_cost(doc, self.placeholder_rates)
		except process_cost.ProcessRateMissing as error:
			self.rates_needed += error.needed
			raise
		self.rates_needed += missing
		if cost:
			self.count("YRP Process Cost")
			self.notes.append(f"Process Cost {cost} for {doc.process_name} / {doc.supplier} / {doc.item}")
		doc.submit()
		self.count("YRP Work Order")
		if source:
			self.notes.append(f"{doc.name} ({plan.process}, {plan.dc.number}) sourced from {source}")
		return doc.name

	def get_yarn_ready_dates(self, knitting):
		"""A new Knitting DC cannot be posted before the yarn it delivers was received for the lot."""
		dates = {}
		for plan in knitting:
			name = self.work_orders[self.get_key(plan)]
			if name in self.reused:
				continue
			items = {row.item_variant for row in frappe.get_doc("YRP Work Order", name).deliverables}
			ready = yarn.get_stock_ready_date(self.plan.lot, items)
			if ready and ready > plan.dc.date:
				dates[(plan.dc.number, plan.cloth)] = ready
				self.notes.append(
					f"{plan.dc.number} posted on {format_date(ready)} (old date {format_date(plan.dc.date)}): "
					"the lot's yarn was received in yrp then"
				)
		return dates

	def ensure_yarn(self, knitting, new_work_orders):
		"""Receive the yarn shortfall of the new Knitting WOs and of the reused WOs' excess deliveries."""
		self.excess_yarn = {
			self.work_orders[self.get_key(plan)]: yarn.get_excess_yarn(
				self.work_orders[self.get_key(plan)], plan.kg
			)
			for plan in knitting
			if self.work_orders[self.get_key(plan)] in self.reused
		}
		self.excess_yarn = {name: excess for name, excess in self.excess_yarn.items() if excess}
		if not new_work_orders and not self.excess_yarn:
			return
		date = min(self.dates[("DC", plan.dc.number, plan.cloth)] for plan in knitting)
		self.yarn_shortfall = yarn.get_shortfall(
			self.plan.lot, new_work_orders, list(self.excess_yarn.values())
		)
		if self.yarn_shortfall:
			yarn.ensure_receipt(self.plan.lot, self.yarn_shortfall, date, self.allow_zero_rate)
			self.count("YRP Stock Entry (Material Receipt)")

	def ensure_delivery(self, plan):
		key = self.get_key(plan)
		if plan.process != KNITTING:
			self.follow_booked_dias(plan)
			self.ensure_work_order(plan)
		work_order = self.work_orders[key]
		if work_order in self.excess_yarn:
			self.ensure_excess_delivery(plan, work_order)
		if key in self.delivery_challans:
			return
		name = find_tagged(
			"YRP Delivery Challan", {"work_order": work_order, "comments": get_tag(plan.dc.number)}
		)
		if name:
			self.skipped["YRP Delivery Challan"] += 1
		else:
			date = self.dates[("DC", plan.dc.number, plan.cloth)]
			name = documents.make_delivery_challan(work_order, plan, date, self.next_time()).name
			self.count("YRP Delivery Challan")
		self.delivery_challans[key] = name

	def follow_booked_dias(self, plan):
		"""Knitted fabric booked on its planned Dia moves on in that Dia, so later lines in the old Dia follow it.
		Knitted Greige becomes every dyed colour, so its remap applies to them too."""
		for document in [plan.dc, *plan.grns]:
			document.lines = [
				replace(
					line,
					dia=get_booked_dia(self.dia_remaps, plan.cloth, line.colour, line.dia),
					planned_dia=get_booked_dia(self.dia_remaps, plan.cloth, line.colour, line.planned_dia),
				)
				for line in document.lines
			]

	def ensure_excess_delivery(self, plan, work_order):
		"""Deliver the yarn a reused Knitting WO still needs for the cloth the old GRNs received."""
		quantities = self.excess_yarn.pop(work_order)
		tag = get_tag(plan.dc.number) + " (excess yarn)"
		if find_tagged("YRP Delivery Challan", {"work_order": work_order, "comments": tag}):
			self.skipped["YRP Delivery Challan"] += 1
			return
		date = self.dates[("DC", plan.dc.number, plan.cloth)]
		documents.make_delivery_challan(work_order, plan, date, self.next_time(), quantities)
		self.count("YRP Delivery Challan")
		self.notes.append(f"{work_order}: excess yarn DC {quantities} for the received cloth")

	def get_knit_routes(self, plan, work_order):
		"""Knitting colour/Dia pairs the WO's cloth IPD can receive (for Actual Dia); empty for other processes."""
		if plan.process != KNITTING:
			return set()
		if work_order not in self.knit_routes:
			builder = WorkOrderBuilder(self.plan.lot, plan, self.fabric_rows[plan.cloth], GREIGE_COLOUR)
			self.knit_routes[work_order] = builder.get_knit_routes(
				documents.get_fabric_deliverable_context(work_order)
			)
		return self.knit_routes[work_order]

	def ensure_receipt(self, plan, grn):
		key = self.get_key(plan)
		work_order = self.work_orders[key]
		if find_tagged(
			"YRP Goods Received Note", {"against_id": work_order, "comments": get_receipt_comments(grn)}
		):
			self.skipped["YRP Goods Received Note"] += 1
			return
		date = self.dates[("GRN", grn.number, plan.dc.number, plan.cloth)]
		knit_routes = self.get_knit_routes(plan, work_order)
		doc, notes = documents.make_goods_received_note(
			work_order,
			self.delivery_challans.get(key),
			grn,
			date,
			self.next_time(),
			knit_routes,
			cap_to_pending=plan.process != KNITTING,
		)
		if plan.process == KNITTING:
			for line in grn.lines:
				if documents.is_booked_on_planned_dia(line, knit_routes):
					self.dia_remaps[(plan.cloth, line.colour, line.dia)] = line.planned_dia
		if grn.remark and doc:
			notes.append(f"{doc.name} ({grn.number}): {grn.remark}")
		self.notes += notes
		self.count("YRP Goods Received Note", int(doc is not None))


def get_booked_dia(dia_remaps, cloth, colour, dia):
	"""The Dia a knitted line was booked on: its own colour's remap, else knitted Greige's."""
	for key in ((cloth, colour, dia), (cloth, GREIGE_COLOUR, dia)):
		if key in dia_remaps:
			return dia_remaps[key]
	return dia
