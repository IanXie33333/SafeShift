"""Native workbook package, metric, parameter, and publication-gate tests."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

from src.analysis.tableau_release import build


class TableauReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.annual = self.root / "annual.csv"
        self.cases = self.root / "cases.csv"
        annual = {"year": 2024, "size_group": "lt_50", "size_group_order": 1,
                  "scenario": "primary", "establishment_year_count": 2,
                  "hours_sum": 100000, "dart_case_count": 5, "dafw_days_sum": None,
                  "djtr_days_sum": None, "dafw_days_status": "blocked_review",
                  "djtr_days_status": "blocked_review"}
        pd.DataFrame([annual, {**annual, "scenario": "exposure_sensitivity"}]).to_csv(self.annual,index=False)
        case = {"year": 2023, "scenario": "primary", "mechanism_group": "harmful_exposure",
                "mechanism_label": "Harmful exposure", "soc_major": "53",
                "soc_major_label": "Transportation and Material Moving Occupations",
                "case_report_count": 10, "dafw_days_sum": None, "djtr_days_sum": None,
                "outcome_dafw_count": 8,
                "dafw_days_known_report_count": 10, "djtr_days_known_report_count": 9,
                "dafw_days_status": "blocked_review", "djtr_days_status": "blocked_review"}
        pd.DataFrame([case, {**case, "scenario": "day_review_sensitivity"}]).to_csv(self.cases,index=False)

    def build(self):
        target = build(self.annual, self.cases, self.root / "tableau")
        with zipfile.ZipFile(target) as archive:
            return ET.fromstring(archive.read("SafeShift_Research.twb")), archive.namelist()

    def test_genuine_native_workbook_package(self):
        xml, names = self.build()
        self.assertEqual(xml.tag, "workbook")
        self.assertEqual(len(xml.findall("worksheets/worksheet")), 8)
        self.assertEqual(len(xml.findall("dashboards/dashboard")), 3)
        self.assertIn("Data/annual_size_summary.csv", names)
        self.assertIn("Data/case_pattern_summary.csv", names)

    def test_no_fact_join_and_separate_sources(self):
        xml, _ = self.build()
        self.assertEqual(len(xml.findall(".//relation[@type='join']")), 0)
        self.assertEqual({d.attrib["name"] for d in xml.findall("datasources/datasource")},
                         {"Parameters", "ss_annual", "ss_cases"})

    def test_every_worksheet_has_mandatory_row_filter(self):
        xml, _ = self.build()
        for sheet in xml.findall("worksheets/worksheet"):
            self.assertEqual(sheet.find(".//filter/groupfilter").attrib["member"], "true")
        formulas = [c.attrib["formula"] for c in xml.findall("datasources/datasource/column/calculation")]
        self.assertTrue(any('[scenario] = [Parameters].[Annual scenario]' in f for f in formulas))
        self.assertTrue(any('[scenario] = [Parameters].[Case scenario]' in f for f in formulas))

    def test_scenario_parameters_are_single_value_lists(self):
        xml, _ = self.build()
        parameters = xml.find("datasources/datasource[@name='Parameters']")
        for name in ["Annual scenario", "Case scenario"]:
            field = parameters.find(f"column[@name='[{name}]']")
            self.assertEqual(field.attrib["param-domain-type"], "list")
            self.assertEqual(field.attrib["value"], '"primary"')
            self.assertEqual(len(field.findall("members/member")), 2)

    def test_pooled_rate_and_global_day_gate(self):
        xml, _ = self.build()
        rate = xml.find("datasources/datasource[@name='ss_annual']/column[@name='[DART rate]']/calculation")
        self.assertIn("SUM([dart_case_count]) / SUM([hours_sum])", rate.attrib["formula"])
        gate = xml.find("datasources/datasource[@name='ss_cases']/column[@name='[Accepted DAFW days]']/calculation")
        self.assertIn("FIXED", gate.attrib["formula"])
        self.assertIn("blocked_review", gate.attrib["formula"])

    def test_highlighting_does_not_filter_denominator(self):
        xml, _ = self.build()
        visible = xml.find("datasources/datasource[@name='ss_cases']/column[@name='[Visible rows]']/calculation")
        self.assertNotIn("Highlight mechanism", visible.attrib["formula"])

    def test_blocked_values_cannot_enter_package(self):
        frame = pd.read_csv(self.cases)
        frame["dafw_days_sum"] = 10
        frame.to_csv(self.cases,index=False)
        with self.assertRaisesRegex(ValueError,"Blocked day values"):
            self.build()

    def test_identifying_fields_cannot_enter_package(self):
        frame = pd.read_csv(self.cases)
        frame["establishment_id"] = "private-link"
        frame.to_csv(self.cases,index=False)
        with self.assertRaisesRegex(ValueError,"Identifying"):
            self.build()

    def test_application_validation_is_never_claimed(self):
        self.build()
        manifest = json.loads((self.root / "tableau/tableau_build_manifest.json").read_text())
        self.assertTrue(manifest["tableau_application_check"].startswith("PENDING"))
        references = pd.read_csv(self.root / "tableau/tableau_qa_references.csv")
        self.assertTrue(references.observed_value.isna().all())

    def test_workbook_overwrite_guard(self):
        self.build()
        with self.assertRaises(FileExistsError):
            self.build()


if __name__ == "__main__":
    unittest.main()
