"""Input validation and reproducible release outputs for annual descriptive WP1."""

from __future__ import annotations

import hashlib
import json
import platform
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

FLAGS = ["is_naics_4931", "core_fields_valid", "establishment_year_unique"]
SCENARIOS = ["exposure_sensitivity", "primary"]
IDENTIFIERS = ["id", "establishment_id", "naics_code", "source_file", "establishment_name"]
CORE = ["annual_average_employees", "total_hours_worked", "total_dafw_cases",
        "total_djtr_cases", "dart_count"]
REQUIRED = FLAGS + IDENTIFIERS + CORE + [
    "year", "source_record", "total_dafw_days", "total_djtr_days"]
ADDITIVE = {"establishment_year_count": ("id", "size"),
            "employee_count_sum": ("annual_average_employees", "sum"),
            "hours_sum": ("total_hours_worked", "sum"),
            "dafw_case_count": ("total_dafw_cases", "sum"),
            "djtr_case_count": ("total_djtr_cases", "sum"),
            "dart_case_count": ("dart_count", "sum")}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_days(values):
    values = pd.to_numeric(values, errors="coerce")
    return values.notna() & np.isfinite(values) & values.ge(0) & values.mod(1).eq(0)


def read_validated_input(path):
    raw = pd.read_csv(path, dtype={c: "string" for c in IDENTIFIERS},
                      keep_default_na=False, low_memory=False)
    require(not (set(REQUIRED) - set(raw)),
            f"Missing required columns: {sorted(set(REQUIRED) - set(raw))}")
    require(len(raw) > 0, "The annual input is empty")
    for flag in FLAGS:
        values = raw[flag].astype("string").str.strip().str.lower()
        require(values.isin(["true", "false", "1", "0"]).all(),
                f"Invalid or missing Boolean flag: {flag}")
        raw[flag] = values.isin(["true", "1"])
    for field in CORE + ["year", "source_record"]:
        raw[field] = pd.to_numeric(raw[field], errors="coerce")
    for field in ["total_dafw_days", "total_djtr_days"]:
        missing = raw[field].astype("string").str.strip().str.lower().isin(
            ["", "na", "n/a", "none", "null", "nan"])
        raw[field] = raw[field].mask(missing)
    require((valid_days(raw.year) & raw.year.between(2016, 2025)).all(),
            "Every source row needs an integer reporting year in 2016–2025")
    raw["year"] = raw.year.astype(int)
    ids = raw.establishment_id.str.strip()
    valid_id = ids.str.fullmatch(r"[0-9]+").fillna(False) & ids.str.contains(r"[1-9]")
    keys = pd.DataFrame({"year": raw.year, "establishment_id": ids.str.lstrip("0")})
    unique = valid_id & ~keys.duplicated(["year", "establishment_id"], keep=False)
    require(raw.establishment_year_unique.eq(unique).all(),
            "establishment_year_unique disagrees with actual normalized keys")
    naics = raw.naics_code.str.strip()
    valid_naics = naics.str.fullmatch(r"[1-9][0-9]{5}").fillna(False)
    require(raw.is_naics_4931.eq(valid_naics & naics.str.startswith("4931")).all(),
            "is_naics_4931 disagrees with the actual six-digit NAICS code")
    trusted = raw.core_fields_valid
    numeric_valid = pd.Series(True, index=raw.index)
    for field in CORE:
        values = raw[field]
        valid = values.notna() & np.isfinite(values) & values.ge(0)
        if field != "total_hours_worked":
            valid &= values.mod(1).eq(0)
        numeric_valid &= valid
    numeric_valid &= raw.annual_average_employees.gt(0) & raw.total_hours_worked.gt(0)
    require((~trusted | (numeric_valid & valid_id & valid_naics)).all(),
            "A core-valid row has invalid keys, counts, employees, or hours")
    require((~trusted | raw.dart_count.eq(raw.total_dafw_cases + raw.total_djtr_cases)).all(),
            "Stored DART count disagrees with DAFW plus DJTR cases")
    if "no_injuries_illnesses" in raw:
        no_cases = raw.no_injuries_illnesses.astype("string").str.strip().isin(["2", "2.0"])
        require((~trusted | ~no_cases | raw.dart_count.eq(0)).all(),
                "A core-valid row contradicts its no-injury indicator")
    selected = raw[FLAGS].all(axis=1)
    traceable = (raw.source_file.str.strip().ne("") & valid_days(raw.source_record)
                 & raw.source_record.gt(0))
    require((~selected | traceable).all(), "Eligible rows need valid source coordinates")
    require(not raw.loc[selected].duplicated(["source_file", "source_record"]).any(),
            "Eligible rows repeat source coordinates")
    return raw


