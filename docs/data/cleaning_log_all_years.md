# Cleaning log: OSHA annual summaries, 2016–2025

**Run date:** September 28, 2026
**Script:** `src/cleaning/clean_ita_data.py`
**Status:** Completed successfully

## Files processed

Processed the ten `ITA Data [year].csv` summary files below `data/raw/`.
The three case-detail files for 2023–2025 were listed as skipped because they
contain individual incidents and require separate cleaning. Raw files were not
edited. This run used the existing local files; no download or upload was performed.

## Before and after

All cleaned records use the same **42 columns**. No rows were removed.

| Year | Rows before | Rows after | Columns before | Columns after | Warehouse rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2016 | 214,978 | 214,978 | 31 | 42 | 4,463 |
| 2017 | 259,758 | 259,758 | 31 | 42 | 5,041 |
| 2018 | 289,534 | 289,534 | 31 | 42 | 6,151 |
| 2019 | 290,475 | 290,475 | 31 | 42 | 6,431 |
| 2020 | 293,391 | 293,391 | 31 | 42 | 6,803 |
| 2021 | 317,978 | 317,978 | 31 | 42 | 7,117 |
| 2022 | 346,799 | 346,799 | 31 | 42 | 7,937 |
| 2023 | 394,234 | 394,234 | 32 | 42 | 9,328 |
| 2024 | 398,620 | 398,620 | 32 | 42 | 9,885 |
| 2025 | 383,283 | 383,283 | 32 | 42 | 9,238 |
| **Total** | **3,189,050** | **3,189,050** | — | — | **72,394** |

Warehouse counts are rows with valid six-digit NAICS codes starting with `4931`.
They include repeated records and are not counts of unique establishments.

## Changes made

- Standardized column order and reporting-year name: `year_filing_for` became `year`.
- Trimmed surrounding spaces, uppercased state abbreviations, and normalized
  integer-like ID/category values such as `123.00` to `123`, including the 2019 formatting.
- Kept IDs, ZIP codes, and category codes as text. Removed leading zeros from
  numeric establishment IDs and padded short numeric ZIPs to five digits.
- Converted employee counts, hours, injury/illness counts, and days to numbers.
  The precise output types are in `data/processed/data_dictionary.csv`.
- Added blank `naics_year` values for 2016–2022, where that field was absent.
  No NAICS version was guessed and no industry crosswalk was applied.
- Added `dart_count` and `dart_rate`. DART count is days-away cases plus
  job-transfer/restriction cases. The rate uses positive hours only.
- Added eight tracking/review fields: `source_file`, `source_record`,
  `is_naics_4931`, `core_fields_valid`, `establishment_year_unique`,
  `candidate_for_linkage`, `needs_review`, and `quality_flags`.
- No other current source field was dropped. Records were stacked across years;
  establishments were not matched across years.

The 2018 file required the CP1252 text-reading fallback. This is recorded in the
run manifest; text should still be spot-checked.

## Missing values and unusual numbers

Missing values were not filled with zero or averages. Invalid numeric values
were left blank in the cleaned numeric columns and flagged. Zero injury counts
were retained. Zero hours and employees were retained and flagged.

Key missing inputs were **16 hours values**, **3 employee counts**,
**3 days-away case counts**, and **3 transfer/restriction case counts**.
Other column-level missingness is recorded in `data/processed/column_profile.csv`.

DART stays blank if either component is missing. DART rate stays blank when
DART is missing or hours are missing, zero, or invalid. Negative counts/hours
were not changed to positive values.

## Quality findings

**44,729 rows received at least one review flag.** Counts below overlap because
one row can have several problems. This table lists the main findings; all checks
and their counts are in `data/processed/quality_summary.csv`.

| Finding | Affected rows |
| --- | ---: |
| Zero hours | 11,719 |
| Missing hours | 16 |
| Negative hours | 2 |
| Zero employees | 14,790 |
| Missing employees | 3 |
| Missing days-away case count | 3 |
| Missing transfer/restriction case count | 3 |
| Negative days-away or transfer/restriction case count | 0 |
| Negative total-injury count | 2 |
| Negative other-recordable-case count | 1 |
| Invalid or missing ZIP format | 16,411 |
| Unknown NAICS version | 2,676 |
| DART exceeds average employees | 1,405 |
| No-injury indicator conflicts with positive DART | 74 |
| Missing or invalid reporting year | 6 |
| Rows in repeated establishment-year groups | 9,406 |
| Exact duplicate rows | 0 |

## Duplicates and filters

**Duplicate rows removed: 0.** Repeated establishment-year records were retained
and flagged, rather than choosing one automatically. Repeats occurred in 2016,
2017, 2018, 2020, 2021, and 2023. None occurred in the 2024 summary.

The full cleaned table includes every industry and every parsed summary row.
A separate warehouse file applies the `4931` filter; it also keeps flagged rows.
Eligibility columns are preliminary checks, not row-deletion rules or final
modeling approval.

## Output files

- `data/processed/summary_cleaned.csv`: all 3,189,050 standardized summary records.
- `data/processed/warehouses_4931.csv`: 72,394 warehouse records.
- `data/processed/rows_for_review.csv`: 44,729 flagged records.
- `data/processed/inventory.csv`: per-file counts and available columns.
- `data/processed/column_profile.csv`: original missingness and observed types.
- `data/processed/quality_summary.csv`: counts for each quality check.
- `data/processed/data_dictionary.csv`: definitions for the 42 output fields.
- `data/processed/run_manifest.json`: completion status and source/script hashes.

The warehouse and review files are subsets of the full table, not additional records.

## Questions still requiring review

- Which repeated establishment-year record should be used when values conflict?
- Should zero-hour or zero-employee records enter the forecasting dataset?
- How should the six malformed/missing-year records in the 2025 summary be handled?
- Can invalid industry versions, ZIPs, or other suspect values be corrected from the source?
- Are establishment IDs reliable for matching across years?

The completed run retained all records. Saved-output checks confirmed row totals,
DART calculations, and the warehouse count. The current script matches the version
recorded in the run manifest. Detailed rules are in `cleaning_decisions_all_years.md`.
