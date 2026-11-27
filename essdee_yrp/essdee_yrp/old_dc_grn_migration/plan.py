"""Pure per-lot migration plan: one Work Order per old DC and cloth, with the GRNs that received against it."""

from dataclasses import dataclass, field, replace

KNITTING_PROGRAM = "Knitting Program"
KNITTING = "Knitting"
DYEING = "Dyeing"
GREIGE_COLOURS = {"GREY FABRIC", "GREIGE"}
EXCLUDED_PROCESSES = {"Cutting"}
# Lots with no Dyeing (user decision 16-11-2026): this process replaces Dyeing on the cloth IPD and turns the knitted
# Greige into the finished colour, so its lines and every later process's lines carry that colour.
COLOUR_STEPS = {
	"F0826-18": {"process": "Bleaching", "colour": "White"},
	"F0926-49": {"process": "Washing", "colour": "White"},
	"F0726-09": {"process": "Bleaching", "colour": "White"},
	"F0926-48": {"process": "Bleaching", "colour": "White"},
}
# Knitting DC lines put on another IPD Dia by user decision (16-11-2026): (DC number, colour, old Dia) -> IPD Dia.
# GY0926-17: its GRN received the cloth in 32 Dia, not knitted by the IPD. GY0926-10: GRN-2526-9620 received no 24 Dia
# and 453.2 kg of 26 Dia (24 + 26 Dia ordered 459 kg); the IPD's Red 24 Dia folding cannot move onto 26 Dia (Red 26 Dia
# is already a route), so the 24 Dia program is booked on 26 Dia.
KNIT_DIA_MOVES = {
	("PG-2526-1398", "Grey Melange", "22 Dia"): "24 Dia",
	("PG-2526-1259", "Greige", "24 Dia"): "26 Dia",
}
# Old Dias that are a lot's second cloth, not its Knitting Program cloth (user decision 16-11-2026): lot -> {Dia: cloth}.
# The 14 Dia (PG-2526-1314, PG-2526-1315) is the folding cloth (IPD cloth type White Folding); F0926-48 received it
# as 15 Dia.
CLOTH_BY_DIA = {
	"F0726-09": {"14 Dia": "40's VL Interlock Cloth"},
	"F0926-48": {"14 Dia": "40's VL Interlock Cloth", "15 Dia": "40's VL Interlock Cloth"},
}
# GRNs that also received a DC they do not link (user decision 16-11-2026): GRN number -> DC numbers.
# F0926-48: GRN-2526-10576 (linked to PG-2526-1392) received PG-2526-1315's 14 Dia folding as 15 Dia 125.8 kg.
GRN_EXTRA_DCS = {"GRN-2526-10576": ("PG-2526-1315",)}
# GRNs the old system lacks, derived from the next DC by user decision (16-11-2026): lot -> ({"dc", "from_dc"}, ...).
# The DC receives from_dc's lines on from_dc's date. F0926-48: no Bleaching GRN returned the folding of
# DC-2526-11011, so Steaming DC-2526-11280's quantity is its Bleaching receipt.
SYNTHETIC_GRNS = {"F0926-48": ({"dc": "DC-2526-11011", "from_dc": "DC-2526-11280"},)}
# DCs whose lines are another cloth (and colour) than their old colour maps to (user decision 16-11-2026):
# lot -> {DC number: (cloth, yrp colour or None)}. A GRN takes the entry of the DCs it receives.
# GY0926-25: the Greige 36's GL is two cloths. PG-2526-1405 is 36's GL Dyed Cloth (dyed Maroon/Navy);
# PG-2526-1406 is 36's GL White Fabric, knitted White from White yarn and washed (DC-2526-11092), never dyed.
DC_CLOTHS = {
	"GY0926-25": {
		"PG-2526-1405": ("36's GL Dyed Cloth", None),
		"PG-2526-1406": ("36's GL White Fabric", "White"),
		"DC-2526-11092": ("36's GL White Fabric", "White"),
	},
}
# GRNs whose old DC links are wrong (user decision 16-11-2026): GRN number -> the DC numbers it receives instead.
# GY0926-25: both knitting GRNs link PG-2526-1406; GRN-2526-10538 (673.8 kg, dyed by DC-2526-10942) is PG-2526-1405's.
GRN_LINKS = {"GRN-2526-10538": ("PG-2526-1405",)}
# Garment IPD accessory Dias changed by user decision (16-11-2026): lot -> (IPD, IPD Dia, new Dia).
# F0826-45: the old system knitted the Folding accessory in 24 Dia; the IPD has it in 26 Dia.
IPD_ACCESSORY_DIAS = {"F0826-45": ("Casual Designer vest - 5-11", "26 Dia", "24 Dia")}
# Old DC/GRN lines entered in the wrong Dia (user decision 17-11-2026): lot -> {(document number, old colour, old Dia):
# corrected old Dia}. The line merges into the document's line of that colour and Dia. GY0926-24: Dyeing DC-2526-10946's
# Navy 15 Dia 21 kg is Navy 24 Dia (no 15 Dia was knitted in the lot).
# F0926-55 (27-11-2026): the 28 Dia Navy/Black was booked on 26 Dia on 17-11; the later Washing GRN follows it.
LINE_DIAS = {
	"GY0926-24": {("DC-2526-10946", "NAVY", "15"): "24"},
	"F0926-55": {
		("DC-2526-10717", "NAVY BLUE", "28"): "26",
		("DC-2526-10796", "BLACK", "28"): "26",
		("GRN-2526-10976", "NAVY BLUE", "28"): "26",
		("GRN-2526-10976", "BLACK", "28"): "26",
	},
}
# Old documents left out by user decision (27-11-2026): lot -> document numbers.
# F0926-48: GRN-2526-11024 repeats GRN-2526-10862 (same Steaming DC, same 125.8 kg).
SKIPPED_DOCUMENTS = {"F0926-48": {"GRN-2526-11024"}}