def day_audit(primary):
    """DART-based review flags, plus invalid values and a separate combined screen."""
    audits = []
    away = pd.to_numeric(primary.total_dafw_days, errors="coerce")
    restricted = pd.to_numeric(primary.total_djtr_days, errors="coerce")
    both_valid = valid_days(primary.total_dafw_days) & valid_days(primary.total_djtr_days)
    for measure, values, cases in [
        ("dafw", primary.total_dafw_days, primary.total_dafw_cases),
        ("djtr", primary.total_djtr_days, primary.total_djtr_cases),
        ("combined", (away + restricted).where(both_valid), primary.dart_count),
    ]:
        numeric = pd.to_numeric(values, errors="coerce")
        invalid = (~valid_days(values) if measure != "combined"
                   else pd.Series(False, index=primary.index))
        high = valid_days(values) & primary.dart_count.gt(0) & numeric.gt(180 * primary.dart_count)
        zero_dart = numeric.gt(0) & primary.dart_count.eq(0)
        flagged = high | zero_dart | invalid
        columns = ["year", "establishment_id", "establishment_name", "source_file",
                   "source_record", "dart_count"]
        records = primary.loc[flagged, columns].copy()
        records["reported_days"] = values.loc[flagged]
        records["reported_cases"] = cases.loc[flagged]
        records["measure"] = measure
        records["review_case_count"] = primary.dart_count.loc[flagged]
        records["high_days_per_case"] = high.loc[flagged]
        records["positive_days_zero_cases"] = zero_dart.loc[flagged]
        records["invalid_day_value"] = invalid.loc[flagged]
        records["disposition"] = "pending_review"
        audits.append(records)
    return pd.concat(audits, ignore_index=True)


def destinations(output_dir, audit_dir):
    return {"annual_size_summary.csv": output_dir / "annual_size_summary.csv",
            "annual_coverage.csv": output_dir / "annual_coverage.csv",
            **{name: audit_dir / name for name in ["day_anomaly_audit.csv",
               "coverage_reconciliation.csv", "scenario_comparison.csv",
               "tableau_reference_totals.csv", "source_run_manifest.json"]}}


def preflight(input_path, paths, overwrite):
    resolved = {p.resolve() for p in paths.values()}
    require(len(resolved) == len(paths), "Output destinations collide")
    require(input_path.resolve() not in resolved, "An output would overwrite the input")
    existing = [str(p) for p in paths.values() if p.exists()]
    if existing and not overwrite:
        raise FileExistsError("Outputs already exist; choose new directories or pass --overwrite: "
                              + ", ".join(existing))


def direct_reference(scenarios, years):
    grid = pd.MultiIndex.from_product([sorted(years), SCENARIOS], names=["year", "scenario"])
    fields = {k: v for k, v in ADDITIVE.items() if k != "employee_count_sum"}
    result = scenarios.groupby(["year", "scenario"], observed=True).agg(**fields).reindex(
        grid, fill_value=0).reset_index()
    result["dart_rate_reference"] = 200000 * result.dart_case_count / result.hours_sum.where(
        result.hours_sum.gt(0))
    return result


def comparison(summary):
    metrics = ["establishment_year_count", "hours_sum", "dart_case_count", "dart_rate"]
    wide = summary.set_index(["year", "size_group", "scenario"])[metrics].unstack("scenario")
    wide = wide.reindex(columns=pd.MultiIndex.from_product([metrics, SCENARIOS]))
    for metric in metrics[:-1]:
        for scenario in SCENARIOS:
            wide[(metric, scenario)] = wide[(metric, scenario)].fillna(0)
    wide.columns = [f"{metric}_{scenario}" for metric, scenario in wide.columns]
    wide = wide.reset_index()
    wide["excluded_establishment_years"] = (wide.establishment_year_count_primary
                                             - wide.establishment_year_count_exposure_sensitivity)
    wide["dart_rate_difference"] = wide.dart_rate_exposure_sensitivity - wide.dart_rate_primary
    return wide


