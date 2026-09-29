# Cleaning decisions and log: all annual summary files

Script: `src/cleaning/clean_ita_data.py`
Documented run: September 28, 2026

## Purpose

Prepare the annual OSHA summary files for Work Package 1: make their formats
consistent, calculate DART, count records, and identify problems for review.
The rules come from the project plan and OSHA dictionaries. Formatting choices
and preliminary eligibility checks are documented below for team review.

## How the script handles the files

| Files below `data/raw/` | What happens |
| --- | --- |
| `ITA Data 2016.csv` through `ITA Data 2025.csv` | Each file is cleaned separately using the same rules, then its rows are added to one combined table. |
| `Case Detail Data 2023.csv`, `2024.csv`, and `2025.csv` | Recognized from their columns and listed as skipped. Incident narratives need a separate cleaning process. |
| Dictionary PDFs | Reference material; the script does not read or modify them. |

The script recursively reads CSVs below `data/raw/`, checks their headers, and records
their columns, row counts, and observed data types. It stops on an unrecognized
CSV, missing required columns, or multiple summary files for the same year.
One summary filename must contain one clear reporting year.

The combined table stacks annual records. It does not match establishments across
years, combine repeated records, or train a forecasting model. Raw files stay unchanged.

## Cleaning rules applied to every summary year

| Item | Decision |
| --- | --- |
| Column names | Use lowercase names and underscores. Standardize the reporting-year field as `year`. |
| Text | Remove surrounding spaces and uppercase state abbreviations. Do not fuzzy-match names or addresses. |
| IDs and codes | Read as text first. Remove zero decimal suffixes, such as `123.00` → `123`. Remove leading zeros from numeric establishment IDs. |
| ZIP codes | Keep as text; pad short numeric ZIPs to five digits. |
| Numeric fields | Convert employees, hours, injury/illness counts, and days to numbers. Fractional case/day/employee counts are flagged and left blank. |
| Missing or invalid numbers | Recognize blanks, NA, N/A, null, none, and nan. Missing, nonnumeric, infinite, or negative numeric values become blank and receive a flag. Never replace them with zero. |
| Zero values | Retain zero injury counts. Retain and flag zero hours and zero employees. |
| DART count | Add `total_dafw_cases + total_djtr_cases` for each row. If either is missing, DART stays blank. |
| DART rate | Calculate `dart_count × 200,000 / total_hours_worked` only when hours are positive; round to six decimals. |
| Duplicates | Flag exact duplicate rows and repeated establishment IDs within the same year. Keep all affected records; remove none. |
| NAICS 4931 | Mark rows with a valid six-digit code starting with `4931`. Keep all industries in the full table and also save a warehouse subset. |
| Industry version and size | Preserve the source categories. Leave unavailable `naics_year` values blank; do not invent a version or treat size codes as employee counts. |
| Reporting year | Use the record's reporting year. A filename year is a flagged fallback only if the entire year column is absent. Do not fill isolated missing years automatically. |
| Traceability | Add `source_file` and `source_record` so a cleaned row can be traced to its original CSV record. |

The current files use `total_hours_worked`. The script does not assume an unfamiliar
name such as `annual_average_hours` means the same thing; that requires a dictionary check.

## What the quality flags mean

`quality_flags` lists each row's problems; `needs_review` indicates at least one flag.
Examples include missing addresses, invalid ZIP formats, unknown industry versions,
and DART counts exceeding average employees. A flag does not prove a record is wrong.

The script also adds provisional checks:

- `core_fields_valid`: valid year/ID/NAICS format, valid DART components, positive
  hours and employees, and no conflict between positive DART and a no-injury indicator.
- `establishment_year_unique`: a valid year/ID combination appears once in that year.
- `candidate_for_linkage`: passes both checks above. This is not final model approval.

These checks do not remove rows. The team still decides which records to use.

## Recorded results

Every output row uses the same **42-column schema**. The year field was renamed,
10 calculated/provenance/quality columns were added, and older files received a
blank `naics_year` column. No other current source field was dropped.

| Year | Rows before | Rows after | Columns before | NAICS 4931 rows |
| --- | ---: | ---: | ---: | ---: |
| 2016 | 214,978 | 214,978 | 31 | 4,463 |
| 2017 | 259,758 | 259,758 | 31 | 5,041 |
| 2018 | 289,534 | 289,534 | 31 | 6,151 |
| 2019 | 290,475 | 290,475 | 31 | 6,431 |
| 2020 | 293,391 | 293,391 | 31 | 6,803 |
| 2021 | 317,978 | 317,978 | 31 | 7,117 |
| 2022 | 346,799 | 346,799 | 31 | 7,937 |
| 2023 | 394,234 | 394,234 | 32 | 9,328 |
| 2024 | 398,620 | 398,620 | 32 | 9,885 |
| 2025 | 383,283 | 383,283 | 32 | 9,238 |
| **Total** | **3,189,050** | **3,189,050** | — | **72,394** |

**Rows removed: 0. Duplicate rows removed: 0. Rows needing review: 44,729.**
Warehouse totals count rows, not deduplicated establishments.

## Files produced in `data/processed/`

| Output | Contains |
| --- | --- |
| `summary_cleaned.csv` | All annual summary rows in one consistent format. |
| `warehouses_4931.csv` | Only NAICS 4931 rows, including flagged records. |
| `rows_for_review.csv` | Copies of rows with quality flags. |
| `inventory.csv` | Yearly counts, available columns, and skipped files. |
| `column_profile.csv` | Original missingness and observed types by column and file. |
| `quality_summary.csv` | Counts for each quality check, including duplicates and invalid values. |
| `data_dictionary.csv` | Definitions and intended types for all 42 output columns. |
| `run_manifest.json` | Run status, source hashes, and script version hash. |

The three data tables overlap; do not add their row counts together.
