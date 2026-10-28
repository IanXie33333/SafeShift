"""Data-independent regression checks for the WP2 linkage safeguards."""

import ast
import io
import unittest
from pathlib import Path

import pandas as pd

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks/linkage_feasibility.py"
IDENTITY_FIELDS = ["name_normalized", "address_normalized", "city", "state", "zip_code"]


def load_functions():
    # The analysis script reads CSVs at module scope. Load only its pure functions.
    tree = ast.parse(NOTEBOOK.read_text(encoding="utf-8"))
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"build_forecasting_pairs", "classify_linkage", "load_warehouse_data"}
    ]
    namespace = {"pd": pd}
    module = ast.Module(body=functions, type_ignores=[])
    # Trusted repository code: execute only the allowlisted function definitions.
    exec(compile(module, str(NOTEBOOK), "exec"), namespace)  # noqa: S102
    return (namespace["build_forecasting_pairs"], namespace["classify_linkage"],
            namespace["load_warehouse_data"])


BUILD, CLASSIFY, LOAD = load_functions()


def records():
    return pd.DataFrame([
        {
            "establishment_id": "A",
            "year": year,
            "candidate_for_linkage": True,
            "dart_count": dart,
            "annual_average_employees": employees,
            "total_hours_worked": hours,
            **dict.fromkeys(IDENTITY_FIELDS, "same"),
        }
        for year, dart, employees, hours in [
            (2023, 3, 50, 100000), (2024, 5, 55, 105000), (2025, 8, 60, 110000)
        ]
    ])


class TestLinkageSafeguards(unittest.TestCase):
    def test_csv_reader_preserves_distinct_ids_and_zip_leading_zero(self):
        csv = io.StringIO(
            "establishment_id,year,zip_code,candidate_for_linkage\n"
            "9007199254740992,2023,01234,True\n"
            "9007199254740993,2024,01234,True\n"
            ",2023,01234,False\n"
        )
        frame = LOAD(csv)
        self.assertEqual(frame.loc[0, "establishment_id"], "9007199254740992")
        self.assertEqual(frame.loc[1, "establishment_id"], "9007199254740993")
        self.assertTrue(pd.isna(frame.loc[2, "establishment_id"]))
        self.assertTrue(frame["zip_code"].eq("01234").all())

    def test_features_targets_and_holdout(self):
        pairs = CLASSIFY(BUILD(records()))
        self.assertTrue(pairs["linkage_class"].eq("high_confidence").all())
        self.assertEqual(pairs["dart_count_t"].tolist(), [3, 5])
        self.assertEqual(pairs["dart_count_t1"].tolist(), [5, 8])
        self.assertEqual(pairs["employee_count_t"].tolist(), [50, 55])
        self.assertEqual(pairs["hours_worked_t"].tolist(), [100000, 105000])
        self.assertEqual(pairs["dataset_split"].tolist(), ["train_validation", "holdout_test"])

    def test_all_eligible_duplicate_group_is_rejected(self):
        frame = pd.concat([records(), records().iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "Duplicate establishment/year"):
            BUILD(frame)

    def test_partially_eligible_duplicate_group_is_rejected(self):
        frame = pd.concat([records(), records().iloc[[0]]], ignore_index=True)
        frame.loc[3, "candidate_for_linkage"] = False
        with self.assertRaisesRegex(ValueError, "Duplicate establishment/year"):
            BUILD(frame)

    def test_fully_excluded_duplicate_group_does_not_block_other_pairs(self):
        frame = pd.concat([records(), records().iloc[[0]]], ignore_index=True)
        frame.loc[frame["year"].eq(2023), "candidate_for_linkage"] = False
        self.assertEqual(BUILD(frame)["target_year"].tolist(), [2025])

    def test_missing_identity_values_are_uncertain(self):
        for value in ["", "  ", None, pd.NA]:
            with self.subTest(value=repr(value)):
                frame = records()
                for field in IDENTITY_FIELDS:
                    frame[field] = value
                pairs = CLASSIFY(BUILD(frame))
                self.assertTrue(pairs["linkage_class"].eq("uncertain_confidence").all())

    def test_partial_and_complete_mismatches(self):
        frame = records().iloc[:2].copy()
        frame.loc[1, "address_normalized"] = "different"
        self.assertEqual(CLASSIFY(BUILD(frame))["linkage_class"].item(), "uncertain_confidence")
        for field in IDENTITY_FIELDS:
            frame.loc[1, field] = "different"
        self.assertEqual(CLASSIFY(BUILD(frame))["linkage_class"].item(), "failed_validation")

    def test_nonconsecutive_years_do_not_form_pairs(self):
        frame = records()
        self.assertTrue(BUILD(frame.loc[frame["year"].ne(2024)]).empty)

    def test_numeric_zip_codes_still_match_after_shift(self):
        frame = records()
        frame["zip_code"] = 2134
        self.assertTrue(CLASSIFY(BUILD(frame))["linkage_class"].eq("high_confidence").all())


if __name__ == "__main__":
    unittest.main()