@dataclass(frozen=True)
class Line:
	colour: str
	dia: str
	rolls: int
	kg: float


@dataclass
class Document:
	"""One old DC or GRN of one lot; date is ISO (YYYY-MM-DD)."""

	side: str
	document_id: int
	number: str
	date: str
	process: str
	supplier: str
	linked_dc_ids: tuple = ()
	lines: list = field(default_factory=list)
	remark: str = ""

	@classmethod
	def from_dict(cls, data):
		lines = [
			Line(row["colour"], row["dia"], int(row["rolls"]), float(row["kg"])) for row in data["lines"]
		]
		return cls(
			data["side"],
			int(data["document_id"]),
			data["number"],
			data["date"],
			data["process"],
			data["supplier"],
			tuple(data["linked_dc_ids"]),
			lines,
		)


class PlanError(Exception):
	"""The old data cannot be mapped to yrp without a decision."""


@dataclass(frozen=True)
class PlanLine:
	colour: str
	dia: str
	rolls: int
	kg: float
	old_colour: str = ""
	planned_dia: str = ""
	cloth: str = ""


@dataclass
class PlannedDocument:
	number: str
	date: str
	lines: list = field(default_factory=list)
	remark: str = ""


@dataclass
class WorkOrderPlan:
	process: str
	cloth: str
	supplier: str
	old_supplier: str
	dc: PlannedDocument
	grns: list = field(default_factory=list)
	program_lines: list = field(default_factory=list)

	@property
	def lines(self):
		return self.dc.lines

	@property
	def kg(self):
		return round(sum(line.kg for line in self.dc.lines), 3)


@dataclass(frozen=True)
class LotMappings:
	"""Old -> yrp names resolved by the gap analysis; cloth_by_colour lists the cloths whose IPD routes carry a yrp colour."""

	colours: dict
	suppliers: dict
	greige_colour: str
	cloth_by_old_colour: dict
	cloth_by_colour: dict


@dataclass
class LotPlan:
	"""cloth_processes: cloth -> its process order from the cloth IPD's Fabric Processes, once known."""

	lot: str
	processes: list
	work_orders: list
	cloth_processes: dict = field(default_factory=dict)

	def get_stages(self, cloth):
		"""The cloth's processes in chain order: its IPD's order when set, else the lot's process order."""
		if cloth in self.cloth_processes:
			return self.cloth_processes[cloth]
		return [
			p for p in self.processes if any(w.process == p and w.cloth == cloth for w in self.work_orders)
		]


