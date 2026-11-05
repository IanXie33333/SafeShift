"""Small regression checks for WP3's cohort, duplication, and saved review work."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "src/audit/wp3_narrative_audit.py"
SPEC = importlib.util.spec_from_file_location("wp3_audit", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def sample_frame():
    rows = []
    for year in [2023, 2024]:
        for major in ["2", "4", "5", "6", "7"]:
            for i in range(8):
                code = major + ("2" if year == 2023 else "3")
                text = f"worker reported an incident in category {major} number {i}"
                rows.append({"year": year, "source_row": len(rows), "is_4931": True,
                             "text": text, "n_words": 10, "event_2d": code,
                             "event_major": major, "event_code_raw": code,
                             "event_title": f"category {major}, release {year}"})
        for i in range(2):
            rows.append({"year": year, "source_row": len(rows), "is_4931": True,
                         "text": f"pain {i}", "n_words": 2, "event_2d": "71",
                         "event_major": "7", "event_code_raw": "71", "event_title": "pain"})
    outside = rows[0].copy()
    outside.update(is_4931=False, text="OUTSIDE INDUSTRY", source_row=999)
    rows.append(outside)
    return pd.DataFrame(rows)


class AuditRegressionTests(unittest.TestCase):
    def test_field_separators_do_not_hide_short_narratives(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "Case Detail 2023.csv"
            fields = ["NEW_NAR_WHAT_HAPPENED", "NEW_NAR_INJURY_ILLNESS",
                      "NEW_NAR_OBJECT_SUBSTANCE"]
            pd.DataFrame({fields[0]: ["fell"], fields[1]: ["knee"], fields[2]: ["floor"],
                          "event_code_pred": ["42"], "event_title_pred": ["Falls"],
                          "naics_code": ["493110"]}).to_csv(path, index=False)
            cols = {"text": fields, "event_code": "event_code_pred",
                    "event_title": "event_title_pred", "naics": "naics_code",
                    "est_id": None, "case_id": None, "incident_date": None}
            frame = audit.load_year(path, cols, 2023, "utf-8")
            self.assertEqual(frame["text"].item(), "fell | knee | floor")
            self.assertEqual(frame["n_words"].item(), 3)
            self.assertEqual(audit.quality(frame, cols, 5)["short_narrative_lt_5_words"], 1)

    def test_case_counts_require_both_complete_keys(self):
        df = pd.DataFrame({"est": ["A", "A", "B", "B", "C", "C"],
                           "case": ["1", "1", "", "", None, None],
                           "text": ["same words"] * 6, "n_words": [2] * 6,
                           "event_code_raw": ["71"] * 6, "code_valid": [True] * 6,
                           "event_2d": ["71"] * 6, "is_4931": [True] * 6})
        cols = {"est_id": "est", "case_id": "case", "event_code": "event_code_raw",
                "incident_date": None}
        q = audit.quality(df, cols, 5)
        self.assertEqual(q["repeated_case_key_rows"], 2)
        self.assertEqual(q["repeated_case_key_extra_copies"], 1)
        self.assertEqual(q["repeated_case_key_same_text_rows"], 2)
        self.assertEqual(q["rows_with_incomplete_case_key"], 4)
        cols["case_id"] = None
        self.assertIsNone(audit.quality(df, cols, 5)["repeated_case_key_rows"])

    def test_full_row_duplicates_use_unloaded_columns_and_cross_chunk_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "raw.csv"
            pd.DataFrame({"text": ["same", "same", "other", "same"],
                          "unloaded_column": ["A", "B", "C", "A"]}).to_csv(path, index=False)
            with patch.object(audit, "CHUNK", 2):
                counts = audit.raw_duplicate_counts(path, "utf-8")
            self.assertEqual(counts["exact_duplicate_raw_rows"], 2)
            self.assertEqual(counts["exact_duplicate_raw_extra_copies"], 1)

    def test_full_row_duplicates_tolerate_undefined_cp1252_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "raw.csv"
            path.write_bytes(
                b"text,unloaded_column\nother,C\nsame,broken\x9d\nsame,broken\x9d\n"
            )
            enc = audit.detect_encoding(path)
            self.assertEqual(enc, "cp1252")
            with patch.object(audit, "CHUNK", 2):
                counts = audit.raw_duplicate_counts(path, enc)
            self.assertEqual(counts["exact_duplicate_raw_rows"], 2)
            self.assertEqual(counts["exact_duplicate_raw_extra_copies"], 1)

    def test_major_denominator_and_zero_classes(self):
        base = sample_frame().iloc[[0, 1, 8, 42]].copy()
        counts, _ = audit.major_tables(base)
        first = counts.loc[counts["year"].eq(2023)].set_index("event_major")
        self.assertEqual(first.loc["2", "count"], 2)
        self.assertEqual(first.loc["4", "count"], 1)
        self.assertEqual(first.loc["2", "percentage"], 66.67)
        self.assertEqual(first.loc["1", "count"], 0)
        self.assertEqual(len(counts), 14)

    def test_sample_is_warehouse_only_both_years_unique_and_reproducible(self):
        df = sample_frame()
        samples = audit.review_samples(df, "event_title", 3, 42)
        again = audit.review_samples(df, "event_title", 3, 42)
        self.assertEqual(set(samples["year"]), {2023, 2024})
        self.assertNotIn("OUTSIDE INDUSTRY", set(samples["text"]))
        self.assertTrue(samples["review_id"].is_unique)
        self.assertTrue(30 <= len(samples) <= 40)
        self.assertEqual(samples["review_id"].tolist(), again["review_id"].tolist())
        self.assertEqual(set(samples["sample_type"]), {"short_text", "changed_code", "common_major"})

    def test_annotations_and_legacy_sample_survive_rerun(self):
        samples = audit.review_samples(sample_frame(), "event_title", 3, 42)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            legacy = out / "review_samples.csv"
            legacy.write_text("previous annotations\n", encoding="utf-8")
            manual = audit.save_review_samples(samples, out)
            manual.loc[0, "notes"] = "Already reviewed; preserve this."
            manual.to_csv(out / "manual_review.csv", index=False)
            before = (out / "manual_review.csv").read_bytes()
            audit.save_review_samples(samples, out)
            self.assertEqual((out / "manual_review.csv").read_bytes(), before)
            self.assertEqual(legacy.read_text(), "previous annotations\n")

    def test_new_2025_labels_fail_inference_assumption(self):
        frame = sample_frame().iloc[[0]].copy()
        audit.validate_labels(frame)
        frame["year"] = 2025
        with self.assertRaisesRegex(AssertionError, "2025 now has labels"):
            audit.validate_labels(frame)

    def test_loader_accepts_cp1252_and_mixed_case_headers(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "Case Detail 2023.csv"
            pd.DataFrame({"NEW_NAR_WHAT_HAPPENED": ["Employee’s foot slipped"],
                          "EVENT_CODE_PRED": ["42.0"], "EVENT_TITLE_PRED": ["Falls"],
                          "NAICS_CODE": ["493110"]}).to_csv(path, index=False, encoding="cp1252")
            cols = {"text": ["NEW_NAR_WHAT_HAPPENED"], "event_code": "EVENT_CODE_PRED",
                    "event_title": "EVENT_TITLE_PRED", "naics": "NAICS_CODE",
                    "case_id": None, "est_id": None, "incident_date": None}
            enc = audit.detect_encoding(path)
            self.assertEqual(enc, "cp1252")
            loaded = audit.load_year(path, cols, 2023, enc)
            self.assertEqual(loaded["event_2d"].item(), "42")
            self.assertEqual(loaded["event_major"].item(), "4")
            self.assertTrue(loaded["is_4931"].item())

    def test_three_year_cli_and_completed_review_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            raw, out = root / "raw", root / "out"
            raw.mkdir()
            for year in [2023, 2024, 2025]:
                source = sample_frame()
                source = source.loc[source["year"].eq(min(year, 2024))].copy()
                frame = pd.DataFrame({
                    "NEW_NAR_WHAT_HAPPENED": source["text"],
                    "naics_code": source["is_4931"].map({True: "493110", False: "111110"}),
                    "establishment_id": "E1",
                    "case_number": source["source_row"].astype(str),
                    "date_of_incident": f"{year}-02-01",
                })
                if year != 2025:
                    frame["event_code_pred"] = source["event_code_raw"]
                    frame["event_title_pred"] = source["event_title"]
                else:
                    frame.rename(columns={"NEW_NAR_WHAT_HAPPENED": "New_nar_what_happened"},
                                 inplace=True)
                frame.to_csv(raw / f"Case Detail Data {year}.csv", index=False)
            report = root / "report.md"
            cmd = [sys.executable, str(SCRIPT), "--raw-dir", str(raw), "--out-dir", str(out),
                   "--years", "2023", "2024", "2025", "--report", str(report)]
            run = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("Manual-review evidence: **pending**", report.read_text())
            for name in ["major_class_counts.csv", "group_1_6_details.csv", "columns_2023.csv",
                         "columns_used_2025.csv", "quality_checks.csv"]:
                self.assertTrue((out / name).is_file(), name)
            manual = pd.read_csv(out / "manual_review.csv", keep_default_na=False)
            manual["text_supports_label_y_n"] = "y"
            manual["easy_or_difficult"] = "easy"
            manual["notes"] = "Synthetic annotation for integration test only."
            types = ["easy", "difficult", "insufficient", "label_disagreement"]
            for i, kind in enumerate(types):
                manual.loc[i, "example_type"] = kind
                manual.loc[i, "anonymized_example"] = f"Synthetic {kind} illustration."
            manual.to_csv(out / "manual_review.csv", index=False)
            before = (out / "manual_review.csv").read_bytes()
            rerun = subprocess.run(cmd + ["--skip-profile"], capture_output=True, text=True, check=False)
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            self.assertIn("Manual-review evidence: **complete**", report.read_text())
            self.assertEqual(before, (out / "manual_review.csv").read_bytes())


if __name__ == "__main__":
    unittest.main()
