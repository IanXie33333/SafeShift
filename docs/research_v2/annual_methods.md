# WP1 — Annual Warehouse Establishment Patterns

## 1. Overview

This analysis examines annual establishment-level patterns in U.S. warehousing and storage (NAICS 4931) using OSHA Injury Tracking Application (ITA) data from 2016–2025.

The analysis summarizes establishment counts, employment, hours worked, and workplace injury measures by year and establishment size group.

Two analytical scenarios are produced:

- **Primary:** Structurally valid warehouse establishment-year records
- **Exposure sensitivity:** Primary records that additionally meet employee and hours-worked exposure criteria

The analysis produces annual summary tables, coverage diagnostics, and a day-metric anomaly audit to support reproducible reporting and visualization.

Reported days-away-from-work (DAFW) and job-transfer-or-restriction (DJTR) day totals remain blocked pending anomaly review.

## 2. Cohort Selection

The analysis uses the processed OSHA ITA warehouse dataset covering 2016–2025.

Each record represents an establishment-year.

### Primary Cohort

Records are included when all three conditions are satisfied:

- `is_naics_4931` is true
- `core_fields_valid` is true
- `establishment_year_unique` is true

The primary cohort contains 72,235 establishment-year records from 72,394 input records.

### Establishment Size Groups

Establishments are classified using `annual_average_employees`:

| Size group | Average employees |
|---|---|
| `lt_50` | Fewer than 50 |
| `50_249` | 50–249 |
| `250_999` | 250–999 |
| `1000_plus` | 1,000 or more |

Size-group boundaries are inclusive at the lower end.

### Exposure Sensitivity Cohort

The exposure sensitivity scenario retains primary records satisfying:

- Annual average employees greater than zero
- Total hours worked greater than zero
- Hours worked per employee between 100 and 8,784, inclusive

This scenario contains 71,607 establishment-year records.

The sensitivity scenario excludes 628 primary records that do not satisfy these exposure criteria.


## 3. Injury Measures and Aggregation

### Injury Case Counts

The analysis reports three injury case measures:

- **DAFW cases:** Cases involving days away from work
- **DJTR cases:** Cases involving job transfer or restriction
- **DART cases:** Sum of DAFW and DJTR cases

DART cases are calculated as:

`dart_count = total_dafw_cases + total_djtr_cases`

### Weighted DART Rate

The annual DART rate is calculated using aggregate case counts and hours worked:

`DART rate = (sum of DART cases / sum of hours worked) × 200,000`

The rate is calculated separately for each year, establishment size group, and scenario.

This method weights establishments by their reported exposure hours rather than averaging individual establishment rates.

### Day Measures

The analysis also tracks:

- Reported DAFW days
- Reported DJTR days

Day measures are distinct from injury case counts and are not interpreted as lost work hours or monetary costs.

Day totals are currently withheld from the summary export pending anomaly review. Case counts and exposure measures remain available.


## 4. Day-Metric Eligibility and Anomaly Handling

### Basic Day-Value Validation

Reported DAFW and DJTR days are evaluated separately.

A day value passes basic validation when it is:

- Present and numeric
- Nonnegative
- A whole number

Zero is treated as a valid reported value, not as missing data.

Passing basic validation does not guarantee that a value is plausible.

### Anomaly Screening

Records are flagged for review when:

- Reported days exceed 180 times total DART cases for the individual or combined measure
- Reported days are positive while total DART cases are zero
- An individual day value is missing, nonnumeric, negative, or fractional

These conditions are screening flags, not automatic exclusion rules.

### Audit and Review Status

The anomaly audit is regenerated using the DART denominator and a separate combined-day screen. Its current row count is recorded in the generated source/run manifest.

Each flagged record retains source-identification information and a `pending_review` disposition.

The analysis does not automatically cap, replace, or remove flagged day values.

Until anomaly dispositions are resolved:

- DAFW day sums remain unavailable
- DJTR day sums remain unavailable
- Both measures have status `blocked_review`

Case counts, establishment counts, employment, and hours-worked summaries remain available.

### Detailed Policy

See `docs/research_v2/annual_day_policy.md` for the full anomaly-handling policy and source-record investigation.


## 5. Outputs and Reproducibility

### Input Dataset

The analysis reads:

`data/processed/warehouses_4931.csv`

This dataset contains processed OSHA ITA warehouse establishment-year records from 2016–2025.

### Generated Outputs

The analysis generates the following core CSV files:

1. `data/processed/research_v2/annual_size_summary.csv`
   - Annual metrics by year, size group, and scenario
   - 80 rows

2. `data/processed/research_v2/annual_coverage.csv`
   - Annual cohort coverage and exclusion diagnostics
   - 20 rows

3. `artifacts/research_v2/annual/day_anomaly_audit.csv`
   - Record-level day-metric screening results
   - DART-based individual/combined review flags and invalid individual values

### Reproduction Command

Run the analysis from the repository root:

```bash
uv run --locked python -m src.analysis.annual_establishments \
  --input data/processed/warehouses_4931.csv \
  --output-dir data/processed/research_v2 \
  --audit-dir artifacts/research_v2/annual
```

### Automated Tests

Run the complete test suite:

```bash
uv run --locked --extra dev pytest -q
```

At the time of this analysis, all 47 tests passed.

### Quality Assurance

The following checks were completed:

- Input-to-primary cohort reconciliation
- Primary-to-sensitivity cohort reconciliation
- Annual summary-to-coverage reconciliation
- Duplicate year/size-group/scenario detection
- Size-group boundary tests
- Weighted DART rate calculation tests
- Day-metric validation and anomaly-screening tests
- Blocked day-total export tests

The analysis is reproducible from the processed input dataset using the command above.

## Review patch: complete release and refresh behavior

The same command also regenerates `coverage_reconciliation.csv`,
`scenario_comparison.csv`, `tableau_reference_totals.csv`, and
`source_run_manifest.json` under the audit directory. Reference totals are
computed directly from the scenario facts and reconciled with size summaries.
The manifest records the actual source/code/output hashes, runtime versions,
Git revision, dirty-worktree status, parameters, and passed quality checks.

Existing output files are protected. Use new output directories for a new run,
or explicitly add `--overwrite` after preserving the accepted outputs. The local
patch runner backs up the prior WP1 outputs before using this option.

The loader preserves identifiers as text and checks schema, Boolean flags,
normalized key uniqueness, actual NAICS values, positive core exposure,
nonnegative/integer case fields, DART components, and source coordinates.
Invalid core rows already excluded by upstream flags remain excluded; contradictory
true flags stop the run. Every source year appears in coverage for both scenarios,
including zero-row scenarios. Empty-cohort rates remain missing, not zero.

Independent post-run verification:

```bash
uv run --locked python scripts/verify_wp1_release.py
```

Only the local verification script's successful full test run establishes the
current checkout's project-wide test result. Earlier test counts are historical.