def get_yrp_process(old_process):
	return KNITTING if old_process == KNITTING_PROGRAM else old_process


def to_dia(old_dia):
	"""'18' -> '18 Dia'; blank or 0 -> None."""
	text = (old_dia or "").strip()
	try:
		number = float(text)
	except ValueError:
		return None
	if number <= 0:
		return None
	return f"{number:g} Dia"


def allocate(total, weights):
	"""Split total by weights (equal when all weights are 0), rounded to 3 decimals; the last share takes the rounding."""
	if not weights:
		raise PlanError("nothing to allocate to")
	if not any(weights):
		weights = [1] * len(weights)
	weight_sum = sum(weights)
	shares = [round(total * weight / weight_sum, 3) for weight in weights[:-1]]
	return [*shares, round(total - sum(shares), 3)]


def allocate_rolls(total, weights):
	shares = [round(value) for value in allocate(total, weights)[:-1]]
	return [*shares, total - sum(shares)]


def split_dialess_lines(lines, reference_lines):
	"""Book lines without a Dia in the Dia ratio of the same colour's reference lines."""
	result = []
	for line in lines:
		if to_dia(line.dia):
			result.append(line)
			continue
		reference = [r for r in reference_lines if r.colour == line.colour and to_dia(r.dia)]
		if not reference:
			raise PlanError(f"{line.kg} kg of {line.colour} has no Dia and no reference line to split it by")
		weights = [r.kg for r in reference]
		kgs = allocate(line.kg, weights)
		rolls = allocate_rolls(line.rolls, weights)
		result += [
			Line(line.colour, r.dia, roll, kg) for r, kg, roll in zip(reference, kgs, rolls, strict=True)
		]
	return result


def get_process_order(documents):
	"""Knitting, Dyeing, then the other processes by their first old DC date (the app's supported cloth route)."""
	first_dates = {}
	for document in documents:
		if document.side == "DC":
			process = get_yrp_process(document.process)
			first_dates[process] = min(first_dates.get(process, document.date), document.date)
	return sorted(
		first_dates,
		key=lambda process: (process != KNITTING, process != DYEING, first_dates[process], process),
	)


