# Old DC/GRN migration

This one-off script moves the "Ready" lots from the old DC/GRN software into yrp. It is a plain package that you run by hand: it is not a patch, it adds no hooks and it changes no doctypes. At runtime it reads only `data.py` and the site DB.

**It dry-runs by default.** Unless you pass `commit`, a run does all the work in one transaction and then rolls it back.

## What it does per lot

1. **Garment IPD accessory Dia.** A lot in `plan.IPD_ACCESSORY_DIAS` (user decision) gets its garment IPD's accessory Dia changed (e.g. F0826-45 Folding 26 → 24 Dia) before its cloth programs are built, with the same revert and re-approve as below. It fails if another lot uses that IPD.
1. **Cloth programs.** If a planned cloth has no Lot fabric row, the script builds the lot's cloth programs with Build Cloth Programs. Knitting colours come from the old Knitting Program DCs. For yarn colours, it prefers a variant the lot already has in stock.
2. **Process chain.** It adds any missing process (Washing, Bleaching, Steaming, Heat Setting, ...) to the cloth IPD's Fabric Processes chain as a plain step.
   - If the IPD is Approved, it reverts the approval, adds the steps, then re-approves it with the app's own `revert_ipd_approval` / `approve_ipd`.
   - If the IPD already has every step, the script leaves it alone.
   - Lots in `plan.COLOUR_STEPS` have no Dyeing (user decision): their Bleaching or Washing takes the Dyeing step's place on the cloth IPD (at Build Cloth Programs, or by renaming the Dyeing step of an existing IPD), turns Greige into White, and every later line carries White.
   - Every revert and re-approve is logged in the report.
   - Each cloth's stages then follow its IPD's Fabric Processes order.
3. **Work Orders.** It creates one YRP Work Order per old DC and cloth, with the old supplier and the old quantities, through the Calculate popup's API (`calculate_fabric_deliverables`).
   - A real submitted Knitting WO of the lot, for the same supplier and cloth and the same quantity (within 2%), is reused instead of creating a new one.
   - A Knitting WO's quantity is raised to the cloth that was actually received.
   - Old Dias listed in `plan.CLOTH_BY_DIA` belong to the lot's second cloth (e.g. the 14 Dia folding of F0726-09 and F0926-48), and `plan.GRN_EXTRA_DCS` lets a GRN receive a program DC it does not link.
   - `plan.LINE_DIAS` corrects an old line entered in the wrong Dia (user decision) and merges it into that document's line of the corrected Dia (GY0926-24: Dyeing DC-2526-10946 Navy 15 → 24 Dia).
   - `plan.DC_CLOTHS` puts a DC's lines on another cloth and colour (e.g. GY0926-25: PG-2526-1406 and its Washing DC are 36's GL White Fabric, knitted White); a GRN takes its DCs' entry. `plan.GRN_LINKS` replaces a GRN's old DC links (GY0926-25: GRN-2526-10538 belongs to PG-2526-1405).
   - A Knitting DC line listed in `plan.KNIT_DIA_MOVES` (user decision), or in a Dia the IPD does not knit for its colour, is put on the Dia set there, else on the IPD Dia whose GRNs received the most over the old program (e.g. 22 Dia ordered, 24 Dia received). When no single IPD Dia received extra cloth, the lot fails with the received-minus-program per Dia.
   - If no approved Process Cost applies, it creates and approves one at the rate in `data.PROCESS_RATES`. A `{Colour: rate}` value (Dyeing, priced per colour) makes a Colour-wise Process Cost with one price per colour the WO receives; a receivable colour without a rate fails the lot.
