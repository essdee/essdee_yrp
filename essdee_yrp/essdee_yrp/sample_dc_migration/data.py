"""Frozen inputs for the Sample lot migration: 8 old-system SAMPLE DCs (user-approved 20-11-2026), mapped to prod items."""

LOT = "Sample"
LOCATION = "S-0005"
PROCESS_COST_TAX_SLAB = "5"

# User decision 20-11-2026: Rs/kg for every supplier and colour.
PROCESS_RATES = {"Knitting": 13.0, "Dyeing": 50.0, "Heat Setting": 10.0, "Washing": 8.0}

YARN_34_RL = "Yarn 34's RL"
RIB_34_RL = "34's RL Single Rib Fabric"
INTERLOCK = "40's VL Interlock Cloth"
ANDHRA = "30's Andhra Melange Fabric"
ECOVERA = "30's Ecovera Viscose Vortex 20 Denier Fabric"
TENCEL = "34s Tencel Std Ring Spun Siro Compact + 30D Spandex"
SINGLE_JERSEY = "Single Jersey Fabric"


def row(item, qty, rolls=0, rate=None, **attributes):
	"""One WO deliverable (rate = Material Receipt rate), receivable or GRN line; attributes pick the variant."""
	return {"item": item, "attributes": attributes, "qty": qty, "rolls": rolls, "rate": rate}


# Material Receipt rates (Rs/kg) and their prod source (Metabase db 14, read 20-11-2026).
RATE_SOURCES = {
	"Yarn 34's RL-Greige": (323.0, "GRN-2627-07931 / PI26/27-04268 Sri Subam Textiles, 14-10-2026"),
	INTERLOCK: (362.0, "valuation of 40's VL Interlock Cloth-14 Dia-Greige, YRP-GRN-2026-00983, 02-11-2026"),
	ANDHRA: (367.28, "valuation of 30's Andhra Melange Fabric-32 Dia, YRP-GRN-2026-01034, 13-10-2026"),
	ECOVERA: (370.0, "PI26/27-04606 Pallava Textiles 29.75 kg, 27-10-2026 (this sample's purchase)"),
	TENCEL: (420.0, "YRP-GRN-2026-01181 (Product Development), 19-11-2026"),
	SINGLE_JERSEY: (320.0, "PI26/27-03656 NR Fabrics, Single Jersey Fabric-Black-32 Dia, 22-09-2026"),
}


def rate(key):
	return RATE_SOURCES[key][0]


DOCUMENTS = [
	{
		"number": "PG-2526-1333",
		"date": "2026-09-15",
		"process": "Knitting",
		"supplier": "S.C.C APPARELS",
		"remark": "Yarn from old yarn DC DC-2526-10283 (lot Not Applicable, 34's subam, 189.3 kg)",
		"deliverables": [row(YARN_34_RL, 189.3, 0, rate("Yarn 34's RL-Greige"), Colour="Greige")],
		# The 189.3 kg program is split over the received Dias in the received ratio (21.4 : 13.5).
		"receivables": [
			row(RIB_34_RL, 116.07, Colour="Greige", Dia="30 Dia"),
			row(RIB_34_RL, 73.23, Colour="Greige", Dia="36 Dia"),
		],
		"grns": [
			{
				"number": "GRN-2526-9784",
				"date": "2026-09-15",
				"lines": [row(RIB_34_RL, 13.5, 1, Colour="Greige", Dia="36 Dia")],
			},
			{
				"number": "GRN-2526-9844",
				"date": "2026-09-16",
				"lines": [row(RIB_34_RL, 21.4, 2, Colour="Greige", Dia="30 Dia")],
			},
		],
	},
	{
		"number": "DC-2526-10412",
		"date": "2026-09-21",
		"process": "Dyeing",
		"supplier": "M.S.Dyeing Company",
		"remark": "Interlock jersey",
		"deliverables": [row(INTERLOCK, 12.6, 1, rate(INTERLOCK), Colour="Greige", Dia="31 Dia")],
		"receivables": [row(INTERLOCK, 12.6, Colour="Black", Dia="31 Dia")],
	},
	{
		"number": "DC-2526-10637",
		"date": "2026-10-03",
		"process": "Washing",
		"supplier": "KKM WASHING UNIT",
		"remark": "yarn pull out check, lab testing",
		"deliverables": [row(ANDHRA, 4.9, 0, rate(ANDHRA), Colour="Andhra Melange", Dia="38 Dia")],
		"receivables": [row(ANDHRA, 4.9, Colour="Andhra Melange", Dia="38 Dia")],
	},
	{
		"number": "DC-2526-11073",
		"date": "2026-10-23",
		"process": "Dyeing",
		"supplier": "Time Process Mills",
		"remark": "ECO VERA VISCOSE SAMPLE, Black 30 Dia (item has no Colour/Dia variants)",
		"deliverables": [row(ECOVERA, 29.75, 1, rate(ECOVERA))],
		"receivables": [row(ECOVERA, 29.75)],
	},
	{
		"number": "DC-2526-11231",
		"date": "2026-10-30",
		"process": "Heat Setting",
		"supplier": "Ahill Roopa Processors",
		"remark": "LYOCEL ELASTANE, Grey (item has no Colour/Dia variants)",
		"deliverables": [row(TENCEL, 30.3, 1, rate(TENCEL))],
		"receivables": [row(TENCEL, 30.3)],
	},
	{
		"number": "DC-2526-11238",
		"date": "2026-10-31",
		"process": "Washing",
		"supplier": "Vignesh Textiles Process",
		"remark": "SILICON SOFTNER WASHING PURPOSE",
		"deliverables": [row(SINGLE_JERSEY, 10.0, 1, rate(SINGLE_JERSEY), Colour="Black", Dia="28 Dia")],
		"receivables": [row(SINGLE_JERSEY, 10.0, Colour="Black", Dia="28 Dia")],
	},
	{
		"number": "DC-2526-11268",
		"date": "2026-11-02",
		"process": "Dyeing",
		"supplier": "Time Process Mills",
		"remark": "Greige, old Dia 0 (68 Dia from the same-day 26.6 kg Black Compacting DC-2526-11272)",
		"deliverables": [row(SINGLE_JERSEY, 26.6, 1, rate(SINGLE_JERSEY), Colour="Greige", Dia="68 Dia")],
		"receivables": [row(SINGLE_JERSEY, 26.6, Colour="Black", Dia="68 Dia")],
	},
	{
		"number": "DC-2526-11376",
		"date": "2026-11-17",
		"process": "Washing",
		"supplier": "KKM WASHING UNIT",
		"remark": "Silicone Wash Purpose, Single Jersey",
		"deliverables": [row(SINGLE_JERSEY, 10.0, 1, rate(SINGLE_JERSEY), Colour="Black", Dia="68 Dia")],
		"receivables": [row(SINGLE_JERSEY, 10.0, Colour="Black", Dia="68 Dia")],
	},
]
