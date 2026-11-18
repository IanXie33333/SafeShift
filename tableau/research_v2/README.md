# Tableau integration (WP3, research_v2)

Genuine packaged workbook: `SafeShift_research_v2.twbx` (built in Tableau Desktop 2026.3; open with Tableau Desktop or Reader).

## Data sources (separate, never joined or blended)

| Data source | File (in `Data/`) | Grain |
|---|---|---|
| annual_size_summary | `annual_size_summary.csv` | year x size group x scenario (primary, exposure_sensitivity) |
| annual_coverage | `annual_coverage.csv` | year x scenario |
| case_pattern_summary | `case_pattern_summary.csv` | year x mechanism x SOC major group x scenario (primary, day_review_sensitivity) |
| case_coverage | `case_coverage.csv` | year x scenario |

The case files are a **provisional export**; swap in the WP2 owner's export when available (same column contract, checked by `validate_contracts.py`).

## Dashboards

- **Annual dashboard** - "Reported warehouse cases and rates by establishment size, 2016-2025"
- **Case dashboard** - "Mechanisms and occupations in reported warehouse cases, 2023-2024" (labelled PROVISIONAL CASE EXPORT)
- **Methods and coverage** - always-available methods, scenarios, limitations and coverage tables

Each dashboard has one single-value scenario parameter (default `primary`, no "All scenarios") and a mandatory `[scenario] = [Selected scenario]` filter on every sheet.

## Calculations

- Pooled rate = `200000 * SUM(dart_case_count) / SUM(hours_sum)`; the stored `dart_rate` column is never averaged.
- Mean days = `SUM(days_sum) / SUM(known_report_count)`.
- Percent of reports uses a level-of-detail denominator and includes Unknown and Other.
- Day gate: `blocked_review` -> withheld with "Work-time measure awaiting validation"; `partial_valid_values` -> shown with a coverage note; `ready` -> shown.
- Sheets prefixed `QA ` are QA-only (integer-scaled values for full precision) and are on no dashboard.

## Rebuild and re-check

```
python tableau/research_v2/validate_contracts.py --annual-dir data/processed/research_v2 --case-dir <case export dir> \
  --annual-ref artifacts/research_v2/annual/tableau_reference_totals.csv --case-ref <case reference totals> \
  --out artifacts/research_v2/tableau/contract_checks.csv
python tableau/research_v2/build_workbook.py --annual-dir ... --case-dir ... --out-dir <dir> --data-directory <abs path to Data>
```

`build_workbook.py` writes a starting .twb; the delivered .twbx was opened and saved by Tableau (File > Save As > packaged workbook). Re-run QA: open the workbook, copy each `QA ` sheet (Worksheet > Copy > Data) into `artifacts/research_v2/tableau/displayed/`, then run `make_qa_results.py`.

## Not included

No Tableau Public publication (needs the owner's instruction). See `artifacts/research_v2/tableau/qa_note.md` for QA results and open issues, and `artifacts/research_v2/tableau/public_export_inventory.md` before any public export.
