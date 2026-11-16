"""Tests for annual warehouse establishment analysis."""

from pathlib import Path

import pandas as pd

from src.analysis.annual_establishments import (
    create_day_anomaly_audit,
    create_scenarios,
    flag_high_days_per_case,
    load_primary_cohort,
    summarize_annual,
    valid_day_values,
)


# Test that DART rate is calculated using total hours.
def test_dart_rate_uses_total_hours():
    """DART rate must use aggregate cases and hours."""

    data = pd.DataFrame({
        "year": [2024, 2024],
        "size_group": ["lt_50", "lt_50"],
        "scenario": ["primary", "primary"],
        "id": [1, 2],
        "dart_count": [10, 20],
        "total_dafw_cases": [6, 12],
        "total_djtr_cases": [4, 8],
        "total_hours_worked": [100_000, 400_000],
        "annual_average_employees": [25, 30],
    })

    result = summarize_annual(data)

    assert len(result) == 1
    assert result.iloc[0]["establishment_year_count"] == 2
    assert result.iloc[0]["dafw_case_count"] == 18
    assert result.iloc[0]["djtr_case_count"] == 12
    assert result.iloc[0]["dart_case_count"] == 30
    assert result.iloc[0]["hours_sum"] == 500_000
    assert result.iloc[0]["dart_rate"] == 12.0
    assert pd.isna(result.iloc[0]["dafw_days_sum"])
    assert pd.isna(result.iloc[0]["djtr_days_sum"])
    assert result.iloc[0]["dafw_days_status"] == "blocked_review"
    assert result.iloc[0]["djtr_days_status"] == "blocked_review"


# Test that employee counts map to the correct size groups.
def test_size_group_boundaries(tmp_path: Path):
    """Check that employee counts map to the correct size groups."""

    employees = [1, 49, 50, 249, 250, 999, 1000]

    data = pd.DataFrame({
        "is_naics_4931": [True] * 7,
        "core_fields_valid": [True] * 7,
        "establishment_year_unique": [True] * 7,
        "annual_average_employees": employees,
    })

    # The loader now validates the complete cleaned-input contract.
    data["id"] = range(1, 8)
    data["year"] = 2024
    data["establishment_id"] = [str(i) for i in range(1, 8)]
    data["naics_code"] = "493110"
    data["establishment_name"] = "Synthetic"
    data["source_file"] = "synthetic.csv"
    data["source_record"] = range(1, 8)
    data["total_hours_worked"] = data["annual_average_employees"] * 2000
    data["total_dafw_cases"] = 1
    data["total_djtr_cases"] = 1
    data["dart_count"] = 2
    data["total_dafw_days"] = 1
    data["total_djtr_days"] = 1
    input_path = tmp_path / "test_warehouses.csv"
    data.to_csv(input_path, index=False)

    result = load_primary_cohort(input_path)

    assert result["size_group"].astype(str).tolist() == [
        "lt_50",
        "lt_50",
        "50_249",
        "50_249",
        "250_999",
        "250_999",
        "1000_plus",
    ]


# Test that exposure sensitivity includes only valid exposure ranges.
def test_exposure_sensitivity_boundaries():
    """Keep only records within the inclusive exposure thresholds."""

    data = pd.DataFrame({
        "id": [1, 2, 3, 4, 5, 6],
        "annual_average_employees": [10] * 6,
        "total_hours_worked": [
            990,       # 99 hours/employee: exclude
            1000,      # 100: include
            20000,     # 2000: include
            87840,     # 8784: include
            87850,     # 8785: exclude
            0,         # zero exposure: exclude
        ],
    })

    result = create_scenarios(data)

    primary = result[result["scenario"] == "primary"]
    sensitivity = result[result["scenario"] == "exposure_sensitivity"]

    assert len(primary) == 6
    assert len(sensitivity) == 3
    assert sensitivity["id"].tolist() == [2, 3, 4]


