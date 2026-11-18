# WP3 Tableau QA note (research_v2)

Checked in Tableau Desktop 2026.3 (Apple silicon), Tue 17 Nov 2026. Workbook: `tableau/research_v2/SafeShift_research_v2.twbx`. Machine-readable detail: `artifacts/research_v2/tableau/qa_results.csv` (1,216 rows, 0 fail).

## What passed

- **Opens cleanly.** The .twbx was saved by Tableau itself (File > Save As, packaged workbook), re-opened from the package with no schema or data errors. Four separate data sources (annual size summary, annual coverage, case pattern summary, case coverage); no joins, blends or relationships.
- **Input contracts, 25/25** (`contract_checks.csv`): unique grain, enums, DART = DAFW + DJTR, blank day sums while blocked, reconciliation to the WP1 reference, stored rates agree with 200000 x DART / hours.
- **Displayed numbers vs reference tables** (values copied out of Tableau with Worksheet > Copy > Data from QA-only sheets, then compared in `make_qa_results.py`):
  - Annual by year and scenario (20 rows) and by size x year x scenario (80 rows): cases, establishment-years exact; hours within 0.5; pooled rate within 5e-10 (tolerance 1e-6, checked on an integer-scaled calculation so display rounding cannot hide an error).
  - Case by year (4), by mechanism (28), by occupation (64), all years by mechanism (14): report counts, day numerators and denominators exact; mean days exact to 1e-9; percent of reports within 5e-10 and sums to 100% in every scenario/year (Unknown and Other included).
  - Both scenarios of each source were checked, not only the default.
- **Scenario control.** Single-value parameter per dashboard, default `primary`, no "All scenarios"; the Boolean `[scenario] = [Selected scenario]` filter is on every dashboard sheet. Switching to `exposure_sensitivity` re-renders every Annual chart (e.g. 2016 establishment-years 2,022 -> 1,990).
- **Day-total gates.** Annual day totals are withheld (source status `blocked_review`): the dashboard shows "Work-time measure awaiting validation" and no day chart. Case days are shown (provisional export, status `ready`). Synthetic development-only test (NOT data; `tableau/research_v2/dev_synthetic/`): forcing `blocked_review` empties the day charts and shows the withheld status with counts unchanged; forcing `partial_valid_values` shows them with the coverage-note status. Screenshot: `screenshots/dev_synthetic_blocked_case_dashboard.png`.
- **Fixed during QA:** the coverage tables and the work-time status text rendered blank (aggregate text calculations were declared as dimensions). Corrected in `build_workbook.py`, rebuilt, re-checked, and the screenshots re-exported after the fix.

## Remaining issues

1. **Case data are provisional.** The case summaries come from the case-pattern module I wrote earlier (WP2 spec), not from the WP2 owner's export. Every case title, caption and screenshot says so. Replace `Data/case_pattern_summary.csv` and `case_coverage.csv` with the owner's export, re-run `validate_contracts.py` and `make_qa_results.py`. Needs confirming with Ian who owns that export.
2. **2025 primary rates are distorted.** One record with 100,551,000,000 reported hours drags the 2025 primary rate for 50-249 employees to 0.017 (exposure sensitivity: 2.502). The dashboard note says to compare with exposure sensitivity; consider showing both side by side in the talk.
3. **2024 day anomaly.** 1,664 case reports in 2024 carry the DAFW outcome with zero days (13 in 2023). They are reported as-is and flagged in a caption; worth a sentence in the Q&A.
4. **Annual day totals stay withheld** until the work-time review clears; nothing was substituted.
5. **Not done:** (a) mechanism highlighting is not wired as a dashboard action (legend only; filtering is not used); (b) the custom colour palette did not render, so Tableau's default categorical colours are used (consistent across sheets, no colour-vision check); (c) QA copies come from QA-only sheets that use the same calculations as the dashboard sheets, so dashboard sheets were verified visually, not by a second copy of each; (d) coverage tables show counts without thousands separators.
6. **Reading cautions (also on the dashboards):** establishment-years are reporting records, not distinct establishments; case reports are not workers; annual and case populations differ and are not joined or compared.
7. **Housekeeping:** nothing was published to Tableau Public. Tableau left hidden `.~*.twbr` lock files in `tableau/research_v2/` (safe to delete, suggest git-ignoring); older test workbooks were moved to `tableau/research_v2/dev_scratch/` (not for the repo); the first screenshot attempt left a stray `annual_dashboard_primary.png` in `~/Documents` outside the project. The WP2 module, its tests and the reference map are still uncommitted in the working tree.