4. **Yarn.** It reuses the lot's yarn in the fabric store (S-0005) and makes one Material Receipt for the shortfall, at the lot's rate in `data.YARN_RATES` (lot → {yarn item: rate}). A reused Knitting WO that received more cloth than its yarn gets an excess yarn DC.
5. **DCs and GRNs.** It creates them chain stage by stage, in date order, with `get_work_order_defaults`.
   - The posting date is the old date. A DC moves later, and the report says so, when the yarn or the upstream fabric it needs was received later in yrp (counted per colour when the previous stage keeps the colour).
   - A GRN line is split over the receivable rows of its variant (one per source bucket) by their pending kg.
   - A GRN the old system lacks is derived from the next DC when listed in `plan.SYNTHETIC_GRNS` (user decision): e.g. F0926-48's Bleaching DC-2526-11011 receives Steaming DC-2526-11280's folding qty on the Steaming DC's date. Its number is `DERIVED-<DC no>` and its comments say where the quantity came from.
   - The old DC/GRN number goes in `comments` ("Migrated from old DC/GRN: <no>") and in `supplier_document_no`.
   - A Knitting GRN line in a Dia its old DC did not program belongs only to the programmed Dia of its colour that it replaced: the one its GRNs fell short of the most (e.g. 20 Dia ordered, 18 Dia received). If no single Dia fell short, the lot fails with the received-minus-program per Dia.
   - A Knitting GRN in another Dia is booked as Actual Dia (the GRN's Actual Dia rows) when the IPD knits that Colour/Dia. yrp calculates an Actual Dia's yarn from the IPD's Knitting matrix and rejects a Dia it lacks, so otherwise the line is booked on the planned Dia and noted.
   - Ordered vs received differences are not errors. A DC sends at most what the upstream GRNs hold, and a process GRN (not Knitting) books at most the kg still pending at the supplier; each cut is noted. Later lines follow a knitted Dia that was booked on its planned Dia (for knitted Greige, in every dyed colour).
   - Pending balances stay open on the WO.

Re-running skips anything that already carries the tag. If one lot fails, it is rolled back to its savepoint and reported, and the other lots continue.

**Rates.** The script refuses to create a Material Receipt while a needed yarn rate is `None`, unless you pass `allow_zero_rate`. It refuses to create a Process Cost while a needed process rate is `None`, because the app requires a price above 0. `placeholder_rates` is allowed in a dry run only: it uses rate 1 so you can test the rest of the run. Each report lists the rates still needed.

**Live integrations.**
- Outbound `requests` HTTP is blocked for the whole run.
- In a dry run, no background job is queued.
- In a commit run, jobs for Telegram, GSTIN, spine, SMS, WhatsApp, notifications, email or FCM are dropped. Local jobs such as stock reposting still queue.
- Realtime events are intercepted, email is muted and yrp partner generation is deferred.

## Commands

```bash
# 1. Masters: YRP Process, Colour and Dia from the prod values in data.MASTERS, the Supplier (with its Billing Address)
#    and the supplier Warehouse listed in masters.SUPPLIERS (Sri Pavai Knits), the cloth yarn recipes in
#    masters.CLOTH_YARN_RECIPES, the garment IPD cloths in masters.IPD_CLOTHS and the lot cloth programs in
#    masters.LOT_CLOTH_PROGRAMS (built with Build Cloth Programs and the prod routes when the lot has none). Only what the
#    site lacks or has differently is changed; on prod this creates the Sri Pavai Knits Warehouse (the rest is already there).
bench --site <site> execute essdee_yrp.essdee_yrp.old_dc_grn_migration.run.execute --kwargs '{"sync_masters": True}'
bench --site <site> execute essdee_yrp.essdee_yrp.old_dc_grn_migration.run.execute --kwargs '{"sync_masters": True, "commit": True}'

# 2. Dry run (the default), for all lots or for some lots
bench --site <site> execute essdee_yrp.essdee_yrp.old_dc_grn_migration.run.execute
bench --site <site> execute essdee_yrp.essdee_yrp.old_dc_grn_migration.run.execute --kwargs '{"lots": "F0926-49,GY0926-25"}'
bench --site <site> execute essdee_yrp.essdee_yrp.old_dc_grn_migration.run.execute --kwargs '{"placeholder_rates": True, "allow_zero_rate": True}'

# 3. Commit, one lot per transaction. Do this only after you have reviewed the dry-run report and filled YARN_RATES / PROCESS_RATES.
bench --site <site> execute essdee_yrp.essdee_yrp.old_dc_grn_migration.run.execute --kwargs '{"commit": True}'
```

Each run writes `sites/<site>/private/old_dc_grn_migration/<mode>_<timestamp>_report.csv` and `_summary.md`. Per lot they list the status, the error, the documents created per doctype, the yarn shortfall, the rates still needed, the IPD approvals and notes.

## Data

`data.py` is generated. Edit only `YARN_RATES` and `PROCESS_RATES` by hand; the local generator that rebuilds the file keeps those rates. Run the tests with `python -m unittest essdee_yrp.essdee_yrp.old_dc_grn_migration.test_plan`.
