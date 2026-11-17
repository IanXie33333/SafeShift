"""Independently verify annual WP1 release files against the cleaned source."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(left, right, keys, fields):
    left = left.sort_values(keys).reset_index(drop=True)[keys + fields]
    right = right.sort_values(keys).reset_index(drop=True)[keys + fields]
    pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=False,
                                  rtol=1e-12, atol=1e-9)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/warehouses_4931.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/research_v2"))
    parser.add_argument("--audit-dir", type=Path, default=Path("artifacts/research_v2/annual"))
    parser.add_argument("--previous-summary", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.audit_dir / "source_run_manifest.json").read_text())
    assert manifest["source_sha256"] == digest(args.input), "Input hash changed"
    assert manifest["analysis_version"] == "wp1-review-fix-v1"
    root = Path(__file__).resolve().parents[1]
    for name, expected in manifest["code_sha256"].items():
        assert digest(root / "src/analysis" / name) == expected, f"Code changed: {name}"
    assert len(manifest["outputs"]) == 6
    assert manifest["qa_checks"] and all(manifest["qa_checks"].values())
    for name, entry in manifest["outputs"].items():
        path = (args.output_dir if name in {"annual_size_summary.csv", "annual_coverage.csv"}
                else args.audit_dir) / name
        assert digest(path) == entry["sha256"], f"Output hash changed: {name}"
        assert len(pd.read_csv(path)) == entry["rows"], f"Output row count changed: {name}"
    raw = pd.read_csv(args.input, dtype={"establishment_id": "string"}, low_memory=False)
    flags = [raw[c].astype(str).str.lower().isin(["true", "1"]) for c in
             ["is_naics_4931", "core_fields_valid", "establishment_year_unique"]]
    primary = raw.loc[flags[0] & flags[1] & flags[2]].copy()
    primary["size_group"] = pd.cut(primary.annual_average_employees,
                                    bins=[0, 50, 250, 1000, float("inf")], right=False,
                                    labels=["lt_50", "50_249", "250_999", "1000_plus"])
    sensitivity = primary.loc[(primary.total_hours_worked / primary.annual_average_employees)
                              .between(100, 8784)].copy()
    fact = pd.concat([primary.assign(scenario="primary"),
                      sensitivity.assign(scenario="exposure_sensitivity")])
    fields = {"establishment_year_count": ("year", "size"),
              "employee_count_sum": ("annual_average_employees", "sum"),
              "hours_sum": ("total_hours_worked", "sum"),
              "dafw_case_count": ("total_dafw_cases", "sum"),
              "djtr_case_count": ("total_djtr_cases", "sum"),
              "dart_case_count": ("dart_count", "sum")}
    keys = ["year", "size_group", "scenario"]
    expected = fact.groupby(keys, observed=True).agg(**fields).reset_index()
    expected["size_group"] = expected.size_group.astype(str)
    expected["dart_rate"] = 200000 * expected.dart_case_count / expected.hours_sum.where(
        expected.hours_sum.gt(0))
    summary = pd.read_csv(args.output_dir / "annual_size_summary.csv")
    assert not summary.duplicated(keys).any(), "Repeated summary key"
    compare(summary, expected, keys, [*fields, "dart_rate"])
    for prefix in ["dafw", "djtr"]:
        assert summary[f"{prefix}_days_sum"].isna().all(), "Unreviewed day totals exported"
        assert summary[f"{prefix}_days_status"].eq("blocked_review").all()
    coverage = pd.read_csv(args.output_dir / "annual_coverage.csv")
    assert len(coverage) == 2 * raw.year.nunique()
    assert not coverage.duplicated(["year", "scenario"]).any()
    assert coverage.sensitivity_records.notna().all()
    assert coverage.exposure_excluded.notna().all()
    assert coverage.input_records.eq(coverage.primary_records + coverage.structurally_excluded).all()
    assert coverage.primary_records.eq(coverage.sensitivity_records + coverage.exposure_excluded).all()
    grid = pd.MultiIndex.from_product([sorted(raw.year.unique()), ["exposure_sensitivity", "primary"]],
                                      names=["year", "scenario"])
    ref_fields = {k: v for k, v in fields.items() if k != "employee_count_sum"}
    direct = fact.groupby(["year", "scenario"], observed=True).agg(**ref_fields).reindex(
        grid, fill_value=0).reset_index()
    direct["dart_rate_reference"] = 200000 * direct.dart_case_count / direct.hours_sum.where(
        direct.hours_sum.gt(0))
    reference = pd.read_csv(args.audit_dir / "tableau_reference_totals.csv")
    compare(reference, direct, ["year", "scenario"], [*ref_fields, "dart_rate_reference"])
    pd.testing.assert_frame_equal(coverage, pd.read_csv(args.audit_dir / "coverage_reconciliation.csv"))
    audit = pd.read_csv(args.audit_dir / "day_anomaly_audit.csv")
    assert audit.review_case_count.eq(audit.dart_count).all()
    if args.previous_summary:
        previous = pd.read_csv(args.previous_summary)
        compare(summary, previous, keys, [*fields, "dart_rate"])
        print("Original WP1 counts, exposures, size groups, scenarios, and rates are unchanged.")
    assert np.isclose(summary.loc[summary.scenario.eq("primary"),
                                  "establishment_year_count"].sum(), len(primary))
    print(f"Verified: {len(primary):,} primary, {len(sensitivity):,} sensitivity, "
          f"{len(summary)} summary rows; six output hashes and source/code hashes match.")
    print(f"Day audit: {len(audit)} measure-level flags; all day totals remain blocked.")


if __name__ == "__main__":
    main()
