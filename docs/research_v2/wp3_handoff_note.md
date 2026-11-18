# WP3 handoff note

**Status (Tue 17 Nov 2026, evening):** workbook built, opened and checked in Tableau, dashboards exported, QA passing; ready for tonight's review with the caveats below.

**Where things are** (all under the SafeShift project folder)

- `tableau/research_v2/SafeShift_research_v2.twbx`, `README.md`, `Data/`, `build_workbook.py`, `validate_contracts.py`, `make_qa_results.py`
- `artifacts/research_v2/tableau/`: `qa_note.md`, `qa_results.csv`, `contract_checks.csv`, `source_run_manifest.json`, `public_export_inventory.md`, `displayed/` (values copied out of Tableau), `screenshots/`
- `docs/research_v2/`: `tableau_findings_limitations.md`, this note

**Needs a decision**

1. Who owns the real case export (WP2)? Until it lands, the case dashboard stays labelled PROVISIONAL. Swap the two case CSVs, re-run the two scripts, re-save in Tableau.
2. For Wednesday's talk: show primary and exposure-sensitivity side by side for 2025.
3. Whether to wire a mechanism highlight action (not done) and fix the palette (default colours currently).

**Not done:** Tableau Public publishing (no instruction); committing/branching (nothing committed; working tree has untracked WP2 module, tests, reference map and these WP3 files).

**Scratch to ignore:** `tableau/research_v2/dev_scratch/` (old test workbooks), hidden `.~*.twbr` lock files, `dev_synthetic/` (development-only gate test, not data).
