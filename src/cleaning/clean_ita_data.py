#!/usr/bin/env python3
"""Standardize OSHA ITA annual summaries and produce a reproducible WP1 audit.

Run from the repository root: python src/cleaning/clean_ita_data.py
Requires pandas. Raw files are never modified. Case-detail CSVs are inventoried,
but deliberately not cleaned by this establishment-year pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {
    "establishment_id", "establishment_name", "street_address", "city", "state",
    "zip_code", "naics_code", "annual_average_employees", "total_hours_worked",
    "total_dafw_cases", "total_djtr_cases",
}
COUNTS = [
    "annual_average_employees", "total_deaths", "total_dafw_cases",
    "total_djtr_cases", "total_other_cases", "total_dafw_days", "total_djtr_days",
    "total_injuries", "total_skin_disorders", "total_respiratory_conditions",
    "total_poisonings", "total_hearing_loss", "total_other_illnesses",
]
MISSING_NUMERIC = {"", "na", "n/a", "null", "none", "nan"}
OUTPUT_COLUMNS = [
    "source_file", "source_record", "year", "id", "establishment_id",
    "establishment_name", "company_name", "ein", "street_address", "city",
    "state", "zip_code", "naics_code", "naics_year", "industry_description",
    "establishment_type", "size", "annual_average_employees", "total_hours_worked",
    "no_injuries_illnesses", "total_deaths", "total_dafw_cases", "total_djtr_cases",
    "total_other_cases", "total_dafw_days", "total_djtr_days", "total_injuries",
    "total_skin_disorders", "total_respiratory_conditions", "total_poisonings",
    "total_hearing_loss", "total_other_illnesses", "created_timestamp", "change_reason",
    "dart_count", "dart_rate", "is_naics_4931", "core_fields_valid",
    "establishment_year_unique", "candidate_for_linkage", "needs_review", "quality_flags",
]


def normalize_header(name: str) -> str:
    return re.sub(r"[\s-]+", "_", name.strip().lstrip("\ufeff").lower())


def normalize_integer_text(values: pd.Series) -> pd.Series:
    """Remove only a zero decimal suffix; do not round or parse IDs as floats."""
    return values.str.strip().str.replace(r"^([0-9]+)\.0+$", r"\1", regex=True)


def filename_year(path: Path) -> int | None:
    years = set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", path.stem))
    return int(next(iter(years))) if len(years) == 1 else None


def missing(values: pd.Series) -> pd.Series:
    return values.str.strip().str.lower().isin(MISSING_NUMERIC)


def read_csv(path: Path, *, header_only: bool = False) -> tuple[pd.DataFrame, str]:
    kwargs = dict(dtype=str, keep_default_na=False, skip_blank_lines=False,
                  on_bad_lines="error", nrows=0 if header_only else None)
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **kwargs), "utf-8-sig"
    except UnicodeDecodeError:
        # Any undefined CP1252 bytes become visible replacement characters and
        # are flagged below. No undecodable bytes are silently discarded.
        return pd.read_csv(path, encoding="cp1252", encoding_errors="replace", **kwargs), "cp1252 (replacement characters flagged)"


def clean_summary(raw: pd.DataFrame, source_name: str, expected_year: int | None):
    """Return all standardized rows, column profiles, and flag counts."""
    d = raw.copy().fillna("")
    d.columns = [normalize_header(c) for c in d.columns]
    if d.columns.duplicated().any():
        raise ValueError(f"{source_name}: duplicate column names after normalization")
    absent = REQUIRED - set(d.columns)
    if absent:
        raise ValueError(f"{source_name}: required columns missing: {sorted(absent)}")
    profiles = []
    for column in d:
        text = d[column].str.strip()
        number = pd.to_numeric(text.mask(missing(text)), errors="coerce")
        nonmissing = ~missing(text)
        profiles.append({
            "source_file": source_name, "column": column,
            "raw_dtype": "text (CSV)",
            "observed_type": "empty" if not nonmissing.any() else
                ("numeric-compatible text" if number[nonmissing].notna().all() else "text/mixed"),
            "rows": len(d), "missing_count": int(missing(text).sum()),
            "missing_percent": round(float(missing(text).mean() * 100), 4),
        })
        d[column] = text

    flags = pd.Series("", index=d.index, dtype=object)
    blocking = pd.Series(False, index=d.index)
    flag_counts = []

    def flag(mask, label, *, blocks=False):
        nonlocal flags, blocking
        mask = pd.Series(mask, index=d.index).fillna(False).astype(bool)
        if mask.any():
            flags.loc[mask] = flags.loc[mask] + label + ";"
        if blocks:
            blocking |= mask
        flag_counts.append({"source_file": source_name, "flag": label,
                            "rows": int(mask.sum()), "blocks_core_fields": blocks})

    # Duplicate rows are retained, and separately distinguished from ID conflicts.
    flag(raw.fillna("").duplicated(keep=False), "exact_duplicate_row")
    bad_text = pd.Series(False, index=d.index)
    for column in d:
        bad_text |= d[column].str.contains("\ufffd", regex=False)
    flag(bad_text, "text_decode_replacement")

    year_column = next((c for c in ["year_filing_for", "year_of_filing", "year"] if c in d), None)
    if year_column is None:
        if expected_year is None:
            raise ValueError(f"{source_name}: no reporting-year column or unambiguous filename year")
        year_text = pd.Series(str(expected_year), index=d.index)
        flag(pd.Series(True, index=d.index), "year_from_filename")
    else:
        year_text = normalize_integer_text(d[year_column])
    valid_year = year_text.str.fullmatch(r"20\d{2}")
    flag(~valid_year, "invalid_or_missing_year", blocks=True)
    d["year"] = pd.to_numeric(year_text.where(valid_year), errors="coerce").astype("Int64")
    if expected_year is not None:
        flag(d["year"].notna() & d["year"].ne(expected_year), "year_filename_mismatch", blocks=True)

    for column in ["id", "establishment_id", "ein", "naics_code", "naics_year", "size", "establishment_type", "no_injuries_illnesses"]:
        if column in d:
            d[column] = normalize_integer_text(d[column])
    valid_id = d["establishment_id"].str.fullmatch(r"[0-9]+") & d["establishment_id"].str.contains(r"[1-9]")
    flag(~valid_id, "invalid_or_missing_establishment_id", blocks=True)
    # Treat zero-padded numeric establishment identifiers consistently.
    d.loc[valid_id, "establishment_id"] = d.loc[valid_id, "establishment_id"].str.lstrip("0")
    d["zip_code"] = normalize_integer_text(d["zip_code"])
    short_zip = d["zip_code"].str.fullmatch(r"\d{1,5}")
    d.loc[short_zip, "zip_code"] = d.loc[short_zip, "zip_code"].str.zfill(5)
    d["state"] = d["state"].str.upper()
    flag(~d["zip_code"].str.fullmatch(r"\d{5}(?:-?\d{4})?"), "invalid_or_missing_zip")
    for column in ["establishment_name", "street_address", "city", "state"]:
        flag(d[column].eq(""), f"missing_{column}")
    valid_naics = d["naics_code"].str.fullmatch(r"[1-9]\d{5}")
    flag(~valid_naics, "invalid_or_missing_naics", blocks=True)
    d["is_naics_4931"] = valid_naics & d["naics_code"].str.startswith("4931")
    if "naics_year" in d:
        flag(~d["naics_year"].isin(["2012", "2017", "2022"]), "unknown_naics_version")
    # Leave unavailable NAICS version metadata blank; do not invent row-level values.
    if "size" in d:
        flag(~d["size"].isin(["1", "2", "21", "22", "3"]), "invalid_size_code")

    for column in [c for c in COUNTS + ["total_hours_worked"] if c in d]:
        text = d[column]
        absent_value = missing(text)
        number = pd.to_numeric(text.mask(absent_value), errors="coerce")
        finite = number.notna() & np.isfinite(number)
        is_core = column in {"annual_average_employees", "total_hours_worked", "total_dafw_cases", "total_djtr_cases"}
        flag(absent_value, f"missing_{column}", blocks=is_core)
        flag(~absent_value & ~finite, f"invalid_{column}", blocks=is_core)
        flag(finite & number.lt(0), f"negative_{column}", blocks=is_core)
        if column in COUNTS:
            fractional = finite & number.mod(1).ne(0)
            flag(fractional, f"fractional_{column}", blocks=is_core)
            # Keep invalid values blank in numeric output; originals are traceable
            # using source_file and source_record. Do not turn missing into zero.
            number = number.where(~fractional)
        d[column] = number.where(finite & number.ge(0))

    flag(d["total_hours_worked"].eq(0), "zero_hours", blocks=True)
    flag(d["annual_average_employees"].eq(0), "zero_employees", blocks=True)
    d["dart_count"] = d["total_dafw_cases"] + d["total_djtr_cases"]
    d["dart_rate"] = (d["dart_count"] * 200000 / d["total_hours_worked"].where(d["total_hours_worked"].gt(0))).round(6)
    flag(d["dart_count"].gt(d["annual_average_employees"]), "dart_exceeds_average_employees")
    if "no_injuries_illnesses" in d:
        flag(d["no_injuries_illnesses"].eq("2") & d["dart_count"].gt(0), "no_injury_indicator_conflicts_with_dart", blocks=True)

    valid_key = valid_id & d["year"].notna()
    repeated = valid_key & d.duplicated(["year", "establishment_id"], keep=False)
    flag(repeated, "repeated_establishment_year")
    d["establishment_year_unique"] = valid_key & ~repeated
    d["core_fields_valid"] = ~blocking
    d["candidate_for_linkage"] = d["core_fields_valid"] & d["establishment_year_unique"]
    d["quality_flags"] = flags.str.rstrip(";")
    d["needs_review"] = d["quality_flags"].ne("")
    d["source_file"] = source_name
    d["source_record"] = np.arange(1, len(d) + 1)
    return d.reindex(columns=OUTPUT_COLUMNS), profiles, flag_counts


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_dictionary(output):
    definitions = {
        "source_file": "Original input filename; raw input is never modified.",
        "source_record": "1-based CSV data-record number (not physical line number); excludes header.",
        "year": "Calendar year of reported outcomes, not submission timestamp.",
        "id": "Source record ID; not a longitudinal establishment key.",
        "establishment_id": "Source establishment identifier; stability across years requires Charles's verification.",
        "naics_code": "Six-digit industry code; 4931 prefix identifies the preliminary warehouse subset.",
        "naics_year": "Source NAICS version; absent older metadata stays blank. No cross-version mapping performed.",
        "size": "Peak employee-size category: 1 <20; 2 20–249; 21 20–99; 22 100–249; 3 250+. Not a headcount.",
        "annual_average_employees": "Annual average employee count; nonnegative integer.",
        "total_hours_worked": "Annual hours worked by all establishment employees.",
        "total_dafw_cases": "Number of cases with days away from work (Form 300A H).",
        "total_djtr_cases": "Number of cases with job transfer or restriction (Form 300A I).",
        "total_dafw_days": "Days away from work; not a case count.",
        "total_djtr_days": "Days of job transfer or restriction; not a case count.",
        "no_injuries_illnesses": "1 = injuries/illnesses reported; 2 = none reported (not a boolean).",
        "dart_count": "total_dafw_cases + total_djtr_cases; missing if either is invalid/missing.",
        "dart_rate": "dart_count * 200000 / positive total_hours_worked; otherwise blank; rounded to 6 decimals.",
        "is_naics_4931": "Valid six-digit NAICS code starts with 4931.",
        "core_fields_valid": "Passes provisional required year/ID/industry/count/hour/employee checks; see README.",
        "establishment_year_unique": "Valid year and ID, with no repeated normalized year-ID key within input.",
        "candidate_for_linkage": "Core fields valid and establishment-year unique; not a verified match or final modeling approval.",
        "needs_review": "One or more quality flags; not necessarily an exclusion.",
        "quality_flags": "Semicolon-separated audit findings. No flagged records are silently deleted.",
        "created_timestamp": "Submission timestamp; not the year being reported.",
        "change_reason": "Source explanation of a revised submission, when available.",
        "establishment_type": "1 private/non-government; 2 state government; 3 local government.",
        "ein": "Employer tax identifier; may cover multiple establishments. Preserved as text.",
        "zip_code": "Postal code stored as text; numeric values of 1–5 digits padded to five digits.",
    }
    labels = {
        "establishment_name": "Reporting establishment name", "company_name": "Owning company name",
        "street_address": "Establishment street address", "city": "Establishment city", "state": "State/territory code",
        "industry_description": "Source industry description", "total_deaths": "Deaths (Form 300A G)",
        "total_other_cases": "Other recordable cases (Form 300A J)", "total_injuries": "Injury cases (Form 300A M1)",
        "total_skin_disorders": "Skin disorder cases (M2)", "total_respiratory_conditions": "Respiratory condition cases (M3)",
        "total_poisonings": "Poisoning cases (M4)", "total_hearing_loss": "Hearing loss cases (M5)",
        "total_other_illnesses": "Other illness cases (M6)",
    }
    definitions.update(labels)
    numeric = set(COUNTS + ["total_hours_worked", "dart_count", "dart_rate", "year", "source_record"])
    boolean = {"is_naics_4931", "core_fields_valid", "establishment_year_unique", "candidate_for_linkage", "needs_review"}
    pd.DataFrame([{"column": c, "type": "boolean" if c in boolean else "numeric" if c in numeric else "text",
                   "definition": definitions[c]} for c in OUTPUT_COLUMNS]).to_csv(output / "data_dictionary.csv", index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=REPO_ROOT / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data" / "processed")
    parser.add_argument("--overwrite", action="store_true", help="Replace this script's generated output files")
    args = parser.parse_args()
    input_dir, output = args.input_dir.resolve(), args.output_dir.resolve()
    if output == input_dir or input_dir in output.parents or output in input_dir.parents:
        parser.error("Input and output directories must be separate, non-nested directories.")
    paths = sorted(input_dir.rglob("*.csv"))
    if not paths:
        parser.error(f"No CSV files found in {input_dir}")
    names = ["summary_cleaned.csv", "warehouses_4931.csv", "rows_for_review.csv",
             "inventory.csv", "column_profile.csv", "quality_summary.csv", "data_dictionary.csv", "run_manifest.json"]
    if output.exists() and any((output / n).exists() for n in names) and not args.overwrite:
        parser.error("Generated outputs already exist. Use --overwrite to rerun, or choose a new --output-dir.")

    # Preflight all headers before starting a potentially long run.
    inventory, summaries, seen_years = [], [], set()
    for path in paths:
        source_name = path.relative_to(input_dir).as_posix()
        header, _ = read_csv(path, header_only=True)
        cols = [normalize_header(c) for c in header.columns]
        kind = "summary" if {"total_dafw_cases", "total_djtr_cases"} <= set(cols) else "case_detail" if "case_number" in cols and "incident_outcome" in cols else "unknown"
        entry = {"source_file": source_name, "kind": kind, "columns": len(cols), "column_names": "|".join(cols)}
        inventory.append(entry)
        if kind == "unknown":
            parser.error(f"Unrecognized CSV schema: {source_name}. No guessing about its meaning.")
        if kind == "summary":
            if REQUIRED - set(cols):
                parser.error(f"{source_name}: missing required fields {sorted(REQUIRED - set(cols))}")
            year = filename_year(path)
            if year is None:
                parser.error(f"{source_name}: give each summary a filename with exactly one reporting year, e.g. ITA Data 2024.csv")
            if year in seen_years:
                parser.error(f"Multiple summary files for {year}. Select one source release per year.")
            seen_years.add(year)
            summaries.append((path, entry, year))
        else:
            entry["status"] = "skipped: incident-level file belongs to separate NLP pipeline"
    if not summaries:
        parser.error("No annual summary files found.")
    output.mkdir(parents=True, exist_ok=True)
    for name in names:
        if (output / name).exists():
            (output / name).unlink()
    manifest = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
                "input_dir": str(input_dir), "pandas_version": pd.__version__,
                "script_sha256": file_hash(Path(__file__)), "sources": [],
                "policy": "Retain all summary rows. Provisional candidate flags only. Case details skipped."}
    manifest_path = output / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    profiles, flags = [], []
    try:
        for i, (path, entry, year) in enumerate(summaries):
            source_name = entry["source_file"]
            print(f"Cleaning {source_name} ...", flush=True)
            raw, encoding = read_csv(path)
            clean, profile, counts = clean_summary(raw, source_name, year)
            profiles.extend(profile)
            flags.extend(counts)
            warehouses = clean["is_naics_4931"]
            for name, subset in [("summary_cleaned.csv", clean),
                                 ("warehouses_4931.csv", clean.loc[warehouses]),
                                 ("rows_for_review.csv", clean.loc[clean["needs_review"]])]:
                subset.to_csv(output / name, index=False, mode="w" if i == 0 else "a", header=i == 0)
            entry.update({"status": "processed", "year": year, "encoding": encoding,
                          "raw_rows": len(raw), "cleaned_rows": len(clean),
                          "warehouse_rows": int(warehouses.sum()),
                          "warehouse_candidate_rows": int((warehouses & clean["candidate_for_linkage"]).sum()),
                          "candidate_rows": int(clean["candidate_for_linkage"].sum()),
                          "review_rows": int(clean["needs_review"].sum()),
                          "repeated_key_rows": int(clean["quality_flags"].str.contains("repeated_establishment_year").sum())})
            manifest["sources"].append({"file": source_name, "sha256": file_hash(path), "bytes": path.stat().st_size,
                                        "rows": len(raw), "encoding": encoding})
            print(f"  {len(clean):,} rows retained; {int(warehouses.sum()):,} warehouse rows", flush=True)
        pd.DataFrame(inventory).to_csv(output / "inventory.csv", index=False)
        pd.DataFrame(profiles).to_csv(output / "column_profile.csv", index=False)
        pd.DataFrame(flags).to_csv(output / "quality_summary.csv", index=False)
        write_dictionary(output)
        manifest.update(status="complete", finished_utc=datetime.now(timezone.utc).isoformat(),
                        summary_rows=sum(e["raw_rows"] for e in inventory if e["kind"] == "summary"),
                        skipped_files=[e["source_file"] for e in inventory if e["kind"] != "summary"])
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Done. Results: {output}")


if __name__ == "__main__":
    main()
