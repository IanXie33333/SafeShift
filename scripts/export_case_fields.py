"""Extract small warehouse case fields for WP2; raw input files stay read-only."""

import argparse
import codecs
import csv
import hashlib
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

FIELDS = {
    "source_id": "id", "establishment_id": "establishment_id", "case_number": "case_number",
    "naics_code": "naics_code", "incident_date_raw": "date_of_incident",
    "incident_outcome_raw": "incident_outcome", "dafw_days_raw": "dafw_num_away",
    "djtr_days_raw": "djtr_num_tr", "soc_code_raw": "soc_code",
    "soc_description_raw": "soc_description", "soc_reviewed_raw": "soc_reviewed",
    "soc_probability_raw": "soc_probability", "event_code_raw": "event_code_pred",
    "event_title_raw": "event_title_pred",
}
EXPECTED = {
    2023: "851bc39e9b0fd5d3308167ee74a0126185bf638c98e58db580f7f854a0f97b02",
    2024: "ef4ceb0935d0bcb2d8c6a8f31f4742a821ffa43adab7c1b1bcaa1d30ec6ce4c4",
}


def normalize(value):
    return re.sub(r"[\s-]+", "_", value.strip().lstrip("\ufeff").lower())


def identify(path):
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    utf8 = True
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
            if utf8:
                try:
                    decoder.decode(block)
                except UnicodeDecodeError:
                    utf8 = False
    if utf8:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            utf8 = False
    return digest.hexdigest(), "utf-8-sig" if utf8 else "cp1252"


def locate(root, year):
    expected = f"case detail data {year}.csv"
    matches = [p for p in root.rglob("*.csv") if p.name.casefold() == expected]
    if len(matches) != 1:
        raise ValueError(f"Expected one {expected} beneath {root}; found {len(matches)}. "
                         f"Pass --case-{year} with the exact file path.")
    return matches[0]


def export_one(path, year, archive):
    sha, encoding = identify(path)
    counts = {"raw_rows": 0, "warehouse_rows": 0, "missing_source_id": 0,
              "warehouse_rows_with_decode_replacement": 0}
    source_ids = set()
    with path.open(encoding=encoding, errors="replace", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        original = reader.fieldnames or []
        names = [normalize(c) for c in original]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate normalized headers: {path.name}")
        absent = set(FIELDS.values()) - set(names)
        if absent:
            raise ValueError(f"{path.name}: required raw fields missing: {sorted(absent)}")
        source_columns = dict(zip(names, original, strict=True))
        naics_column = source_columns["naics_code"]
        needed = set(FIELDS.values()) | {"job_description"}
        kept_columns = {key: column for key, column in source_columns.items() if key in needed}
        columns = ["source_year", "source_record", *FIELDS, "job_description_present"]
        with (
            archive.open(f"case_fields_{year}.csv", "w") as binary,
            io.TextIOWrapper(binary, encoding="utf-8", newline="") as output,
        ):
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            for position, record in enumerate(reader, 1):
                counts["raw_rows"] += 1
                if None in record or any(v is None for v in record.values()):
                    raise ValueError(f"Malformed CSV record {position} in {path.name}")
                naics = re.sub(r"^([0-9]+)\.0+$", r"\1", record[naics_column].strip())
                if not re.fullmatch(r"4931[0-9]{2}", naics):
                    continue
                # Normalize column names once, and inspect only warehouse
                # records/required fields rather than copying every narrative.
                record = {key: record[column].strip() for key, column in kept_columns.items()}
                counts["warehouse_rows"] += 1
                identifier = record["id"]
                counts["missing_source_id"] += not identifier
                if identifier:
                    if identifier in source_ids:
                        raise ValueError(f"Repeated source ID in {year}; review before exporting")
                    source_ids.add(identifier)
                values = {out: record[raw] for out, raw in FIELDS.items()}
                values.update(source_year=year, source_record=position,
                              job_description_present=int(bool(record.get("job_description", ""))))
                counts["warehouse_rows_with_decode_replacement"] += any(
                    "\ufffd" in str(v) for v in values.values())
                writer.writerow(values)
    return {"source_year": year, "source_file": path.name, "source_sha256": sha,
            "matches_previous_raw_hash": sha == EXPECTED[year], "encoding": encoding, **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path.home() /
                        "Desktop/DATA SC/DATA SC projects/SafeShift Logistics/OSHA Data")
    parser.add_argument("--case-2023", type=Path)
    parser.add_argument("--case-2024", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path.home() / "Downloads/safeshift_case_fields.zip")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Output exists: {args.output}; choose another --output path")
    sources = {year: (getattr(args, f"case_{year}") or locate(args.raw_dir, year))
               for year in [2023, 2024]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory) / "case_fields.zip"
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            metadata = {"purpose": "WP2 warehouse case fields; no names, addresses, narratives, or free-text jobs",
                        "schema_version": 1, "sources": []}
            for year, path in sources.items():
                print(f"Reading {year}: {path.name}", flush=True)
                result = export_one(path, year, archive)
                metadata["sources"].append(result)
                print(f"  {result['warehouse_rows']:,} warehouse reports; "
                      f"previous hash match: {result['matches_previous_raw_hash']}", flush=True)
            archive.writestr("source_manifest.json", json.dumps(metadata, indent=2) + "\n")
        import shutil
        shutil.copyfile(temporary, args.output)
    print(f"Ready to upload: {args.output} ({args.output.stat().st_size / 1048576:.2f} MB)")


if __name__ == "__main__":
    main()