class LotPlanner:
	"""Maps one lot's old documents to Work Order plans."""

	def __init__(self, lot, mappings):
		self.lot = lot
		self.mappings = mappings

	def map_colour(self, old):
		if old in GREIGE_COLOURS:
			return self.mappings.greige_colour
		if old not in self.mappings.colours:
			raise PlanError(f"lot {self.lot}: old colour {old!r} has no yrp Colour mapping")
		return self.mappings.colours[old]

	def map_supplier(self, old):
		if old not in self.mappings.suppliers:
			raise PlanError(f"lot {self.lot}: old supplier {old!r} has no yrp Supplier mapping")
		return self.mappings.suppliers[old]

	def get_cloth(self, old_colour, colour):
		"""Knitting fabric mapping of the old colour first, then the one cloth whose IPD carries the colour."""
		names = [old_colour, *sorted(GREIGE_COLOURS)] if old_colour in GREIGE_COLOURS else [old_colour]
		for name in names:
			if name in self.mappings.cloth_by_old_colour:
				return self.mappings.cloth_by_old_colour[name]
		cloths = self.mappings.cloth_by_colour.get(colour, [])
		if len(cloths) != 1:
			raise PlanError(
				f"lot {self.lot}: colour {old_colour!r} maps to cloth {cloths or 'none'}; need exactly one cloth"
			)
		return cloths[0]

	def to_plan_lines(self, lines, number, dc_cloth=None):
		"""dc_cloth: the document's DC_CLOTHS (cloth, colour) entry, which sets every line's cloth and colour."""
		cloth_override, colour_override = dc_cloth or (None, None)
		result = []
		for line in lines:
			dia = to_dia(line.dia)
			if not dia:
				raise PlanError(f"{number}: line {line.colour} has no Dia")
			colour = colour_override or self.map_colour(line.colour)
			cloth = (
				cloth_override
				or CLOTH_BY_DIA.get(self.lot, {}).get(dia)
				or self.get_cloth(line.colour, colour)
			)
			result.append(PlanLine(colour, dia, line.rolls, line.kg, line.colour, dia, cloth))
		return result

	def get_grn_dc_cloth(self, grn, linked):
		"""The DC_CLOTHS entry the GRN's DCs share; fails when they disagree."""
		entries = {DC_CLOTHS.get(self.lot, {}).get(plan.dc.number) for plan in linked.values()}
		if len(entries) > 1:
			raise PlanError(f"{grn.number}: its DCs are on different DC_CLOTHS entries {entries}")
		return entries.pop()

	def build(self, documents):
		documents = correct_line_dias(self.lot, skip_documents(self.lot, documents))
		documents = [*documents, *get_synthetic_grns(self.lot, documents)]
		dcs = [
			d for d in documents if d.side == "DC" and get_yrp_process(d.process) not in EXCLUDED_PROCESSES
		]
		work_orders = {}
		for document in dcs:
			lines = self.to_plan_lines(
				split_dialess_lines(document.lines, self.get_previous_lines(document, documents)),
				document.number,
				DC_CLOTHS.get(self.lot, {}).get(document.number),
			)
			for cloth in dict.fromkeys(line.cloth for line in lines):
				work_orders[(document.document_id, cloth)] = WorkOrderPlan(
					get_yrp_process(document.process),
					cloth,
					self.map_supplier(document.supplier),
					document.supplier,
					PlannedDocument(
						document.number, document.date, [line for line in lines if line.cloth == cloth]
					),
				)
		for document in documents:
			if document.side == "GRN":
				self.add_grn(document, work_orders)
		for plan in work_orders.values():
			if plan.process == KNITTING:
				book_on_replaced_dias(plan)
				raise_to_received(plan)
			elif self.lot in COLOUR_STEPS:
				recolour_greige(plan, self.mappings.greige_colour, COLOUR_STEPS[self.lot]["colour"])
		return LotPlan(self.lot, get_process_order(dcs), list(work_orders.values()))

	@staticmethod
	def get_previous_lines(document, documents):
		"""Reference for a dia-less DC: GRN lines received before it."""
		return [line for d in documents if d.side == "GRN" and d.date <= document.date for line in d.lines]

	def add_grn(self, grn, work_orders):
		"""A GRN can link DCs of several lots; only this lot's DCs (and its GRN_EXTRA_DCS) receive its lines.
		GRN_LINKS replaces the GRN's DC links."""
		extra = GRN_EXTRA_DCS.get(grn.number, ())
		links = GRN_LINKS.get(grn.number)
		linked = {
			key: plan
			for key, plan in work_orders.items()
			if (plan.dc.number in links if links else key[0] in grn.linked_dc_ids) or plan.dc.number in extra
		}
		if not linked:
			raise PlanError(
				f"{grn.number}: none of its linked DC(s) {grn.linked_dc_ids} is a process DC of this lot"
			)
		reference = [
			Line(line.old_colour, line.dia.split()[0], line.rolls, line.kg)
			for plan in linked.values()
			for line in plan.lines
		]
		shares = {key: [] for key in linked}
		lines = self.to_plan_lines(
			split_dialess_lines(grn.lines, reference), grn.number, self.get_grn_dc_cloth(grn, linked)
		)
		for line in lines:
			for key, share in self.allocate_grn_line(grn, line, linked):
				shares[key].append(share)
		for key, lines in shares.items():
			if lines:
				linked[key].grns.append(PlannedDocument(grn.number, grn.date, lines, grn.remark))

	@staticmethod
	def allocate_grn_line(grn, line, linked):
		"""Same cloth, colour and Dia first; Knitting may receive another (actual) Dia of the same colour."""
		candidates = [
			(key, dc_line)
			for key, plan in linked.items()
			for dc_line in plan.lines
			if dc_line.cloth == line.cloth
		]
		targets = [
			(key, dc_line)
			for key, dc_line in candidates
			if (dc_line.colour, dc_line.dia) == (line.colour, line.dia)
		]
		if not targets and next(iter(linked.values())).process == KNITTING:
			targets = [(key, dc_line) for key, dc_line in candidates if dc_line.colour == line.colour]
		if not targets:
			raise PlanError(
				f"{grn.number}: {line.old_colour} {line.dia} {line.kg} kg matches no line of its linked DC(s)"
			)
		weights = [dc_line.kg for _, dc_line in targets]
		kgs = allocate(line.kg, weights)
		rolls = allocate_rolls(line.rolls, weights)
		return [
			(key, PlanLine(line.colour, line.dia, roll, kg, line.old_colour, dc_line.dia, line.cloth))
			for (key, dc_line), kg, roll in zip(targets, kgs, rolls, strict=True)
		]


