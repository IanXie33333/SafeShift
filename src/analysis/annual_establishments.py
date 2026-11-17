"""Annual warehouse establishment patterns, 2016–2025."""

import argparse
from pathlib import Path

import pandas as pd

from src.analysis.annual_review_utils import (
    day_audit,
    destinations,
    file_hash,
    preflight,
    read_validated_input,
    write_release,
)

SIZE_LABELS = [
    "lt_50",
    "50_249",
    "250_999",
    "1000_plus",
]


# Day value validation function
def valid_day_values(values: pd.Series) -> pd.Series:
    """Identify nonmissing, nonnegative, whole-number day values."""
    numeric = pd.to_numeric(values, errors="coerce")

    return (
        numeric.notna()
        & (numeric >= 0)
        & (numeric % 1 == 0)
    )


# High days per case flag function
def flag_high_days_per_case(
    days: pd.Series,
    cases: pd.Series,
    threshold: float = 180,
) -> pd.Series:
    """Flag day counts exceeding 180 days per reported case."""
    numeric_days = pd.to_numeric(days, errors="coerce")
    numeric_cases = pd.to_numeric(cases, errors="coerce")

    return (
        (numeric_days > 0)
        & (numeric_cases > 0)
        & (numeric_days > threshold * numeric_cases)
    )


# Day anomaly audit function
def create_day_anomaly_audit(primary: pd.DataFrame) -> pd.DataFrame:
    """Audit DART-based day review signals without excluding case/rate records."""
    return day_audit(primary)


# Primary cohort loading function
def load_primary_cohort(input_path: Path) -> pd.DataFrame:
    """Load structurally eligible warehouse-year records."""
    df = read_validated_input(input_path)

    eligible = (
        df["is_naics_4931"]
        & df["core_fields_valid"]
        & df["establishment_year_unique"]
    )

    primary = df.loc[eligible].copy()

    primary["size_group"] = pd.cut(
        primary["annual_average_employees"],
        bins=[0, 50, 250, 1000, float("inf")],
        labels=SIZE_LABELS,
        right=False,
    )

    if primary["size_group"].isna().any():
        raise ValueError("Some eligible records have no size group")

    return primary


# Scenario creation function
def create_scenarios(primary: pd.DataFrame) -> pd.DataFrame:
    """Create primary and exposure-sensitivity analysis cohorts."""
    primary = primary.copy()
    primary["scenario"] = "primary"

    employees = primary["annual_average_employees"]
    hours = primary["total_hours_worked"]

    hours_per_employee = hours / employees

    valid_exposure = (
        (employees > 0)
        & (hours > 0)
        & (hours_per_employee >= 100)
        & (hours_per_employee <= 8784)
    )

    sensitivity = primary.loc[valid_exposure].copy()
    sensitivity["scenario"] = "exposure_sensitivity"

    return pd.concat([primary, sensitivity], ignore_index=True)


# Annual summary function
def summarize_annual(scenarios: pd.DataFrame) -> pd.DataFrame:
    """Aggregate warehouse-year records by year, size, and scenario."""

    scenarios = scenarios.copy()

    for prefix, column in [
        ("dafw", "total_dafw_days"),
        ("djtr", "total_djtr_days"),
    ]:
        # Include valid zeros, but exclude missing and malformed values.
        if column in scenarios.columns:
            eligible = valid_day_values(scenarios[column])
        else:
            eligible = pd.Series(False, index=scenarios.index)

        scenarios[f"{prefix}_days_eligible"] = eligible.astype(int)

        scenarios[f"{prefix}_days_eligible_dart"] = (
            scenarios["dart_count"].where(eligible, 0)
        )

    summary = (
        scenarios.groupby(
            ["year", "size_group", "scenario"],
            observed=True,
        )
        .agg(
            establishment_year_count=("id", "size"),
            employee_count_sum=("annual_average_employees", "sum"),
            hours_sum=("total_hours_worked", "sum"),
            dafw_case_count=("total_dafw_cases", "sum"),
            djtr_case_count=("total_djtr_cases", "sum"),
            dart_case_count=("dart_count", "sum"),
            dafw_days_eligible_establishment_years=(
                "dafw_days_eligible", "sum"
            ),
            djtr_days_eligible_establishment_years=(
                "djtr_days_eligible", "sum"
            ),
            dafw_days_cohort_dart_count=(
                "dafw_days_eligible_dart", "sum"
            ),
            djtr_days_cohort_dart_count=(
                "djtr_days_eligible_dart", "sum"
            ),
        )
        .reset_index()
    )

    size_order = {
        "lt_50": 1,
        "50_249": 2,
        "250_999": 3,
        "1000_plus": 4,
    }

    summary["size_group_order"] = (
        summary["size_group"].map(size_order).astype(int)
    )

    summary["dart_rate"] = (
        200_000 * summary["dart_case_count"]
        / summary["hours_sum"].where(summary["hours_sum"] > 0)
    )

    summary["dafw_days_sum"] = float("nan")
    summary["djtr_days_sum"] = float("nan")

    summary["dafw_days_status"] = "blocked_review"
    summary["djtr_days_status"] = "blocked_review"

    return summary


