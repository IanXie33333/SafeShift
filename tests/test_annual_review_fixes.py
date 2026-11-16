"""Regression checks for the WP1 local-review patch; runnable without pytest."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.analysis.annual_establishments import (
    create_day_anomaly_audit,
    create_scenarios,
    load_primary_cohort,
    main,
    summarize_annual,
    summarize_coverage,
)
from src.analysis.annual_review_utils import direct_reference, read_validated_input


def row(**changes):
    value = {
        "id": "0001",
        "year": 2024,
        "establishment_id": "00123",
        "establishment_name": "Synthetic",
        "source_file": "synthetic.csv",
        "source_record": 1,
        "naics_code": "493110",
        "is_naics_4931": True,
        "core_fields_valid": True,
        "establishment_year_unique": True,
        "annual_average_employees": 10,
        "total_hours_worked": 20000,
        "total_dafw_cases": 1,
        "total_djtr_cases": 1,
        "dart_count": 2,
        "total_dafw_days": 10,
        "total_djtr_days": 10,
    }
    value.update(changes)
    return value


class AnnualReviewFixes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input = self.root / "input.csv"

    def write(self, rows):
        pd.DataFrame(rows).to_csv(self.input, index=False)

    def run_cli(self, overwrite=False):
        from unittest.mock import patch
        argv = ["annual_establishments", "--input", str(self.input),
                "--output-dir", str(self.root / "data"), "--audit-dir", str(self.root / "audit")]
        if overwrite:
            argv.append("--overwrite")
        with patch("sys.argv", argv):
            main()

    def test_zero_exposure_with_true_flags_is_rejected(self):
        self.write([row(annual_average_employees=0, total_hours_worked=0)])
        with self.assertRaisesRegex(ValueError, "core-valid"):
            load_primary_cohort(self.input)

    def test_inconsistent_dart_is_rejected(self):
        self.write([row(dart_count=999)])
        with self.assertRaisesRegex(ValueError, "DART count"):
            load_primary_cohort(self.input)

    def test_stale_duplicate_key_flags_are_rejected(self):
        self.write([row(), row(id="2", source_record=2)])
        with self.assertRaisesRegex(ValueError, "actual normalized keys"):
            load_primary_cohort(self.input)

    def test_correctly_flagged_duplicate_group_is_excluded(self):
        self.write([row(establishment_year_unique=False),
                    row(id="2", source_record=2, establishment_year_unique=False)])
        self.assertEqual(len(load_primary_cohort(self.input)), 0)

    def test_false_flags_are_not_parsed_as_truthy_strings(self):
        self.write([row(core_fields_valid="False", total_hours_worked=0)])
        self.assertEqual(len(load_primary_cohort(self.input)), 0)

    def test_invalid_boolean_is_rejected(self):
        self.write([row(core_fields_valid="unknown")])
        with self.assertRaisesRegex(ValueError, "Boolean"):
            load_primary_cohort(self.input)

    def test_identifiers_preserve_leading_zeros(self):
        self.write([row()])
        result = load_primary_cohort(self.input)
        self.assertEqual(result.establishment_id.iloc[0], "00123")
        self.assertEqual(result.id.iloc[0], "0001")

    def test_naics_flag_is_independently_checked(self):
        self.write([row(naics_code="111110")])
        with self.assertRaisesRegex(ValueError, "NAICS"):
            load_primary_cohort(self.input)

    def test_missing_schema_fails_before_outputs_are_written(self):
        pd.DataFrame({"year": [2024]}).to_csv(self.input, index=False)
        with self.assertRaisesRegex(ValueError, "Missing required"):
            self.run_cli()
        self.assertFalse((self.root / "data").exists())

    def test_empty_sensitivity_year_has_zero_counts(self):
        self.write([row(total_hours_worked=10)])
        raw = read_validated_input(self.input)
        scenarios = create_scenarios(load_primary_cohort(self.input))
        coverage = summarize_coverage(scenarios, raw)
        self.assertEqual(len(coverage), 2)
        self.assertTrue(coverage.sensitivity_records.eq(0).all())
        self.assertTrue(coverage.exposure_excluded.eq(1).all())
        self.assertEqual(coverage.loc[coverage.scenario.eq("exposure_sensitivity"),
                                      "establishment_years"].iloc[0], 0)
        reference = direct_reference(scenarios, [2024])
        self.assertTrue(pd.isna(reference.loc[reference.scenario.eq("exposure_sensitivity"),
                                             "dart_rate_reference"].iloc[0]))

    def test_entirely_excluded_year_is_still_reported(self):
        self.write([row(core_fields_valid=False, total_hours_worked=0)])
        self.run_cli()
        coverage = pd.read_csv(self.root / "data/annual_coverage.csv")
        self.assertEqual(len(coverage), 2)
        self.assertTrue(coverage.primary_records.eq(0).all())
        self.assertTrue(coverage.structurally_excluded.eq(1).all())

    def test_ordinary_dafw_restricted_day_combination_is_not_anomaly(self):
        frame = pd.DataFrame([row(total_dafw_cases=10, total_djtr_cases=0,
                                 dart_count=10, total_djtr_days=20)])
        self.assertTrue(create_day_anomaly_audit(frame).empty)

    def test_combined_days_receive_an_explicit_review_flag(self):
        frame = pd.DataFrame([row(total_dafw_days=200, total_djtr_days=200)])
        audit = create_day_anomaly_audit(frame)
        self.assertEqual(audit.measure.tolist(), ["combined"])
        self.assertEqual(audit.review_case_count.iloc[0], 2)

    def test_invalid_days_are_audited_and_not_counted_as_known_zero(self):
        self.write([row(total_dafw_days="invalid", total_djtr_days=-1)])
        primary = load_primary_cohort(self.input)
        audit = create_day_anomaly_audit(primary)
        self.assertEqual(len(audit), 2)
        self.assertTrue(audit.invalid_day_value.all())
        summary = summarize_annual(create_scenarios(primary))
        self.assertTrue(summary.dafw_days_eligible_establishment_years.eq(0).all())
        self.assertTrue(summary.djtr_days_eligible_establishment_years.eq(0).all())
        self.assertTrue(summary.dafw_days_sum.isna().all())

    def test_existing_outputs_need_explicit_overwrite(self):
        self.write([row()])
        self.run_cli()
        target = self.root / "data/annual_size_summary.csv"
        target.write_text("existing accepted output\n")
        with self.assertRaises(FileExistsError):
            self.run_cli()
        self.assertEqual(target.read_text(), "existing accepted output\n")
        self.run_cli(overwrite=True)
        self.assertTrue(target.read_text().startswith("year,"))

    def test_all_release_files_and_actual_hashes_are_generated(self):
        from src.analysis.annual_review_utils import file_hash
        self.write([row()])
        self.run_cli()
        manifest = json.loads((self.root / "audit/source_run_manifest.json").read_text())
        self.assertEqual(manifest["source_sha256"], file_hash(self.input))
        self.assertEqual(len(manifest["outputs"]), 6)
        self.assertTrue(all(manifest["qa_checks"].values()))
        for entry in manifest["outputs"].values():
            self.assertEqual(entry["sha256"], file_hash(Path(entry["path"])))


if __name__ == "__main__":
    unittest.main()