def skip_documents(lot, documents):
	"""SKIPPED_DOCUMENTS: drop the listed old documents; fails if one is not in the lot."""
	skipped = SKIPPED_DOCUMENTS.get(lot, set())
	if missing := skipped - {document.number for document in documents}:
		raise PlanError(f"lot {lot}: SKIPPED_DOCUMENTS {sorted(missing)} not in the old documents")
	return [document for document in documents if document.number not in skipped]


def correct_line_dias(lot, documents):
	"""LINE_DIAS: each listed line moves to its corrected Dia, merged with the document's line already there."""
	corrections = LINE_DIAS.get(lot, {})
	found = {(d.number, line.colour, line.dia) for d in documents for line in d.lines} & corrections.keys()
	if missing := corrections.keys() - found:
		raise PlanError(f"lot {lot}: LINE_DIAS line(s) {sorted(missing)} not in the old documents")
	return [correct_document_dias(document, corrections) for document in documents]


def correct_document_dias(document, corrections):
	if not any((document.number, line.colour, line.dia) in corrections for line in document.lines):
		return document
	lines = {}
	for line in document.lines:
		dia = corrections.get((document.number, line.colour, line.dia), line.dia)
		other = lines.get((line.colour, dia))
		lines[(line.colour, dia)] = (
			Line(line.colour, dia, other.rolls + line.rolls, round(other.kg + line.kg, 3))
			if other
			else replace(line, dia=dia)
		)
	return replace(document, lines=list(lines.values()))


def get_synthetic_grns(lot, documents):
	"""SYNTHETIC_GRNS: a GRN against dc, by its supplier, with from_dc's lines on from_dc's date."""
	dcs = {d.number: d for d in documents if d.side == "DC"}
	grns = []
	for entry in SYNTHETIC_GRNS.get(lot, ()):
		missing = [entry[key] for key in ("dc", "from_dc") if entry[key] not in dcs]
		if missing:
			raise PlanError(f"lot {lot}: synthetic GRN needs DC(s) {missing} not in the lot")
		dc, from_dc = dcs[entry["dc"]], dcs[entry["from_dc"]]
		if from_dc.date < dc.date:
			raise PlanError(f"lot {lot}: {from_dc.number} ({from_dc.date}) is before {dc.number} ({dc.date})")
		remark = (
			f"Derived {dc.process} GRN: the old system has no {dc.process} GRN for {dc.number}; "
			f"quantity taken from {from_dc.process} DC {from_dc.number}"
		)
		grns.append(
			Document(
				"GRN",
				-from_dc.document_id,
				f"DERIVED-{from_dc.number}",
				from_dc.date,
				dc.process,
				dc.supplier,
				(dc.document_id,),
				list(from_dc.lines),
				remark,
			)
		)
	return grns


def book_on_replaced_dias(plan):
	"""A Knitting GRN line in a Dia its DC did not program is booked only on the programmed Dia of its colour that it
	replaced (old DC vs GRN Dias), not spread over every Dia of the colour."""
	programmed = {(line.colour, line.dia) for line in plan.dc.lines}
	for grn in plan.grns:
		actual = {}
		for line in grn.lines:
			if (line.colour, line.dia) not in programmed:
				actual.setdefault((line.colour, line.dia), []).append(line)
		merged = [
			replace(
				lines[0], kg=round(sum(line.kg for line in lines), 3), rolls=sum(line.rolls for line in lines)
			)
			for lines in actual.values()
		]
		grn.lines = [line for line in grn.lines if (line.colour, line.dia) in programmed] + [
			replace(line, planned_dia=get_replaced_dia(plan, line)) for line in merged
		]


