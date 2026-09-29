# Project decisions

Record decisions here when they affect project scope, definitions, data handling,
evaluation, privacy, or reproducibility.

## 2026-09-28 — Repository data policy

- Raw OSHA files remain unchanged and are not committed to GitHub.
- The team-shared Google Drive holds the authoritative raw and full processed data.
- Each member works with a local copy below `data/raw/` and writes generated data
  below `data/processed/`.
- GitHub stores code, tests, source metadata, schemas, checksums, safe aggregates,
  and documentation.

## 2026-09-28 — Annual-summary cleaning policy

- Cleaning retains every parsed summary row and flags questionable records.
- Missing and invalid numeric values are not silently replaced with zero.
- NAICS 4931 is marked as the preliminary warehouse cohort.
- Establishment linkage and final modeling eligibility remain later decisions.

See `docs/data/cleaning_decisions_all_years.md` for the detailed rules.
