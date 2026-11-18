"""Synthetic regression checks for the descriptive case-report release."""

import json
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path

import pandas as pd

from src.analysis.case_patterns import (
    PROJECT,
    aggregate_cases,
    coverage_table,
    load_export,
    make_scenarios,
    parse_date,
    prepare_cases,
    read_policy,
    run,
    verify,
)


def case(year=2023, identifier="1", **changes):
    row = {"source_year": str(year), "year": year, "source_record": identifier,
           "source_id": identifier, "establishment_id": "00100", "case_number": "A",
           "naics_code": "493110", "incident_date_raw": "01/02/2023" if year == 2023 else "02JAN2024",
           "incident_outcome_raw": "2", "dafw_days_raw": "3", "djtr_days_raw": "2",
           "soc_code_raw": "53-7062", "soc_description_raw": "Synthetic occupation",
           "soc_reviewed_raw": "1", "soc_probability_raw": "5", "event_code_raw": "62",
           "event_title_raw": "Struck by object or equipment" if year == 2023 else "Contact with animals"}
    row.update(changes)
    return row


class CasePatternChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.mapping = PROJECT / "reference/nlp_label_map.csv"
        self.soc = PROJECT / "reference/soc_major_groups_2018.csv"
        self.blocked = {key: {"status": "blocked_review"} for key in ["dafw", "djtr"]}
        self.accepted = {key: {"status": "accept_reported_values"} for key in ["dafw", "djtr"]}

    def prepare(self, rows):
        frame, issues = prepare_cases(pd.DataFrame(rows), self.mapping, self.soc)
        self.assertTrue(issues.empty)
        return frame

    def test_year_specific_code_62(self):
        frame = self.prepare([case(), case(2024)])
        self.assertEqual(frame.mechanism_group.tolist(),
                         ["object_equipment_contact", "other_reported_mechanism"])

    def test_unknown_and_other_are_separate(self):
        frame = self.prepare([case(event_code_raw="", event_title_raw=""), case(2024)])
        self.assertEqual(frame.mechanism_group.tolist(),
                         ["unknown_missing_mechanism", "other_reported_mechanism"])

    def test_changed_title_requires_review(self):
        _, issues = prepare_cases(pd.DataFrame([case(event_title_raw="Different classification")]),
                                   self.mapping, self.soc)
        self.assertEqual(len(issues), 1)

    def test_unseen_code_requires_review(self):
        _, issues = prepare_cases(pd.DataFrame([case(event_code_raw="98")]), self.mapping, self.soc)
        self.assertEqual(len(issues), 1)

    def test_manual_soc_indicator_survives(self):
        frame = self.prepare([case()])
        self.assertEqual(frame.soc_major.iloc[0], "53")
        self.assertEqual(frame.soc_assignment_status.iloc[0], "osha_reassigned_indicator_5")

    def test_soc_uncodable_is_retained(self):
        frame = self.prepare([case(soc_code_raw="9999", soc_reviewed_raw="2")])
        self.assertEqual(frame.soc_major.iloc[0], "unknown")
        self.assertEqual(frame.soc_status.iloc[0], "uncodable")
        self.assertTrue(frame.primary_eligible.iloc[0])

    def test_repeated_establishment_case_key_is_not_deduplicated(self):
        frame = self.prepare([case(), case(identifier="2")])
        self.assertEqual(int(frame.primary_eligible.sum()), 2)

    def test_repeated_source_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source IDs"):
            self.prepare([case(), case(source_record="2")])

    def test_missing_source_id_has_traceable_fallback(self):
        frame = self.prepare([case(source_id="")])
        self.assertEqual(frame.record_id.iloc[0], "2023:row:1")

    def test_explicit_dates_and_alignment(self):
        frame = self.prepare([case(), case(identifier="2", incident_date_raw="01/02/2024"),
                              case(identifier="3", incident_date_raw="not a date")])
        self.assertEqual(frame.primary_eligible.tolist(), [True, False, False])
        self.assertIsNone(parse_date("31FEB2024", 2024))

    def test_missing_label_does_not_remove_report(self):
        frame = self.prepare([case(event_code_raw="", event_title_raw="")])
        result = aggregate_cases(make_scenarios(frame), self.blocked)
        self.assertEqual(int(result.loc[result.scenario.eq("primary"), "case_report_count"].sum()), 1)

    def test_missing_invalid_days_differ_from_zero(self):
        frame = self.prepare([case(dafw_days_raw="0", djtr_days_raw=""),
                              case(identifier="2", dafw_days_raw="-1", djtr_days_raw="2.5")])
        result = aggregate_cases(make_scenarios(frame), self.accepted)
        primary = result.loc[result.scenario.eq("primary")]
        self.assertEqual(int(primary.dafw_days_known_report_count.sum()), 1)
        self.assertEqual(int(primary.djtr_days_known_report_count.sum()), 0)
        self.assertEqual(float(primary.dafw_days_sum.sum()), 0)
        self.assertTrue(primary.djtr_days_sum.isna().all())

    def test_day_flags_do_not_clip_primary_values(self):
        frame = self.prepare([case(dafw_days_raw="200", djtr_days_raw="0")])
        scenarios = make_scenarios(frame)
        self.assertEqual(len(scenarios), 1)
        result = aggregate_cases(scenarios, self.accepted)
        self.assertEqual(float(result.dafw_days_sum.sum()), 200)
        self.assertEqual(result.scenario.iloc[0], "primary")

    def test_dafw_case_with_restricted_days_is_allowed(self):
        frame = self.prepare([case()])
        self.assertFalse(frame.outcome_day_review_flag.iloc[0])

    def test_blocked_days_stay_blank(self):
        frame = self.prepare([case()])
        result = aggregate_cases(make_scenarios(frame), self.blocked)
        self.assertTrue(result.dafw_days_sum.isna().all())
        self.assertTrue(result.dafw_days_status.eq("blocked_review").all())

    def test_outcomes_and_reconciliation(self):
        frame = self.prepare([case(), case(2024, incident_outcome_raw="invalid")])
        sources = {2023: {"raw_rows": 10}, 2024: {"raw_rows": 11}}
        scenarios = make_scenarios(frame)
        result = aggregate_cases(scenarios, self.blocked)
        coverage = coverage_table(frame, sources)
        checks = verify(frame, scenarios, result, coverage, self.blocked)
        self.assertTrue(all(checks.values()))
        self.assertEqual(int(result.loc[result.year.eq(2024) & result.scenario.eq("primary"),
                                         "outcome_unknown_count"].sum()), 1)

    def test_policy_must_match_raw_sources(self):
        path = self.root / "policy.json"
        path.write_text(json.dumps({"source_sha256_by_year": {"2023": "different"},
                                    "review_note": "reviewed", "metrics": self.accepted}))
        with self.assertRaisesRegex(ValueError, "different raw sources"):
            read_policy(path, {"sources": [{"source_year": 2023, "source_sha256": "actual"}]})

    def test_full_export_round_trip_and_overwrite_guard(self):
        archive = self.root / "cases.zip"
        sources = []
        with zipfile.ZipFile(archive, "w") as output:
            for year in [2023, 2024]:
                frame = pd.DataFrame([case(year)]).drop(columns="year")
                output.writestr(f"case_fields_{year}.csv", frame.to_csv(index=False))
                sources.append({"source_year": year, "warehouse_rows": 1, "raw_rows": 20,
                                "source_sha256": f"synthetic-{year}"})
            output.writestr("source_manifest.json", json.dumps({"sources": sources}))
        raw, _ = load_export(archive)
        self.assertEqual(len(raw), 2)
        args = Namespace(case_fields_zip=archive, label_map=self.mapping,
                         soc_major_reference=self.soc, day_policy=None,
                         output_dir=self.root / "data", audit_dir=self.root / "audit", overwrite=False)
        run(args)
        self.assertTrue((self.root / "data/case_pattern_summary.csv").is_file())
        with self.assertRaises(FileExistsError):
            run(args)


if __name__ == "__main__":
    unittest.main()