def get_replaced_dia(plan, line):
	"""The programmed Dia of the line's colour whose GRNs fell short of its program the most."""
	dias = [p.dia for p in plan.dc.lines if p.colour == line.colour]
	if len(dias) == 1:
		return dias[0]
	gains = get_dia_gains(plan, line.colour, dias)
	worst = min(gains.values())
	losers = [dia for dia, gain in gains.items() if gain == worst]
	if worst >= 0 or len(losers) != 1:
		raise PlanError(
			f"{plan.dc.number}: {line.colour} received in {line.dia} {line.kg:g} kg replaces no single programmed "
			f"Dia (received minus program: {format_gains(gains)})"
		)
	return losers[0]


def get_dia_gains(plan, colour, dias):
	"""Received (in that exact Dia) minus program kg per Dia of one colour."""
	program_lines = plan.program_lines or plan.dc.lines
	gains = {}
	for dia in dias:
		received = sum(g.kg for grn in plan.grns for g in grn.lines if (g.colour, g.dia) == (colour, dia))
		program = sum(p.kg for p in program_lines if (p.colour, p.dia) == (colour, dia))
		gains[dia] = round(received - program, 3)
	return gains


def format_gains(gains):
	return ", ".join(f"{dia} {gains[dia]:+g} kg" for dia in sorted(gains, key=dia_number))


def raise_to_received(plan):
	"""A Knitting Program DC is a program: when more cloth came back for a Colour/Dia, the WO (and its yarn) covers it.
	program_lines keeps the old DC's own quantities."""
	plan.program_lines = plan.program_lines or list(plan.dc.lines)
	received = {}
	for grn in plan.grns:
		for line in grn.lines:
			key = (line.colour, line.planned_dia)
			received[key] = round(received.get(key, 0) + line.kg, 3)
	plan.dc.lines = [
		replace(line, kg=max(line.kg, received.get((line.colour, line.dia), 0)))
		for line in plan.program_lines
	]


def recolour_greige(plan, greige_colour, colour):
	"""Greige lines of a process at or after the lot's colour step are the finished colour."""
	for document in [plan.dc, *plan.grns]:
		document.lines = [
			replace(line, colour=colour) if line.colour == greige_colour else line for line in document.lines
		]


def move_to_offered_dias(plan, offered):
	"""A Knitting DC line in a Dia the IPD does not knit for its colour (or listed in KNIT_DIA_MOVES) moves to its
	KNIT_DIA_MOVES Dia, else to the offered Dia whose GRNs received the most over its program; GRN lines planned on it
	follow. offered = {(colour, Dia)}. Returns notes."""
	colours = {colour for colour, _dia in offered}
	moving = [
		line
		for line in plan.program_lines
		if (line.colour in colours and (line.colour, line.dia) not in offered)
		or (plan.dc.number, line.colour, line.dia) in KNIT_DIA_MOVES
	]
	notes = []
	for line in moving:
		dia = KNIT_DIA_MOVES.get((plan.dc.number, line.colour, line.dia)) or get_received_dia(
			plan, line, offered
		)
		plan.program_lines = merge_line(plan.program_lines, line, dia)
		for grn in plan.grns:
			grn.lines = [
				replace(g, planned_dia=dia) if (g.colour, g.planned_dia) == (line.colour, line.dia) else g
				for g in grn.lines
			]
		reason = (
			"user decision"
			if (plan.dc.number, line.colour, line.dia) in KNIT_DIA_MOVES
			else "its GRNs received that cloth there"
		)
		knitted = "knitted by the IPD" if (line.colour, line.dia) in offered else "not knitted by the IPD"
		notes.append(
			f"{plan.dc.number}: {line.colour} {line.dia} {line.kg:g} kg put on {dia} ({knitted}; {reason})"
		)
	if moving:
		raise_to_received(plan)
	return notes


def get_received_dia(plan, line, offered):
	"""The one offered Dia of the line's colour whose GRN receipts exceed its program the most."""
	gains = get_dia_gains(plan, line.colour, [dia for colour, dia in offered if colour == line.colour])
	best = max(gains.values(), default=0)
	winners = [dia for dia, gain in gains.items() if gain == best]
	if best <= 0 or len(winners) != 1:
		raise PlanError(
			f"{plan.dc.number}: {line.colour} {line.dia} {line.kg:g} kg is not knitted by the IPD and its GRNs show "
			f"no single IPD Dia that received extra cloth (received minus program: {format_gains(gains)})"
		)
	return winners[0]


