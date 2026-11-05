"""Audit modeling-manifest exposure-ratio flags without changing the source data."""

import argparse
from pathlib import Path

import pandas as pd

if __package__:
    from .review_utils import load_development, protect_submitted_outputs
else:
    from review_utils import load_development, protect_submitted_outputs

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/processed/modeling_v1")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/count_regression_review")
    args = parser.parse_args()
    output = protect_submitted_outputs(args.out, ROOT)
    train, validation = load_development(args.data_dir)
    dev = pd.concat([train, validation], ignore_index=True)
    summary = dev.groupby("dataset_split").agg(
        rows=("pair_id", "size"), flagged_rows=("exposure_review_flag", "sum")
    ).reset_index()
    summary["sensitivity_rows"] = summary.rows - summary.flagged_rows
    output.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output / "exposure_flag_audit_summary.csv", index=False)
    dev.loc[dev.exposure_review_flag].to_csv(output / "exposure_flagged_development_rows.csv",
                                           index=False)
    print(summary.to_string(index=False))
    print("These are ratio-review flags, not upstream zero-hours/zero-employees flags.")


if __name__ == "__main__":
    main()
