import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.cleaning.clean_ita_data import clean_summary


def test_clean_summary_calculates_dart_and_marks_warehouse_row():
    raw = pd.DataFrame(
        [
            {
                "establishment_id": "00123",
                "establishment_name": "Example Warehouse",
                "street_address": "100 Main St",
                "city": "Los Angeles",
                "state": "ca",
                "zip_code": "90001",
                "naics_code": "493110",
                "annual_average_employees": "25",
                "total_hours_worked": "1000",
                "total_dafw_cases": "1",
                "total_djtr_cases": "2",
                "year_filing_for": "2024",
            }
        ]
    )

    cleaned, profiles, flag_counts = clean_summary(raw, "fixture/ITA Data 2024.csv", 2024)

    row = cleaned.iloc[0]
    assert len(cleaned) == 1
    assert row["establishment_id"] == "123"
    assert row["state"] == "CA"
    assert row["dart_count"] == 3
    assert row["dart_rate"] == 600
    assert bool(row["is_naics_4931"])
    assert bool(row["candidate_for_linkage"])
    assert profiles
    assert flag_counts


def test_cli_reads_nested_raw_directory(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    fixture_dir = Path(__file__).parent / "fixtures"
    output_dir = tmp_path / "processed"

    subprocess.run(
        [
            sys.executable,
            str(repository_root / "src" / "cleaning" / "clean_ita_data.py"),
            "--input-dir",
            str(fixture_dir),
            "--output-dir",
            str(output_dir),
        ],
        check=True,
    )

    inventory = pd.read_csv(output_dir / "inventory.csv")
    cleaned = pd.read_csv(output_dir / "summary_cleaned.csv")
    assert inventory.loc[0, "source_file"] == "osha_ita/2024/ITA Data 2024.csv"
    assert cleaned.loc[0, "dart_count"] == 3
    assert bool(cleaned.loc[0, "is_naics_4931"])
