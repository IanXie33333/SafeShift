"""Check figure production using explicitly synthetic case data."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.analysis.research_figures import create


class ResearchFigureChecks(unittest.TestCase):
    def test_figures_and_references_are_generated(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            annual = []
            cases = []
            for year in [2023, 2024]:
                for scenario in ["primary", "exposure_sensitivity"]:
                    annual.append({"year": year, "scenario": scenario, "size_group": "lt_50",
                                   "dart_case_count": 4, "hours_sum": 200000,
                                   "establishment_year_count": 2})
                cases.append({"year": year, "scenario": "primary", "soc_major_label": "SYNTHETIC group",
                              "mechanism_label": "SYNTHETIC mechanism", "case_report_count": 10,
                              "outcome_dafw_count": 5, "outcome_djtr_count": 3,
                              "outcome_other_count": 2, "outcome_death_count": 0, "outcome_unknown_count": 0})
            pd.DataFrame(annual).to_csv(root / "annual.csv",index=False)
            pd.DataFrame(cases).to_csv(root / "cases.csv",index=False)
            create(root / "annual.csv", root / "cases.csv", root / "figures")
            figures = list((root / "figures").glob("*.png"))
            self.assertEqual(len(figures), 5)
            self.assertTrue(all(path.stat().st_size > 5000 for path in figures))
            references = pd.read_csv(root / "figures/annual_figure_reference.csv")
            self.assertTrue(references.rate.eq(4).all())
            self.assertTrue((root / "figures/findings_and_slide_outline.md").is_file())


if __name__ == "__main__":
    unittest.main()
