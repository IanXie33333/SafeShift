# SafeShift

SafeShift analyzes historical OSHA Injury Tracking Application data to study
workplace injury burden in Warehousing and Storage (NAICS 4931). The project
combines establishment-year forecasting with injury-narrative classification
and communicates results through reproducible analysis and a Tableau dashboard.

## Repository layout

- `configs/`: source and pipeline configuration
- `data/`: local raw, interim, and processed data; large data files are ignored by Git
- `docs/`: decisions, data documentation, cleaning records, and meeting notes
- `notebooks/`: exploratory analysis only
- `src/`: reusable ingestion, validation, cleaning, modeling, and export code
- `tests/`: automated tests and small synthetic fixtures
- `artifacts/`: metrics, figures, and model cards
- `tableau/`, `reports/`, and `slides/`: final communication products

## Data setup

The authoritative raw-data snapshot is stored outside GitHub in the team's
shared Google Drive. Download it into `data/raw/` without editing the source
files. See [`data/README.md`](data/README.md) for the expected layout.

Raw OSHA files, full processed datasets, local databases, credentials, model
caches, and restricted Tableau extracts must not be committed.

## Run the annual-summary cleaning pipeline

With Python 3.12 and `uv` installed:

```bash
uv sync --extra dev
uv run python src/cleaning/clean_ita_data.py
```

The pipeline reads CSV files recursively below `data/raw/` and writes generated
outputs to `data/processed/`. Use `--help` to view optional path overrides.

## Collaboration

- Do not push directly to `main`.
- Use a short-lived branch such as `feat/ita-cleaning`.
- Open a pull request and obtain at least one approval before merging.
- Use commit prefixes such as `feat:`, `fix:`, `test:`, `docs:`, and `chore:`.
