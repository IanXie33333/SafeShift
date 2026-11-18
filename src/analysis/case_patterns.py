"""Descriptive warehouse case profiles from the compact raw-field export."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[2]
MECHANISMS = {
    "transportation": "Transportation",
    "falls_slips_trips": "Falls, slips and trips",
    "harmful_exposure": "Harmful exposure",
    "object_equipment_contact": "Contact with objects or equipment",
    "overexertion_bodily_reaction": "Overexertion and bodily reaction",
    "other_reported_mechanism": "Other reported mechanisms",
    "unknown_missing_mechanism": "Unknown mechanism",
}
MONTHS = {name: i for i, name in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
REQUIRED = ["source_year", "source_record", "source_id", "establishment_id", "case_number",
            "naics_code", "incident_date_raw", "incident_outcome_raw", "dafw_days_raw",
            "djtr_days_raw", "soc_code_raw", "soc_description_raw", "soc_reviewed_raw",
            "soc_probability_raw", "event_code_raw", "event_title_raw"]
OUTCOMES = {"1": "death", "2": "dafw", "3": "djtr", "4": "other"}
DIMENSIONS = ["year", "mechanism_group", "mechanism_label", "mechanism_order",
              "soc_major", "soc_major_label", "scenario"]
MISSING = {"", "na", "n/a", "null", "none", "nan"}


def require(value, message):
    if not value:
        raise ValueError(message)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def code_text(series):
    return series.astype("string").fillna("").str.strip().str.replace(
        r"^([0-9]+)\.0+$", r"\1", regex=True)


def missing(series):
    return series.astype("string").fillna("").str.strip().str.lower().isin(MISSING)


def valid_days(series):
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.notna() & np.isfinite(numeric) & numeric.ge(0) & numeric.mod(1).eq(0)


def parse_date(value, year):
    try:
        if year == 2023:
            match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
            if match:
                month, day, yyyy = match.groups()
                return date(int(yyyy), int(month), int(day))
            return None
        match = re.fullmatch(r"(\d{1,2})([A-Za-z]{3})(\d{4})", value)
        if match:
            day, month, yyyy = match.groups()
            return date(int(yyyy), MONTHS[month.upper()], int(day))
    except (KeyError, ValueError):
        return None
    return None


def load_export(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        require({"source_manifest.json", "case_fields_2023.csv", "case_fields_2024.csv"} <= names,
                "Compact export is missing its manifest or a source-year CSV")
        manifest = json.loads(archive.read("source_manifest.json"))
        sources = {int(s["source_year"]): s for s in manifest["sources"]}
        frames = []
        for year in [2023, 2024]:
            with archive.open(f"case_fields_{year}.csv") as stream:
                frame = pd.read_csv(stream, dtype=str, keep_default_na=False)
            require(not (set(REQUIRED) - set(frame)),
                    f"Missing case fields for {year}: {sorted(set(REQUIRED) - set(frame))}")
            require(code_text(frame.source_year).eq(str(year)).all(), "Source year mismatch")
            require(len(frame) == sources[year]["warehouse_rows"], "Export row count mismatch")
            frame["year"] = year
            frame["raw_source_sha256"] = sources[year]["source_sha256"]
            frames.append(frame)
    return pd.concat(frames, ignore_index=True), manifest


def map_mechanisms(frame, mapping):
    lookup = pd.read_csv(mapping, dtype=str, keep_default_na=False)
    require(not lookup.duplicated(["source_year", "event_code_raw"]).any(),
            "Mechanism mapping repeats a source-year/code key")
    expected = {(int(r.source_year), r.event_code_raw): r for r in lookup.itertuples(index=False)}
    groups, issues = [], []
    for year, code, title in zip(frame.year, code_text(frame.event_code_raw), frame.event_title_raw, strict=True):
        if code.lower() in MISSING:
            groups.append("unknown_missing_mechanism")
            continue
        item = expected.get((int(year), code))
        if item is None or normalized_title(item.source_title) != normalized_title(title):
            issues.append({"year": year, "code": code, "title": title})
            groups.append("unreviewed_mapping")
        else:
            groups.append(item.proposed_label or "other_reported_mechanism")
    return pd.Series(groups, index=frame.index), pd.DataFrame(issues)


def normalized_title(value):
    return " ".join(str(value).split()).casefold()


def prepare_cases(raw, mapping, soc_reference):
    frame = raw.copy()
    for field in REQUIRED:
        frame[field] = frame[field].astype("string").fillna("").str.strip()
    require(code_text(frame.naics_code).str.fullmatch(r"4931[0-9]{2}").all(),
            "Compact export contains non-warehouse NAICS codes")
    positions = pd.to_numeric(frame.source_record, errors="coerce")
    require((valid_days(positions) & positions.gt(0)).all(), "Invalid source-row coordinates")
    require(not frame.duplicated(["year", "source_record"]).any(), "Repeated source-row coordinates")
    ids_present = ~missing(frame.source_id)
    require(not frame.loc[ids_present].duplicated(["year", "source_id"]).any(),
            "Repeated source IDs; do not deduplicate without review")
    frame["record_id"] = [f"{y}:{identifier}" if present else f"{y}:row:{position}"
                          for y, identifier, position, present in
                          zip(frame.year, frame.source_id, frame.source_record, ids_present, strict=True)]
    require(not frame.record_id.duplicated().any(), "Derived report identity is not unique")
    frame["incident_date"] = [parse_date(value, int(year)) for value, year in
                              zip(frame.incident_date_raw, frame.year, strict=True)]
    incident_year = frame.incident_date.map(lambda value: value.year if value else -1)
    frame["date_invalid"] = frame.incident_date.isna()
    frame["date_year_mismatch"] = ~frame.date_invalid & incident_year.ne(frame.year)
    frame["primary_eligible"] = ~frame.date_invalid & ~frame.date_year_mismatch
    frame["mechanism_group"], mapping_issues = map_mechanisms(frame, mapping)
    if not mapping_issues.empty:
        return frame, mapping_issues
    frame["mechanism_label"] = frame.mechanism_group.map(MECHANISMS)
    frame["mechanism_order"] = frame.mechanism_group.map(
        {key: n for n, key in enumerate(MECHANISMS, 1)})
    majors = pd.read_csv(soc_reference, dtype=str, keep_default_na=False)
    major_labels = dict(zip(majors.soc_major, majors.soc_major_label, strict=True))
    soc = code_text(frame.soc_code_raw)
    compact = soc.str.replace("-", "", regex=False)
    unassigned = compact.isin(["0", "0000", "000000"])
    uncodable = compact.isin(["9999", "999999"])
    recognized = soc.str.fullmatch(r"(?:[0-9]{2}-[0-9]{4}|[0-9]{6})").fillna(False)
    major_valid = recognized & compact.str[:2].isin(major_labels)
    frame["soc_status"] = np.select(
        [np.asarray(c.fillna(False), dtype=bool)
         for c in [missing(soc), unassigned, uncodable, major_valid]],
        ["missing", "unassigned", "uncodable", "major_group_validated"],
        default="format_or_major_requires_review")
    reviewed = code_text(frame.soc_reviewed_raw)
    frame["soc_review_status_conflict"] = major_valid & reviewed.eq("2")
    usable = major_valid & ~frame.soc_review_status_conflict
    frame["soc_major"] = compact.str[:2].where(usable, "unknown")
    frame["soc_major_label"] = frame.soc_major.map(major_labels).fillna("Unknown occupation")
    confidence = pd.to_numeric(frame.soc_probability_raw, errors="coerce")
    frame["soc_assignment_status"] = np.select(
        [np.asarray(c.fillna(False), dtype=bool) for c in
         [confidence.eq(5), confidence.between(0, 1), missing(frame.soc_probability_raw)]],
        ["osha_reassigned_indicator_5", "ordinary_probability", "missing_probability"],
        default="probability_requires_review")
    outcome = code_text(frame.incident_outcome_raw)
    frame["outcome"] = outcome.map(OUTCOMES).fillna("unknown")
    for prefix in ["dafw", "djtr"]:
        value = frame[f"{prefix}_days_raw"]
        frame[f"{prefix}_days_valid"] = valid_days(value)
        frame[f"{prefix}_days"] = pd.to_numeric(value, errors="coerce").where(valid_days(value))
    frame["day_review_flag"] = (frame.dafw_days.gt(180) | frame.djtr_days.gt(180)
                                 | (frame.dafw_days + frame.djtr_days).gt(180))
    frame["outcome_day_review_flag"] = (
        (frame.outcome.eq("dafw") & frame.dafw_days.eq(0))
        | (frame.outcome.isin(["djtr", "other"]) & frame.dafw_days.gt(0))
        | (frame.outcome.eq("other") & frame.djtr_days.gt(0)))
    return frame, mapping_issues


def make_scenarios(frame):
    primary = frame.loc[frame.primary_eligible].copy()
    sensitivity = primary.loc[~primary.day_review_flag].copy()
    return pd.concat([primary.assign(scenario="primary"),
                      sensitivity.assign(scenario="day_review_sensitivity")], ignore_index=True)


def read_policy(path, source_manifest):
    if path is None:
        return {key: {"status": "blocked_review", "reason": "Raw day-value disposition pending"}
                for key in ["dafw", "djtr"]}
    policy = json.loads(path.read_text())
    actual = {str(s["source_year"]): s["source_sha256"] for s in source_manifest["sources"]}
    require(policy["source_sha256_by_year"] == actual, "Day policy belongs to different raw sources")
    require(bool(policy.get("review_note")), "An accepted day policy needs a review note")
    for key in ["dafw", "djtr"]:
        require(policy["metrics"][key]["status"] in ["blocked_review", "accept_reported_values"],
                "Unknown day-policy status")
    return policy["metrics"]


def aggregate_cases(scenarios, policy):
    frame = scenarios.copy()
    frame["case_report_count"] = 1
    aggregation = {"case_report_count": ("case_report_count", "sum"),
                   "day_review_flag_report_count": ("day_review_flag", "sum")}
    for outcome in [*OUTCOMES.values(), "unknown"]:
        frame[f"outcome_{outcome}_count"] = frame.outcome.eq(outcome).astype(int)
        aggregation[f"outcome_{outcome}_count"] = (f"outcome_{outcome}_count", "sum")
    for key in ["dafw", "djtr"]:
        aggregation[f"{key}_days_known_report_count"] = (f"{key}_days_valid", "sum")
        aggregation[f"{key}_days_sum"] = (f"{key}_days", lambda x: x.sum(min_count=1))
    result = frame.groupby(DIMENSIONS, observed=True).agg(**aggregation).reset_index()
    for key in ["dafw", "djtr"]:
        known = f"{key}_days_known_report_count"
        result[f"{key}_days_invalid_or_missing_count"] = result.case_report_count - result[known]
        if policy[key]["status"] == "blocked_review":
            result[f"{key}_days_sum"] = np.nan
            result[f"{key}_days_status"] = "blocked_review"
        else:
            result[f"{key}_days_status"] = np.where(
                result[known].eq(result.case_report_count), "ready", "partial_valid_values")
    for key in ["case_report_count", "day_review_flag_report_count",
                *[c for c in result if c.endswith("_count")]]:
        result[key] = result[key].astype(int)
    return result


def coverage_table(frame, sources):
    rows = []
    for year in [2023, 2024]:
        raw = frame.loc[frame.year.eq(year)]
        primary = raw.loc[raw.primary_eligible]
        for scenario in ["primary", "day_review_sensitivity"]:
            selected = primary if scenario == "primary" else primary.loc[~primary.day_review_flag]
            key_complete = ~missing(raw.establishment_id) & ~missing(raw.case_number)
            row = {"year": year, "scenario": scenario,
                   "raw_all_industry_rows": sources[year]["raw_rows"],
                   "warehouse_source_reports": len(raw), "invalid_incident_date_reports": int(raw.date_invalid.sum()),
                   "incident_year_mismatch_reports": int(raw.date_year_mismatch.sum()),
                   "primary_reports": len(primary), "scenario_reports": len(selected),
                   "date_quarantined_reports": len(raw) - len(primary),
                   "day_sensitivity_excluded_reports": len(primary) - len(primary.loc[~primary.day_review_flag]),
                   "repeated_establishment_case_key_rows": int(raw.loc[key_complete].duplicated(
                       ["establishment_id", "case_number"], keep=False).sum()),
                   "unknown_occupation_reports": int(selected.soc_major.eq("unknown").sum()),
                   "unknown_mechanism_reports": int(selected.mechanism_group.eq("unknown_missing_mechanism").sum()),
                   "other_mechanism_reports": int(selected.mechanism_group.eq("other_reported_mechanism").sum()),
                   "outcome_unknown_reports": int(selected.outcome.eq("unknown").sum()),
                   "day_review_flag_reports": int(selected.day_review_flag.sum()),
                   "outcome_day_review_flag_reports": int(selected.outcome_day_review_flag.sum()),
                   "soc_reassignment_indicator_5_reports": int(selected.soc_assignment_status.eq(
                       "osha_reassigned_indicator_5").sum()),
                   "job_description_missing_reports": (int(selected.job_description_present.eq("0").sum())
                       if "job_description_present" in selected else None)}
            for prefix in ["dafw", "djtr"]:
                values = selected[f"{prefix}_days_raw"]
                numeric = pd.to_numeric(values, errors="coerce")
                finite = numeric.notna() & np.isfinite(numeric)
                row[f"{prefix}_missing_value_reports"] = int(missing(values).sum())
                row[f"{prefix}_nonnumeric_value_reports"] = int((~missing(values) & numeric.isna()).sum())
                row[f"{prefix}_nonfinite_value_reports"] = int((numeric.notna() & ~np.isfinite(numeric)).sum())
                row[f"{prefix}_negative_value_reports"] = int((finite & numeric.lt(0)).sum())
                row[f"{prefix}_fractional_nonnegative_value_reports"] = int((
                    finite & numeric.ge(0) & numeric.mod(1).ne(0)).sum())
                row[f"{prefix}_numeric_valid_reports"] = int(selected[f"{prefix}_days_valid"].sum())
                row[f"{prefix}_numeric_invalid_or_missing_reports"] = int((~selected[f"{prefix}_days_valid"]).sum())
                row[f"{prefix}_raw_valid_sum_audit_only"] = float(selected[f"{prefix}_days"].sum())
                row[f"{prefix}_raw_valid_max_audit_only"] = float(selected[f"{prefix}_days"].max()) if len(selected) else None
            rows.append(row)
    return pd.DataFrame(rows)


def verify(frame, scenarios, summary, coverage, policy):
    require(not summary.duplicated(["year", "mechanism_group", "soc_major", "scenario"]).any(),
            "Duplicate aggregate keys")
    outcome_fields = [f"outcome_{value}_count" for value in [*OUTCOMES.values(), "unknown"]]
    require(summary[outcome_fields].sum(axis=1).eq(summary.case_report_count).all(),
            "Outcomes do not sum to report counts")
    for subgroup in ["mechanism_group", "soc_major"]:
        keys = ["year", "scenario", subgroup]
        actual = summary.groupby(keys, observed=True).case_report_count.sum()
        direct = scenarios.groupby(keys, observed=True).size()
        pd.testing.assert_series_equal(actual, direct, check_names=False, check_dtype=False)
    for year in [2023, 2024]:
        year_rows = frame.loc[frame.year.eq(year)]
        require(len(year_rows) == int(year_rows.primary_eligible.sum())
                + int(year_rows.date_invalid.sum()) + int(year_rows.date_year_mismatch.sum()),
                "Date inclusion accounting does not reconcile")
        for scenario in ["primary", "day_review_sensitivity"]:
            selected = scenarios.loc[scenarios.year.eq(year) & scenarios.scenario.eq(scenario)]
            cells = summary.loc[summary.year.eq(year) & summary.scenario.eq(scenario)]
            require(int(cells.case_report_count.sum()) == len(selected), "Raw-to-aggregate frequency mismatch")
            c = coverage.loc[coverage.year.eq(year) & coverage.scenario.eq(scenario)].iloc[0]
            require(c.scenario_reports == len(selected), "Coverage mismatch")
            for key in ["dafw", "djtr"]:
                require(int(cells[f"{key}_days_known_report_count"].sum()) ==
                        int(selected[f"{key}_days_valid"].sum()), "Known-day denominators mismatch")
                require((cells[f"{key}_days_known_report_count"]
                         + cells[f"{key}_days_invalid_or_missing_count"]).eq(cells.case_report_count).all(),
                        "Day coverage does not reconcile")
                if policy[key]["status"] == "blocked_review":
                    require(cells[f"{key}_days_sum"].isna().all(), "Blocked days leaked")
                else:
                    require(np.isclose(cells[f"{key}_days_sum"].sum(), selected[f"{key}_days"].sum()),
                            "Day sums mismatch")
    return {"unique_keys": True, "date_reconciliation": True, "frequency_reconciliation": True,
            "outcome_reconciliation": True, "day_denominator_reconciliation": True,
            "raw_subgroup_reconciliation": True}


def run(args):
    outputs = {"case_pattern_summary.csv": args.output_dir / "case_pattern_summary.csv",
               "case_coverage.csv": args.output_dir / "case_coverage.csv",
               **{name: args.audit_dir / name for name in ["case_quality_checks.csv",
                  "case_classification_coverage.csv", "case_mechanism_totals.csv",
                  "case_occupation_totals.csv", "case_source_run_manifest.json"]}}
    if not args.overwrite and any(p.exists() for p in outputs.values()):
        raise FileExistsError("Case outputs exist; choose new directories or pass --overwrite")
    raw, metadata = load_export(args.case_fields_zip)
    frame, issues = prepare_cases(raw, args.label_map, args.soc_major_reference)
    if not issues.empty:
        args.audit_dir.mkdir(parents=True, exist_ok=True)
        path = args.audit_dir / "mechanism_mapping_issues.csv"
        issues.value_counts().rename("reports").reset_index().to_csv(path, index=False)
        raise ValueError(f"Unexpected source-year mechanism code/title; review {path}")
    policy = read_policy(args.day_policy, metadata)
    scenarios = make_scenarios(frame)
    summary = aggregate_cases(scenarios, policy)
    sources = {int(s["source_year"]): s for s in metadata["sources"]}
    coverage = coverage_table(frame, sources)
    checks = verify(frame, scenarios, summary, coverage, policy)
    classification = frame.groupby(["year", "soc_status", "soc_assignment_status"], observed=True).size().rename(
        "warehouse_source_reports").reset_index()
    mechanism = scenarios.groupby(["year", "mechanism_group", "mechanism_label", "scenario"],
                                   observed=True).size().rename("case_report_count").reset_index()
    occupations = scenarios.groupby(["year", "soc_major", "soc_major_label", "scenario"],
                                     observed=True).size().rename("case_report_count").reset_index()
    quality = coverage.copy()
    frames = {"case_pattern_summary.csv": summary, "case_coverage.csv": coverage,
              "case_quality_checks.csv": quality, "case_classification_coverage.csv": classification,
              "case_mechanism_totals.csv": mechanism, "case_occupation_totals.csv": occupations}
    payloads = {name: value.to_csv(index=False).encode("utf-8") for name, value in frames.items()}
    manifest = {"analysis_version": "case-patterns-v1", "created_utc": datetime.now(UTC).isoformat(),
                "python_version": sys.version.split()[0], "pandas_version": pd.__version__,
                "numpy_version": np.__version__, "module_sha256": file_hash(Path(__file__)),
                "git_revision": git_value("rev-parse", "HEAD"),
                "git_worktree_dirty": bool(git_value("status", "--porcelain")),
                "case_fields_zip_sha256": file_hash(args.case_fields_zip), "raw_sources": metadata["sources"],
                "label_map_sha256": file_hash(args.label_map),
                "soc_major_reference_sha256": file_hash(args.soc_major_reference),
                "day_policy_sha256": file_hash(args.day_policy) if args.day_policy else None,
                "soc_detail_membership": "Major groups validated; detailed code membership is not independently certified",
                "day_policy": policy, "qa_checks": checks,
                "outputs": {name: {"path": str(outputs[name]), "sha256": hashlib.sha256(value).hexdigest(),
                   "rows": len(frames[name])} for name, value in payloads.items()}}
    payloads["case_source_run_manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    for name, value in payloads.items():
        outputs[name].parent.mkdir(parents=True, exist_ok=True)
        outputs[name].write_bytes(value)
    print(f"Case profiles: {len(raw):,} source warehouse reports; "
          f"{int(frame.primary_eligible.sum()):,} date-aligned reports; {len(summary)} aggregate rows.")
    print("All case reconciliations passed. Day publication follows the recorded source-matched policy.")
    return frame, summary, coverage


def git_value(*args):
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-fields-zip", type=Path, required=True)
    parser.add_argument("--label-map", type=Path, default=PROJECT / "reference/nlp_label_map.csv")
    parser.add_argument("--soc-major-reference", type=Path,
                        default=PROJECT / "reference/soc_major_groups_2018.csv")
    parser.add_argument("--day-policy", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/research_v2"))
    parser.add_argument("--audit-dir", type=Path, default=Path("artifacts/research_v2/cases"))
    parser.add_argument("--overwrite", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"STOPPED: {error}", file=sys.stderr)
        raise SystemExit(1)