# Test that valid day values include zeros and exclude invalid values.
def test_valid_day_values():
    """Valid zeros count; missing, negative, and fractional days do not."""
    values = pd.Series([0, 12, None, -5, 2.5, 55_555_555])

    result = valid_day_values(values)

    assert result.tolist() == [
        True,
        True,
        False,
        False,
        False,
        True,
    ]


# Test that day eligibility counts include only valid day values.
def test_day_eligibility_counts():
    """Count valid day records and their matched DART cases."""
    data = pd.DataFrame({
        "year": [2024, 2024, 2024],
        "size_group": ["lt_50"] * 3,
        "scenario": ["primary"] * 3,
        "id": [1, 2, 3],
        "annual_average_employees": [10, 20, 30],
        "total_hours_worked": [20_000, 40_000, 60_000],
        "total_dafw_cases": [2, 1, 3],
        "total_djtr_cases": [1, 1, 2],
        "dart_count": [3, 2, 5],
        "total_dafw_days": [10, 0, None],
        "total_djtr_days": [None, 4, 2.5],
    })

    result = summarize_annual(data)
    row = result.iloc[0]

    assert row["dafw_days_eligible_establishment_years"] == 2
    assert row["dafw_days_cohort_dart_count"] == 5

    assert row["djtr_days_eligible_establishment_years"] == 1
    assert row["djtr_days_cohort_dart_count"] == 2

    assert pd.isna(row["dafw_days_sum"])
    assert pd.isna(row["djtr_days_sum"])
    assert row["dafw_days_status"] == "blocked_review"
    assert row["djtr_days_status"] == "blocked_review"


# Test that high days per case are flagged.
def test_flag_high_days_per_case():
    """Flag values above 180 days per reported case."""
    days = pd.Series([100, 180, 181, 500, 0, 100])
    cases = pd.Series([1, 1, 1, 2, 1, 0])

    result = flag_high_days_per_case(days, cases)

    assert result.tolist() == [
        False,  # 100 / 1 = 100
        False,  # 180 / 1 = 180 (boundary)
        True,   # 181 / 1 = 181
        True,   # 500 / 2 = 250
        False,  # Zero days
        False,  # Zero cases (requires separate review)
    ]


# Test that suspicious day values are audited.
def test_create_day_anomaly_audit():
    """Audit suspicious values without excluding records."""
    data = pd.DataFrame({
        "year": [2024, 2024, 2024],
        "establishment_id": [101, 102, 103],
        "establishment_name": ["A", "B", "C"],
        "source_file": ["test.csv"] * 3,
        "source_record": [1, 2, 3],
        "total_dafw_days": [200, 10, 0],
        "total_dafw_cases": [1, 1, 0],
        "total_djtr_days": [0, 300, 20],
        "total_djtr_cases": [0, 0, 1],
        "dart_count": [1, 1, 1],
    })

    audit = create_day_anomaly_audit(data)

    assert len(audit) == 4
    assert set(audit["measure"]) == {"dafw", "djtr", "combined"}

    dafw = audit[audit["measure"] == "dafw"].iloc[0]
    assert dafw["establishment_id"] == 101
    assert dafw["reported_days"] == 200
    assert dafw["high_days_per_case"]
    assert not dafw["positive_days_zero_cases"]

    djtr = audit[audit["measure"] == "djtr"].iloc[0]
    assert djtr["establishment_id"] == 102
    assert djtr["reported_days"] == 300
    assert djtr["high_days_per_case"]
    assert not djtr["positive_days_zero_cases"]
    assert djtr["review_case_count"] == 1

    assert (audit["disposition"] == "pending_review").all()


