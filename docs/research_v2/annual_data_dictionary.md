
# WP1 — Annual Data Dictionary

## 1. Annual Size Summary

**File:** `data/processed/research_v2/annual_size_summary.csv`

**Unit of observation:** One year × establishment size group × analytical scenario.

### Grouping Columns

| Column | Definition |
|---|---|
| `year` | OSHA ITA reporting year |
| `size_group` | Establishment size category based on annual average employees |
| `size_group_order` | Numeric ordering of size groups for visualization |
| `scenario` | Analytical cohort: `primary` or `exposure_sensitivity` |

### Establishment and Exposure Columns

| Column | Definition |
|---|---|
| `establishment_year_count` | Number of eligible establishment-year records in the group |
| `employee_count_sum` | Sum of reported annual average employees |
| `hours_sum` | Sum of reported total hours worked |

### Injury Case Columns

| Column | Definition |
|---|---|
| `dafw_case_count` | Sum of cases involving days away from work |
| `djtr_case_count` | Sum of cases involving job transfer or restriction |
| `dart_case_count` | Sum of DAFW and DJTR cases |
| `dart_rate` | DART cases per 100 full-time-equivalent workers, calculated using aggregate hours |

### Reported Day Columns

| Column | Definition |
|---|---|
| `dafw_days_sum` | Sum of reported DAFW days; currently withheld pending review |
| `djtr_days_sum` | Sum of reported DJTR days; currently withheld pending review |
| `dafw_days_eligible_establishment_years` | Number of records passing basic DAFW day-value validation |
| `djtr_days_eligible_establishment_years` | Number of records passing basic DJTR day-value validation |
| `dafw_days_cohort_dart_count` | DART case count among records passing basic DAFW day-value validation |
| `djtr_days_cohort_dart_count` | DART case count among records passing basic DJTR day-value validation |
| `dafw_days_status` | Publication status of DAFW day totals |
| `djtr_days_status` | Publication status of DJTR day totals |

### Interpretation Notes

- Establishment counts represent establishment-years, not necessarily distinct establishments across multiple years.
- Employee counts and hours are additive within each reporting group.
- DART rates use aggregate case counts and hours rather than averaging establishment-level rates.
- Day-value eligibility is provisional and does not mean a record has passed anomaly review.
- Day totals remain null while their status is `blocked_review`.
- Day measures represent reported days, not hours or financial costs.

## 2. Annual Coverage Report

**File:** `data/processed/research_v2/annual_coverage.csv`

**Unit of observation:** One reporting year × analytical scenario.

The coverage report contains 20 rows: 10 reporting years and 2 scenarios.

### Grouping Columns

| Column | Definition |
|---|---|
| `year` | OSHA ITA reporting year |
| `scenario` | Analytical cohort: `primary` or `exposure_sensitivity` |

### Cohort Coverage Columns

| Column | Definition |
|---|---|
| `establishment_years` | Number of establishment-year records included in the scenario |
| `input_records` | Number of input records for the reporting year |
| `primary_records` | Number of records retained in the primary cohort |
| `structurally_excluded` | Input records excluded from the primary cohort |
| `sensitivity_records` | Primary records retained after exposure filtering |
| `exposure_excluded` | Primary records excluded by exposure sensitivity criteria |

### Missingness Columns

| Column | Definition |
|---|---|
| `dart_missing` | Number of scenario records with missing DART case counts |
| `hours_missing` | Number of scenario records with missing hours-worked values |
| `days_away_missing` | Number of scenario records with missing reported DAFW days |
| `restricted_days_missing` | Number of scenario records with missing reported DJTR days |

### Reconciliation Rules

The following relationships must hold for each reporting year:

`input_records = primary_records + structurally_excluded`

`primary_records = sensitivity_records + exposure_excluded`

The sum of `establishment_year_count` across size groups must equal `establishment_years` for each year and scenario.

### Interpretation Notes

- Structural exclusions and exposure exclusions represent different filtering stages.
- Missingness counts describe the records retained within each scenario.
- Missingness alone does not capture all invalid or anomalous values.
- The report does not yet provide separate counts for every individual exclusion reason.

## 3. Day-Metric Anomaly Audit

**File:** `artifacts/research_v2/annual/day_anomaly_audit.csv`

**Unit of observation:** One flagged establishment-year and day measure.

### Record Identification

| Column | Definition |
|---|---|
| `year` | OSHA ITA reporting year |
| `establishment_id` | Establishment identifier in the processed dataset |
| `establishment_name` | Reported establishment name |
| `source_file` | Original OSHA ITA source file |
| `source_record` | Source-record reference for tracing the observation |

### Injury and Day Measures

| Column | Definition |
|---|---|
| `reported_days` | Reported day count for the flagged measure |
| `reported_cases` | Corresponding injury case count |
| `dart_count` | Total DAFW and DJTR cases |
| `measure` | Day measure being evaluated: DAFW or DJTR |

### Screening and Review

| Column | Definition |
|---|---|
| `high_days_per_case` | Whether reported days exceed 180 per corresponding case |
| `positive_days_zero_cases` | Whether reported days are positive with zero corresponding cases |
| `disposition` | Review status, initially `pending_review` |

### Interpretation Notes

- Screening flags identify observations requiring investigation, not confirmed errors.
- A single establishment-year may appear more than once if both day measures are flagged.
- Source references support tracing observations back to OSHA ITA records.
- No automatic capping, replacement, or exclusion is applied to flagged day values.
- DAFW and DJTR day totals remain blocked pending review.
