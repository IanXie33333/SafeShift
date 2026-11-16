# WP1 Annual Establishment Patterns — Execution Summary

## Input and reproducibility

- Source: `data/processed/warehouses_4931.csv`
- Source rows: 72,394 (2016–2025)
- Source SHA-256: `07bfdc020cd221741e919077e328643ff2e528e81ece1fc7e3b772dc10d2917d`
- Python: 3.14.7
- pandas: 2.3.3
- NumPy: 2.5.3
- Base Git revision: `6a6a7033da86e551556ccc4a6191013dba4c0995`
- Final submitted revision: pending commit
- Full source-year counts: `artifacts/research_v2/annual/source_run_manifest.json`

Execution command (repository root):

```bash
uv run --locked python -m src.analysis.annual_establishments
```

## Cohort reconciliation

| Measure | Records |
|---|---:|
| Input establishment-years | 72,394 |
| Primary eligible | 72,235 |
| Structurally excluded | 159 |
| Failed NAICS flag | 0 |
| Failed core-fields flag | 89 |
| Failed unique-key flag | 70 |
| Exposure-sensitivity eligible | 71,607 |
| Excluded from sensitivity | 628 |

The three structural failure counts total 159, equal to the unique excluded count. No overlapping structural failures were observed in this source snapshot.

## Generated outputs

- `data/processed/research_v2/annual_size_summary.csv` — 80 rows
- `data/processed/research_v2/annual_coverage.csv` — 20 rows
- `artifacts/research_v2/annual/day_anomaly_audit.csv` — 4,351 flagged entries
- `artifacts/research_v2/annual/coverage_reconciliation.csv`
- `artifacts/research_v2/annual/scenario_comparison.csv` — 40 comparisons
- `artifacts/research_v2/annual/tableau_reference_totals.csv` — 20 rows

## Checks completed

- Automated test suite previously reported passing (47 tests)
- Input-to-primary structural counts reconciled
- Primary-to-sensitivity counts reconciled
- Contributing hours matched size-group summaries across all 20 year/scenario combinations (maximum difference: 0)
- DAFW and DJTR availability counts matched size-group summaries (maximum differences: 0)
- Scenario comparison contained 40 year/size combinations with no missing comparison values
- Tableau reference DART cases equaled DAFW plus DJTR cases
- Source/run manifest passed JSON syntax validation

## Important 2025 exposure anomaly

One 2025 establishment-year reported 100,551,000,000 hours, representing 97.02% of the 2025 primary cohort's reported hours.

- Primary 2025 DART rate: 0.103
- Rate excluding only the largest-hours record: 3.463
- Exposure-sensitivity 2025 DART rate: 3.658

This demonstrates substantial denominator sensitivity. The original record has not been altered.

## Unresolved limitations

- DAFW and DJTR day totals remain `blocked_review`; reported-day findings are not approved
- The day anomaly audit requires further review
- Reporting coverage varies by year; results are descriptive patterns among reporting establishments, not nationally representative incidence estimates
- The existing model-result checksum verifier and its manifest have not yet been confirmed
- Final source-code revision and remaining acceptance checks require verification before PR submission

## Findings

See `docs/research_v2/annual_findings.md` for four candidate findings and their numerical evidence.
