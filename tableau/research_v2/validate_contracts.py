"""Validate the WP3 Tableau input contracts (annual + case summaries and coverage tables).

Usage: python validate_contracts.py --annual-dir DIR --case-dir DIR --annual-ref CSV --case-ref CSV
Exit code 1 if any check fails. Prints one PASS/FAIL line per check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SIZE_GROUPS = ["lt_50", "50_249", "250_999", "1000_plus"]
ANNUAL_SCENARIOS = {"primary", "exposure_sensitivity"}
CASE_SCENARIOS = {"primary", "day_review_sensitivity"}
DAY_STATUS = {"ready", "partial_valid_values", "blocked_review"}
MECHANISMS = {
    "transportation", "falls_slips_trips", "harmful_exposure", "object_equipment_contact",
    "overexertion_bodily_reaction", "other_reported_mechanism", "unknown_missing_mechanism",
}
SUBTOTAL_TOKENS = {"all", "total", "overall", "(all)", "subtotal"}


def check(results: list, name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""))


def validate_annual(d: Path, ref: Path, res: list) -> None:
    a = pd.read_csv(d / "annual_size_summary.csv")
    cov = pd.read_csv(d / "annual_coverage.csv")
    key = ["year", "size_group", "scenario"]
    check(res, "annual: unique grain year x size_group x scenario", not a.duplicated(key).any())
    check(res, "annual: size groups are the four expected groups", set(a.size_group) == set(SIZE_GROUPS))
    check(res, "annual: scenarios are primary/exposure_sensitivity", set(a.scenario) == ANNUAL_SCENARIOS)
    check(res, "annual: years 2016-2025, 4 groups x 2 scenarios each",
          sorted(a.year.unique()) == list(range(2016, 2026)) and len(a) == 80)
    sub = a[["size_group", "scenario"]].astype(str).apply(lambda c: c.str.lower().isin(SUBTOTAL_TOKENS))
    check(res, "annual: no subtotal/all rows", not sub.any().any())
    check(res, "annual: dart = dafw + djtr", (a.dart_case_count == a.dafw_case_count + a.djtr_case_count).all())
    check(res, "annual: counts and hours non-negative, no nulls",
          (a[["establishment_year_count", "hours_sum", "dart_case_count"]] >= 0).all().all()
          and a[["establishment_year_count", "hours_sum", "dart_case_count"]].notna().all().all())
    check(res, "annual: day statuses within enum",
          set(a.dafw_days_status) <= DAY_STATUS and set(a.djtr_days_status) <= DAY_STATUS)
    for m in ("dafw", "djtr"):
        blocked = a[f"{m}_days_status"] == "blocked_review"
        check(res, f"annual: {m} day sums blank where blocked_review", a.loc[blocked, f"{m}_days_sum"].isna().all())
    order = {g: i + 1 for i, g in enumerate(SIZE_GROUPS)}
    check(res, "annual: size_group_order consistent", (a.size_group.map(order) == a.size_group_order).all())
    r = pd.read_csv(ref)
    g = a.groupby(["year", "scenario"], as_index=False).agg(
        est=("establishment_year_count", "sum"), hrs=("hours_sum", "sum"), dart=("dart_case_count", "sum"))
    m = g.merge(r, on=["year", "scenario"], how="outer", indicator=True)
    check(res, "annual: summary sums reconcile exactly to WP1 reference counts",
          (m._merge == "both").all() and (m.est == m.establishment_year_count).all()
          and (m.dart == m.dart_case_count).all() and ((m.hrs - m.hours_sum).abs() < 1).all())
    rate = 200000 * m.dart / m.hrs
    check(res, "annual: recomputed pooled rate within 1e-6 of WP1 reference",
          ((rate - m.dart_rate_reference).abs() < 1e-6).all(),
          f"max abs diff {float((rate - m.dart_rate_reference).abs().max()):.2e}")
    check(res, "annual coverage: unique year x scenario, 20 rows",
          not cov.duplicated(["year", "scenario"]).any() and len(cov) == 20)
    prim = cov[cov.scenario == "primary"].set_index("year")
    gp = a[a.scenario == "primary"].groupby("year").establishment_year_count.sum()
    check(res, "annual coverage: primary establishment_years match summary", (prim.establishment_years == gp).all())


def validate_case(d: Path, ref: Path, res: list) -> None:
    c = pd.read_csv(d / "case_pattern_summary.csv", dtype={"soc_major_group": str})
    cov = pd.read_csv(d / "case_coverage.csv")
    key = ["year", "mechanism_group", "soc_major_group", "scenario"]
    check(res, "case: unique grain year x mechanism x SOC x scenario", not c.duplicated(key).any())
    check(res, "case: scenarios primary/day_review_sensitivity", set(c.scenario) == CASE_SCENARIOS)
    check(res, "case: years 2023 and 2024 only", set(c.year) == {2023, 2024})
    check(res, "case: mechanism groups within the 7 expected", set(c.mechanism_group) <= MECHANISMS)
    check(res, "case: no subtotal rows",
          not c.soc_major_group.str.lower().isin(SUBTOTAL_TOKENS).any()
          and not c.mechanism_group.str.lower().isin(SUBTOTAL_TOKENS).any())
    out = c[[f"outcome_{k}_count" for k in ("death", "dafw", "djtr", "other", "unknown")]].sum(axis=1)
    check(res, "case: outcome counts sum to case_report_count", (out == c.case_report_count).all())
    check(res, "case: known day counts <= reports",
          ((c.dafw_days_known_report_count <= c.case_report_count)
           & (c.djtr_days_known_report_count <= c.case_report_count)).all())
    check(res, "case: day statuses within enum",
          set(c.dafw_days_status) <= DAY_STATUS and set(c.djtr_days_status) <= DAY_STATUS)
    inc = c.groupby(["year", "scenario"]).case_report_count.sum().rename("n").reset_index()
    m = inc.merge(cov, on=["year", "scenario"])
    check(res, "case: summary totals equal case_coverage included_report_count",
          len(m) == 4 and (m.n == m.included_report_count).all())
    r = pd.read_csv(ref, dtype={"soc_major_group": str})
    ys = r[r.reference_level == "year_scenario"]
    ys = ys[ys.year != "all"].assign(year=lambda x: x.year.astype(int))
    mm = inc.merge(ys, on=["year", "scenario"])
    check(res, "case: summary totals equal reference_totals year x scenario",
          len(mm) == 4 and (mm.n == mm.case_report_count).all())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--annual-dir", type=Path, required=True)
    p.add_argument("--case-dir", type=Path, required=True)
    p.add_argument("--annual-ref", type=Path, required=True)
    p.add_argument("--case-ref", type=Path, required=True)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    res: list = []
    validate_annual(a.annual_dir, a.annual_ref, res)
    validate_case(a.case_dir, a.case_ref, res)
    if a.out:
        pd.DataFrame(res, columns=["check", "passed", "detail"]).to_csv(a.out, index=False)
    bad = [r for r in res if not r[1]]
    print(f"\n{len(res) - len(bad)}/{len(res)} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
