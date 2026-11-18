# Public-export inventory (WP3)

Nothing has been published. If the owner later asks for a Tableau Public upload, this is what would leave the repo.

| Item | Contents | Notes |
|---|---|---|
| `SafeShift_research_v2.twbx` | Workbook + four embedded CSVs | Aggregated summaries only; no establishment names, addresses, EINs, narrative fields or row-level records |
| `Data/annual_size_summary.csv` | Counts and sums by year x size x scenario | Derived from OSHA ITA Form 300A public data |
| `Data/annual_coverage.csv`, `Data/case_coverage.csv` | Record counts and exclusions | |
| `Data/case_pattern_summary.csv` | Counts by year x mechanism x SOC major group x scenario | Provisional export. Some cells are very small (2-6 reports, e.g. several occupation groups); decide on a minimum-cell rule before any public upload |
| Screenshots in `artifacts/research_v2/tableau/screenshots/` | Dashboard images | The `dev_synthetic_*` image is a development test, not data; do not use in the talk |

Excluded from any export: `dev_scratch/`, `dev_synthetic/`, `.~*.twbr` lock files, QA copies in `displayed/`.

Before export the owner should decide: whether the provisional case export may go public, the small-cell rule, and whether the workbook's embedded author fingerprint (Tableau adds one on save) is acceptable.