def validate_exports(scenarios, summary, coverage, reference):
    require(not summary.duplicated(["year", "size_group", "scenario"]).any(),
            "Duplicate annual summary keys")
    require(summary.dart_case_count.eq(summary.dafw_case_count + summary.djtr_case_count).all(),
            "Summary DART components do not reconcile")
    require(coverage.input_records.eq(coverage.primary_records + coverage.structurally_excluded).all(),
            "Input-to-primary coverage does not reconcile")
    require(coverage.primary_records.eq(coverage.sensitivity_records + coverage.exposure_excluded).all(),
            "Primary-to-sensitivity coverage does not reconcile")
    grouped = summary.groupby(["year", "scenario"], observed=True)[list(ADDITIVE)].sum()
    direct = scenarios.groupby(["year", "scenario"], observed=True).agg(**ADDITIVE)
    pd.testing.assert_frame_equal(grouped, direct, check_dtype=False, check_exact=False,
                                  rtol=1e-12, atol=1e-9)
    expected = reference.set_index(["year", "scenario"]).establishment_year_count
    require(coverage.set_index(["year", "scenario"]).establishment_years.eq(expected).all(),
            "Coverage differs from direct cohort counts")
    rate = 200000 * summary.dart_case_count / summary.hours_sum.where(summary.hours_sum.gt(0))
    require(np.allclose(summary.dart_rate, rate, equal_nan=True), "Pooled-rate check failed")
    for prefix in ["dafw", "djtr"]:
        require(summary[f"{prefix}_days_sum"].isna().all(), "Unreviewed day sums exported")
        require(summary[f"{prefix}_days_status"].eq("blocked_review").all(), "Day status changed")
    return {"input_validated": True, "unique_summary_keys": True, "coverage_reconciles": True,
            "direct_totals_reconcile": True, "pooled_rates_reconcile": True,
            "day_totals_remain_blocked": True}


def git_value(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def write_release(args, raw, scenarios, summary, coverage, audit, source_sha, module_path):
    reference = direct_reference(scenarios, raw.year.unique())
    checks = validate_exports(scenarios, summary, coverage, reference)
    frames = {"annual_size_summary.csv": summary, "annual_coverage.csv": coverage,
              "day_anomaly_audit.csv": audit, "coverage_reconciliation.csv": coverage,
              "scenario_comparison.csv": comparison(summary), "tableau_reference_totals.csv": reference}
    paths = destinations(args.output_dir, args.audit_dir)
    payloads = {name: frame.to_csv(index=False).encode("utf-8") for name, frame in frames.items()}
    require(file_hash(args.input) == source_sha, "Input changed during analysis")
    manifest = {"analysis_version": "wp1-review-fix-v1", "source_file": str(args.input),
                "source_sha256": source_sha, "source_rows": len(raw),
                "source_rows_by_year": {str(k): int(v) for k, v in raw.groupby("year").size().items()},
                "run_created_utc": datetime.now(UTC).isoformat(),
                "python_version": platform.python_version(), "pandas_version": pd.__version__,
                "numpy_version": np.__version__, "git_revision": git_value("rev-parse", "HEAD"),
                "git_worktree_dirty": bool(git_value("status", "--porcelain")),
                "code_sha256": {"annual_establishments.py": file_hash(module_path),
                                "annual_review_utils.py": file_hash(Path(__file__))},
                "run_command": shlex.join(["python", "-m", "src.analysis.annual_establishments",
                                            *sys.argv[1:]]),
                "exposure_hours_per_employee_inclusive": [100, 8784],
                "day_status": "blocked_review", "day_review_denominator": "dart_count",
                "qa_checks": checks,
                "outputs": {name: {"path": str(paths[name]), "rows": len(frames[name]),
                   "sha256": hashlib.sha256(value).hexdigest()} for name, value in payloads.items()}}
    payloads["source_run_manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    for name, value in payloads.items():
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].write_bytes(value)
    return checks
