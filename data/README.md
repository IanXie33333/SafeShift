# Data setup

Large source and generated datasets are stored outside GitHub. The team's shared
Google Drive is the authoritative source for the frozen raw-data snapshot.

## Local layout

Place OSHA ITA files below `data/raw/`. The cleaning script searches recursively,
so the recommended organization is:

```text
data/raw/
└── osha_ita/
    ├── 2016/ITA Data 2016.csv
    ├── 2017/ITA Data 2017.csv
    ├── ...
    ├── 2024/ITA Data 2024.csv
    └── 2025/ITA Data 2025.csv
```

Case-detail files may use the same year folders. The annual-summary cleaner will
inventory and skip them because narrative data require a separate pipeline.

## Rules

1. Never edit or overwrite a raw source file.
2. Keep the shared Drive copy read-only as the team's source of truth.
3. Do not commit raw, interim, or full processed datasets to GitHub.
4. Commit source URLs, retrieval dates, checksums, schemas, scripts, tests, and
   documentation instead.
5. A small synthetic test fixture or safe aggregate may be committed after review.

Run the current cleaning pipeline from the repository root:

```bash
uv run python src/cleaning/clean_ita_data.py
```

Generated files are written to `data/processed/`.