# Test that day totals remain blocked.
def test_day_totals_remain_blocked():
    """Unreviewed day totals must not be published."""
    data = pd.DataFrame({
        "year": [2024],
        "size_group": ["lt_50"],
        "scenario": ["primary"],
        "id": [1],
        "annual_average_employees": [25],
        "total_hours_worked": [50_000],
        "total_dafw_cases": [1],
        "total_djtr_cases": [1],
        "dart_count": [2],
        "total_dafw_days": [55_555_555],
        "total_djtr_days": [12],
    })

    result = summarize_annual(data)
    row = result.iloc[0]

    assert pd.isna(row["dafw_days_sum"])
    assert pd.isna(row["djtr_days_sum"])
    assert row["dafw_days_status"] == "blocked_review"
    assert row["djtr_days_status"] == "blocked_review"


# Test that coverage counts reconcile.

def test_coverage_reconciliation(tmp_path):
    """Every input row is accounted for in the coverage report."""
    from src.analysis.annual_establishments import (
        summarize_coverage,
    )

    raw = pd.DataFrame({
        "year": [2024, 2024, 2024],
        "id": [1, 2, 3],
        "is_naics_4931": [True, True, True],
        "core_fields_valid": [True, True, False],
        "establishment_year_unique": [True, True, True],
    })

    scenarios = pd.DataFrame({
        "year": [2024, 2024, 2024],
        "scenario": [
            "primary",
            "primary",
            "exposure_sensitivity",
        ],
        "id": [1, 2, 1],
        "dart_count": [1, 2, 1],
        "total_hours_worked": [2000, 4000, 2000],
        "total_dafw_days": [5, 10, 5],
        "total_djtr_days": [0, 2, 0],
    })

    coverage = summarize_coverage(scenarios, raw)
    primary = coverage[coverage["scenario"] == "primary"]

    assert primary.iloc[0]["input_records"] == 3
    assert primary.iloc[0]["primary_records"] == 2
    assert primary.iloc[0]["structurally_excluded"] == 1
    assert primary.iloc[0]["sensitivity_records"] == 1
    assert primary.iloc[0]["exposure_excluded"] == 1

    assert (
        primary["input_records"]
        == primary["primary_records"] + primary["structurally_excluded"]
    ).all()

    assert (
        primary["primary_records"]
        == primary["sensitivity_records"] + primary["exposure_excluded"]
    ).all()


# Test that summary totals match coverage totals.

def test_summary_matches_coverage():
    """Size-group totals must match coverage totals."""
    from src.analysis.annual_establishments import summarize_coverage

    raw = pd.DataFrame({
        "year": [2024, 2024, 2024],
        "id": [1, 2, 3],
        "is_naics_4931": [True, True, True],
        "core_fields_valid": [True, True, False],
        "establishment_year_unique": [True, True, True],
    })

    scenarios = pd.DataFrame({
        "year": [2024, 2024, 2024],
        "size_group": ["lt_50", "50_249", "lt_50"],
        "scenario": [
            "primary",
            "primary",
            "exposure_sensitivity",
        ],
        "id": [1, 2, 1],
        "annual_average_employees": [25, 100, 25],
        "total_hours_worked": [50_000, 200_000, 50_000],
        "total_dafw_cases": [1, 2, 1],
        "total_djtr_cases": [1, 1, 1],
        "dart_count": [2, 3, 2],
        "total_dafw_days": [5, 10, 5],
        "total_djtr_days": [0, 2, 0],
    })

    summary = summarize_annual(scenarios)
    coverage = summarize_coverage(scenarios, raw)

    assert len(summary) == 3
    assert not summary.duplicated(
        ["year", "size_group", "scenario"]
    ).any()

    totals = (
        summary.groupby(["year", "scenario"])[
            "establishment_year_count"
        ]
        .sum()
        .reset_index()
    )

    check = totals.merge(
        coverage[["year", "scenario", "establishment_years"]],
        on=["year", "scenario"],
        validate="one_to_one",
    )

    assert len(check) == 2
    assert (
        check["establishment_year_count"]
        == check["establishment_years"]
    ).all()