def dia_number(dia):
	return float(dia.split()[0])


def merge_line(lines, line, dia):
	"""Add line's kg and rolls to the line of the same colour in dia (or move it there)."""
	target = next((other for other in lines if (other.colour, other.dia) == (line.colour, dia)), None)
	if target is None:
		return [replace(other, dia=dia, planned_dia=dia) if other is line else other for other in lines]
	merged = replace(target, kg=round(target.kg + line.kg, 3), rolls=target.rolls + line.rolls)
	return [merged if other is target else other for other in lines if other is not line]


def build_lot_plan(lot, documents, mappings):
	return LotPlanner(lot, mappings).build(documents)


def build_lot_plan_from_snapshot(data):
	"""data = one snapshot lot: {"lot", "documents", "mappings"}."""
	mappings = LotMappings(**data["mappings"])
	return build_lot_plan(data["lot"], [Document.from_dict(d) for d in data["documents"]], mappings)


def get_ready_date(dc_kg_so_far, upstream_receipts):
	"""Earliest upstream GRN date by which the received kg covers dc_kg_so_far; the last one when never covered."""
	received = 0.0
	for date, kg in upstream_receipts:
		received += kg
		if received + 0.001 >= dc_kg_so_far:
			return date
	return upstream_receipts[-1][0] if upstream_receipts else None


def get_effective_dates(plan, min_dc_dates=None):
	"""Posting dates: an old DC is posted no earlier than the upstream receipts that feed it (or its min_dc_dates
	entry, keyed (dc number, cloth)), and a GRN no earlier than its DC.

	Keys: ("DC", dc number, cloth) and ("GRN", grn number, dc number, cloth); values are ISO dates.
	"""
	min_dc_dates = min_dc_dates or {}
	dates = {}
	for cloth in dict.fromkeys(work_order.cloth for work_order in plan.work_orders):
		stages = plan.get_stages(cloth)
		receipts = {}
		for position, process in enumerate(stages):
			work_orders = sorted(
				(w for w in plan.work_orders if w.process == process and w.cloth == cloth),
				key=lambda w: (w.dc.date, w.dc.number),
			)
			upstream = sorted(receipts.get(stages[position - 1], [])) if position else []
			delivered = {}
			for work_order in work_orders:
				for line in work_order.lines:
					delivered[line.colour] = delivered.get(line.colour, 0) + line.kg
				candidates = [
					work_order.dc.date,
					get_upstream_ready_date(work_order.lines, delivered, upstream),
					min_dc_dates.get((work_order.dc.number, cloth)),
				]
				dc_date = max(date for date in candidates if date)
				dates[("DC", work_order.dc.number, cloth)] = dc_date
				for grn in work_order.grns:
					grn_date = max(grn.date, dc_date)
					dates[("GRN", grn.number, work_order.dc.number, cloth)] = grn_date
					receipts.setdefault(process, []).extend(
						(grn_date, line.colour, line.kg) for line in grn.lines
					)
	return dates


def get_upstream_ready_date(lines, delivered, upstream):
	"""Ready date of a DC whose lines bring the stage's kg delivered so far ({colour: kg}) to `delivered`.

	upstream = sorted (date, colour, kg) receipts of the previous stage. Counted per colour when they carry every
	colour of the DC (the stage keeps the colour), else over all colours (e.g. Greige dyed into colours).
	"""
	colours = {line.colour for line in lines}
	if colours and colours <= {colour for _date, colour, _kg in upstream}:
		return max(
			get_ready_date(delivered[colour], [(date, kg) for date, c, kg in upstream if c == colour])
			for colour in colours
		)
	return get_ready_date(sum(delivered.values()), [(date, kg) for date, _colour, kg in upstream])


def get_yarn_shortfall(needed, available):
	"""{yarn item: qty still needed after the yarn already received for the lot}."""
	shortfall = {}
	for item, qty in needed.items():
		missing = round(qty - available.get(item, 0), 3)
		if missing > 0:
			shortfall[item] = missing
	return shortfall


def get_missing_rates(shortfall, rates):
	return sorted(item for item in shortfall if rates.get(item) is None)