# Coverage summary function

# Coverage summary function
def summarize_coverage(
    scenarios: pd.DataFrame,
    raw: pd.DataFrame,
) -> pd.DataFrame:
    """Count eligible warehouse-year records by year and scenario."""
    grid = pd.MultiIndex.from_product(
        [sorted(raw["year"].unique()), ["exposure_sensitivity", "primary"]],
        names=["year", "scenario"],
    )
    coverage = (
        scenarios.groupby(["year", "scenario"])
        .agg(
            establishment_years=("id", "size"),
            contributing_hours=("total_hours_worked", "sum"),
            dart_missing=("dart_count", lambda x: x.isna().sum()),
            hours_missing=("total_hours_worked", lambda x: x.isna().sum()),
            days_away_missing=("total_dafw_days", lambda x: x.isna().sum()),
            dafw_days_available=("total_dafw_days", lambda x: valid_day_values(x).sum()),
            restricted_days_missing=("total_djtr_days", lambda x: x.isna().sum()),
            djtr_days_available=("total_djtr_days", lambda x: valid_day_values(x).sum()),
        )
        .reindex(grid, fill_value=0)
        .reset_index()
    )

    input_counts = raw.groupby("year").size().rename("input_records")

    flags = [
        "is_naics_4931",
        "core_fields_valid",
        "establishment_year_unique",
    ]

    failed = ~raw[flags].astype(bool)

    exclusion_counts = (
        failed.assign(year=raw["year"])
        .groupby("year")
        .sum()
        .rename(columns={
            "is_naics_4931": "excluded_naics",
            "core_fields_valid": "excluded_core_fields",
            "establishment_year_unique": "excluded_duplicate_key",
        })
        .reset_index()
    )

    primary_counts = (
        scenarios.loc[scenarios["scenario"] == "primary"]
        .groupby("year")
        .size()
        .rename("primary_records")
    )

    coverage = coverage.merge(
        input_counts,
        on="year",
        how="left",
        validate="many_to_one",
    )

    coverage = coverage.merge(
        primary_counts,
        on="year",
        how="left",
        validate="many_to_one",
    )

    coverage["primary_records"] = coverage["primary_records"].fillna(0).astype(int)

    # Add exclusion counts by reason
    coverage = coverage.merge(
        exclusion_counts,
        on="year",
        how="left",
        validate="many_to_one",
    )

    coverage["structurally_excluded"] = (
        coverage["input_records"] - coverage["primary_records"]
    )

    sensitivity_counts = (
        scenarios.loc[
            scenarios["scenario"] == "exposure_sensitivity"
        ]
        .groupby("year")
        .size()
        .rename("sensitivity_records")
    )

    coverage = coverage.merge(
        sensitivity_counts,
        on="year",
        how="left",
        validate="many_to_one",
    )

    coverage["sensitivity_records"] = coverage["sensitivity_records"].fillna(0).astype(int)
    coverage["exposure_excluded"] = (
        coverage["primary_records"]
        - coverage["sensitivity_records"]
    )

    return coverage


# Main function.
def main() -> None:
    """Generate annual summary, coverage, and anomaly audit CSVs."""
    parser = argparse.ArgumentParser(
        description="Generate annual warehouse establishment summaries."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/warehouses_4931.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/research_v2"),
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=Path("artifacts/research_v2/annual"),
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace this module's outputs explicitly")
    args = parser.parse_args()

    input_path = args.input
    output_dir = args.output_dir

    audit_dir = args.audit_dir
    preflight(input_path, destinations(output_dir, audit_dir), args.overwrite)
    source_sha = file_hash(input_path)
    raw = read_validated_input(input_path)
    primary = load_primary_cohort(input_path)
    scenarios = create_scenarios(primary)
    summary = summarize_annual(scenarios)
    coverage = summarize_coverage(scenarios, raw)
    audit = create_day_anomaly_audit(primary)
    write_release(args, raw, scenarios, summary, coverage, audit, source_sha, Path(__file__))

    print(f"Annual summary: {len(summary)} rows")
    print(f"Annual coverage: {len(coverage)} rows")
    print(f"Outputs saved to {output_dir}")
    print(f"Day anomaly audit: {len(audit)} flagged rows")
    print(f"Audit saved to {audit_dir}")
    print("Seven release files generated; reconciliation passed; day sums remain blocked.")

# Entry point for the script.
if __name__ == "__main__":
    main()
