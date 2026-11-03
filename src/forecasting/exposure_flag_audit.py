from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "count_regression"

pairs = pd.read_csv(DATA_DIR / "forecasting_reference.csv")
warehouses = pd.read_csv(DATA_DIR / "warehouses_4931.csv")

# Identify exposure-flagged warehouse records
flagged = warehouses[
    warehouses["quality_flags"].str.contains(
        r"zero_hours|zero_employees",
        na=False
    )
].copy()

# Identify all establishment-years used in forecasting
pair_years = pd.concat([
    pairs[["establishment_id", "feature_year"]].rename(
        columns={"feature_year": "year"}
    ),
    pairs[["establishment_id", "target_year"]].rename(
        columns={"target_year": "year"}
    )
]).drop_duplicates()

# Match flagged records against forecasting years
comparison = flagged.merge(
    pair_years,
    on=["establishment_id", "year"],
    how="left",
    indicator=True
)

# Summarize results
audit_summary = pd.DataFrame({
    "metric": [
        "Forecasting pairs",
        "Flagged warehouse records",
        "Unique flagged establishments",
        "Flagged establishments appearing in forecasting",
        "Flagged records used in forecasting",
        "Flagged records excluded from forecasting"
    ],
    "value": [
        len(pairs),
        len(flagged),
        flagged["establishment_id"].nunique(),
        len(
            set(flagged["establishment_id"].dropna())
            & set(pairs["establishment_id"].dropna())
        ),
        (comparison["_merge"] == "both").sum(),
        (comparison["_merge"] == "left_only").sum()
    ]
})

year_summary = (
    comparison.groupby("year")
    .agg(
        flagged_records=("establishment_id", "size"),
        used_in_forecasting=(
            "_merge",
            lambda x: (x == "both").sum()
        )
    )
    .reset_index()
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

audit_summary.to_csv(
    OUTPUT_DIR / "exposure_flag_audit_summary.csv",
    index=False
)

year_summary.to_csv(
    OUTPUT_DIR / "exposure_flag_audit_by_year.csv",
    index=False
)

print(audit_summary.to_string(index=False))
print("\nExposure flag audit saved successfully")
