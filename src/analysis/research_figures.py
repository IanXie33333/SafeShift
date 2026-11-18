"""Create presentation figures and evidence-linked findings from the two aggregates."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

COLORS = ["#246A8D", "#20A39E", "#E5A335", "#8057A0"]
SIZES = {"lt_50": "Fewer than 50", "50_249": "50–249", "250_999": "250–999", "1000_plus": "1,000+"}


def finish(fig, path, footer):
    fig.text(0.02, 0.02, footer, fontsize=9, color="#526371", wrap=True)
    fig.tight_layout(rect=(0, 0.065, 1, 0.96))
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)


def create(annual_path, case_path, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    annual = pd.read_csv(annual_path)
    cases = pd.read_csv(case_path, dtype={"soc_major": str})
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "axes.labelcolor": "#263746",
                         "text.color": "#12263A", "axes.edgecolor": "#CFD8DE"})
    total = annual.groupby(["year", "scenario"], observed=True).agg(
        cases=("dart_case_count", "sum"), hours=("hours_sum", "sum"),
        reporters=("establishment_year_count", "sum")).reset_index()
    total["rate"] = 200000 * total.cases / total.hours.where(total.hours.gt(0))
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.4))
    fig.suptitle("Reported counts and exposure-adjusted rates tell different stories", fontsize=19, x=0.02, ha="left")
    primary = total.loc[total.scenario.eq("primary")]
    axes[0].plot(primary.year, primary.cases, marker="o", color=COLORS[0], linewidth=2.8)
    axes[0].set(title="Reported DART cases", xlabel="Reporting year", ylabel="Cases")
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))
    for scenario, label, color in [("primary", "Primary reported data", COLORS[0]),
                                    ("exposure_sensitivity", "Exposure sensitivity", COLORS[1])]:
        selected = total.loc[total.scenario.eq(scenario)]
        axes[1].plot(selected.year, selected.rate, marker="o", label=label, color=color, linewidth=2.6)
    axes[1].set(title="DART cases per 100 FTE", xlabel="Reporting year", ylabel="Cases per 200,000 reported hours", ylim=(0, None))
    axes[1].legend(frameon=False, fontsize=9, loc="lower left")
    for axis in axes:
        axis.set_xticks([2016, 2018, 2020, 2022, 2024, 2025])
        axis.grid(axis="y", alpha=0.18)
    finish(fig, output_dir / "01_counts_and_rates.png",
           "Reporting coverage and composition vary by year. The 2025 primary denominator contains an extreme hours report.\n"
           "Sensitivity excludes the predeclared hours-per-employee review flags; it does not establish national incidence.")
    fig, ax = plt.subplots(figsize=(12.5, 6.8))
    for (key, label), color in zip(SIZES.items(), COLORS, strict=True):
        selected = annual.loc[annual.scenario.eq("exposure_sensitivity") & annual.size_group.eq(key)].copy()
        selected["pooled_rate"] = 200000 * selected.dart_case_count / selected.hours_sum
        ax.plot(selected.year, selected.pooled_rate, marker="o", label=label, color=color, linewidth=2.4)
    ax.set(title="Observed DART rates by annual-average establishment size", xlabel="Reporting year", ylabel="DART cases per 100 FTE", ylim=(0, None))
    ax.legend(title="Annual average employees", frameon=False, ncol=2)
    ax.grid(axis="y", alpha=0.18)
    finish(fig, output_dir / "02_size_rates.png",
           "Exposure-sensitivity cohort. Rates use summed cases and summed hours. Differences are descriptive, not causal size effects.")
    primary_cases = cases.loc[cases.scenario.eq("primary")]
    mechanism = primary_cases.groupby(["year", "mechanism_label"], observed=True).case_report_count.sum().unstack("year", fill_value=0)
    mechanism = mechanism.loc[mechanism.sum(axis=1).sort_values().index]
    shares = mechanism.div(mechanism.sum(axis=0), axis=1) * 100
    fig, ax = plt.subplots(figsize=(12.5, 7.2))
    positions = np.arange(len(shares))
    for i, year in enumerate(shares):
        ax.barh(positions + (i - 0.5) * 0.34, shares[year], height=0.32, label=str(year), color=COLORS[i])
    ax.set_yticks(positions, shares.index)
    ax.set(title="Mechanisms among reported warehouse cases", xlabel="Share of date-aligned reports (%)")
    ax.legend(frameon=False)
    ax.grid(axis="x", alpha=0.18)
    finish(fig, output_dir / "03_mechanism_shares.png",
           "Unknown and Other mechanisms remain in the denominator. Supplied machine-assigned labels are harmonized by source year.\n"
           "The annual and case-detail reporting populations differ.")
    occupations = primary_cases.groupby("soc_major_label", observed=True).case_report_count.sum().sort_values().tail(12)
    fig, ax = plt.subplots(figsize=(13, 7.5))
    ax.barh(occupations.index, occupations.values, color=COLORS[0])
    ax.set(title="Occupational groups appearing most often in the case reports", xlabel="Source case reports")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    ax.grid(axis="x", alpha=0.18)
    finish(fig, output_dir / "04_occupation_frequency.png",
           "SOC 2018 major groups; at most 12 groups shown here. Full groups remain in Tableau.\n"
           "These are report counts, not occupation-specific injury rates or numbers of unique injured workers.")
    outcome_cols = ["outcome_dafw_count", "outcome_djtr_count", "outcome_other_count",
                    "outcome_death_count", "outcome_unknown_count"]
    if set(outcome_cols) <= set(primary_cases):
        outcome = primary_cases.groupby("year")[outcome_cols].sum()
        labels = ["Days away", "Restriction / job transfer", "Other recordable", "Death", "Unknown"]
        fig, ax = plt.subplots(figsize=(12, 6.4))
        bottom = np.zeros(len(outcome))
        for field, label, color in zip(outcome_cols, labels, [*COLORS, "#9AA5AE"], strict=True):
            values = 100 * outcome[field] / outcome.sum(axis=1)
            ax.bar(outcome.index.astype(str), values, bottom=bottom, label=label, color=color, width=0.5)
            bottom += values.to_numpy()
        ax.set(title="Reported work-time outcomes", ylabel="Share of date-aligned reports (%)", ylim=(0, 100))
        ax.legend(frameon=False, bbox_to_anchor=(1.01, 1), loc="upper left")
        finish(fig, output_dir / "05_reported_outcomes.png",
               "Each report has one most-serious outcome. A days-away case can also contain restricted days.\n"
               "Outcome frequency remains distinct from duration, paid hours lost, and financial cost.")
    known = primary_cases.case_report_count.sum()
    top_mechanisms = primary_cases.groupby("mechanism_label").case_report_count.sum().sort_values(ascending=False)
    occupation_counts = primary_cases.groupby("soc_major_label").case_report_count.sum().sort_values(ascending=False)
    unknown_count = int(occupation_counts.get("Unknown occupation", 0))
    observations = []
    sensitivity = annual.loc[annual.scenario.eq("exposure_sensitivity")].copy()
    if not sensitivity.empty:
        latest = int(sensitivity.year.max())
        size_rates = sensitivity.loc[sensitivity.year.eq(latest) & sensitivity.hours_sum.gt(0)].copy()
        size_rates["rate"] = 200000 * size_rates.dart_case_count / size_rates.hours_sum
        if not size_rates.empty:
            low = size_rates.loc[size_rates.rate.idxmin()]
            high = size_rates.loc[size_rates.rate.idxmax()]
            observations.append(
                f"In {latest}, exposure-sensitivity DART rates ranged from {low.rate:.2f} per 100 FTE "
                f"for establishments with {SIZES[low.size_group]} annual-average employees to {high.rate:.2f} "
                f"for {SIZES[high.size_group]}. These are observed reporting-group differences, not causal size effects. "
                "Evidence: annual_size_summary.csv, exposure_sensitivity, selected year; summed cases / summed hours.")
    observations.append(
        f"The most frequently appearing occupational group is **{occupation_counts.index[0]}**, "
        f"with {int(occupation_counts.iloc[0]):,} reports ({100 * occupation_counts.iloc[0] / known:.2f}%). "
        "This is a frequency among reports, not an occupation-specific injury rate. "
        "Evidence: case_pattern_summary.csv, primary, summed by soc_major_label.")
    observations.append(
        f"Unknown occupation accounts for {unknown_count:,} reports ({100 * unknown_count / known:.2f}%). "
        "These reports remain in all primary frequency denominators. "
        "Evidence: case_pattern_summary.csv, primary, Unknown occupation.")
    if "outcome_dafw_count" in primary_cases:
        dafw_count = int(primary_cases.outcome_dafw_count.sum())
        observations.append(
            f"The most-serious outcome is days away in {dafw_count:,} reports "
            f"({100 * dafw_count / known:.2f}%). This describes the frequency of that outcome, not days lost or cost. "
            "Evidence: case_pattern_summary.csv, primary, SUM(outcome_dafw_count) / SUM(case_report_count).")
    findings = [
        "# Descriptive findings and presentation evidence", "",
        "This project is descriptive, comparative and exploratory; it is not focused on predictive analysis.", "",
        "The annual and case-detail tables describe different reporting populations and must be presented separately.", "",
        f"There are {int(known):,} date-aligned source case reports in the primary case profile.", "",
        (f"The most frequent harmonized mechanism is **{top_mechanisms.index[0]}**, with "
         f"{int(top_mechanisms.iloc[0]):,} reports ({100 * top_mechanisms.iloc[0] / known:.2f}% of reports). "
         "Evidence: case_pattern_summary.csv, primary scenario, summed across years and occupations."), "",
        *[paragraph for observation in observations for paragraph in [observation, ""]],
        ("The figures compare reported counts with pooled exposure-adjusted rates, then show size, mechanism, occupation, "
         "and outcome patterns. Larger totals alone do not establish higher risk."), "",
        "## Presentation sequence", "",
        "1. Revised question and descriptive scope.",
        "2. Two data populations, year coverage, and source-case versus establishment-year units.",
        "3. Counts versus rates, with the 2025 exposure-denominator issue visible.",
        "4. Size comparisons under the documented exposure sensitivity.",
        "5. Mechanism composition including Unknown and Other.",
        "6. Occupational report patterns and most-serious outcome composition.",
        "7. Day measures only if their source-matched policy clears them; otherwise show the limitation explicitly.",
        "8. Coverage, classification uncertainty, and conclusions limited to reporting establishments.", "",
        "## Display gates and limits", "",
        ("Annual reported-day totals remain under review. Case-day publication follows the source-matched case policy. "
         "Do not substitute a zero for a withheld measure, interpret report shares as occupational incidence, or infer causation."), "",
        "Native Tableau opening and displayed-value QA remain necessary even when package/XML checks pass.", "",
    ]
    (output_dir / "findings_and_slide_outline.md").write_text("\n".join(findings))
    total.to_csv(output_dir / "annual_figure_reference.csv", index=False)
    shares.to_csv(output_dir / "mechanism_share_reference.csv")
    print(f"Presentation figures and evidence outline: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annual", type=Path, default=Path("data/processed/research_v2/annual_size_summary.csv"))
    parser.add_argument("--cases", type=Path, default=Path("data/processed/research_v2/case_pattern_summary.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/research_v2/presentation"))
    args = parser.parse_args()
    create(args.annual, args.cases, args.output_dir)


if __name__ == "__main__":
    main()
