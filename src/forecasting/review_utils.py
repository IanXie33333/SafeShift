"""Validation and output safeguards for the post-review forecasting runs."""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["dart_count_t", "employee_count_t", "hours_worked_t"]
TARGET = "dart_count_t1"
EPS = 1e-10
RUNS = ("primary", "sensitivity_excl_exposure_flags")


def protect_original_output(output: Path, original: Path) -> Path:
    output, original = output.resolve(), original.resolve()
    if output == original or original in output.parents or output in original.parents:
        raise ValueError(f"Choose a new output directory; submitted results are protected: {original}")
    return output


def protect_submitted_outputs(output, root):
    for folder in ["count_regression", "lightgbm_forecast", "metrics", "figures"]:
        protect_original_output(output, root / "artifacts" / folder)
    return output.resolve()


def fingerprints(paths):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def load_development(data_dir):
    frame = pd.read_csv(data_dir / "forecasting_reference.csv",
                        dtype={"pair_id": "string", "establishment_id": "string"})
    frame = frame.loc[frame.dataset_split.isin(["train", "validation"])].copy()
    flags = pd.read_csv(data_dir / "forecasting_row_manifest.csv",
                        usecols=["pair_id", "exposure_review_flag"], dtype={"pair_id": "string"})
    frame = frame.merge(flags, on="pair_id", how="left", validate="one_to_one")
    parsed = frame.exposure_review_flag.astype("string").str.lower().map(
        {"true": True, "false": False})
    if parsed.isna().any():
        raise ValueError("Every development pair must have an explicit exposure_review_flag")
    frame["exposure_review_flag"] = parsed.astype(bool)
    values = frame[FEATURES + [TARGET]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Forecasting predictors and targets must be finite and nonnegative")
    if (frame[["employee_count_t", "hours_worked_t"]] <= 0).any().any():
        raise ValueError("Employees and hours must be positive")
    train = frame.loc[frame.dataset_split.eq("train")].copy()
    validation = frame.loc[frame.dataset_split.eq("validation")].copy()
    if (len(train), len(validation)) != (21785, 5019):
        raise ValueError("Expected frozen v1: 21,785 training and 5,019 validation rows")
    if not train.feature_year.between(2016, 2022).all():
        raise ValueError("Unexpected training years")
    if not validation.feature_year.eq(2023).all():
        raise ValueError("Validation must be 2023 -> 2024")
    if not frame.target_year.eq(frame.feature_year + 1).all():
        raise ValueError("Forecasting pairs must be consecutive years")
    return train, validation


def cohort(train, validation, run):
    if run == "primary":
        return train.copy(), validation.copy()
    if run != RUNS[1]:
        raise ValueError(f"Unknown run: {run}")
    return (train.loc[~train.exposure_review_flag].copy(),
            validation.loc[~validation.exposure_review_flag].copy())


def run_file(stem, run):
    return f"{stem}{'' if run == 'primary' else '_' + run}.csv"


def implied_zero_probability(prediction, family, alpha=None):
    prediction = np.asarray(prediction, dtype=float)
    if family == "poisson":
        return np.exp(-prediction)
    if family == "negative_binomial":
        if alpha is None or not np.isfinite(alpha) or alpha <= 0:
            raise ValueError("NB2 zero probabilities require positive fitted dispersion")
        return np.exp(-np.log1p(alpha * prediction) / alpha)
    return np.full(len(prediction), np.nan)


def read_package_a_run(directory, run, validation, train_rows):
    pp = directory / run_file("validation_predictions", run)
    mp = directory / run_file("model_metrics", run)
    if not pp.exists() or not mp.exists():
        raise FileNotFoundError(f"Run corrected Package A first: missing {run} outputs. "
                                "Sensitivity requires refitted models, not filtered old predictions.")
    predictions = pd.read_csv(pp, dtype={"pair_id": "string"})
    metrics = pd.read_csv(mp).set_index("model")
    if "run" not in predictions or not predictions.run.eq(run).all():
        raise ValueError("Package A predictions must identify the same run")
    if predictions.pair_id.duplicated().any():
        raise ValueError("Duplicate Package A prediction IDs")
    if set(predictions.pair_id) != set(validation.pair_id):
        raise ValueError("Package A predictions must cover exactly this validation cohort")
    if not metrics.train_rows.eq(train_rows).all():
        raise ValueError("Package A models were not refitted on the same training cohort")
    if not metrics.validation_rows.eq(len(validation)).all():
        raise ValueError("Package A validation cohort size differs")
    aligned = validation[["pair_id", TARGET]].merge(
        predictions, on="pair_id", how="left", validate="one_to_one")
    if not np.array_equal(aligned.actual_count, aligned[TARGET]):
        raise ValueError("Package A outcomes differ from the frozen data")
    aligned = aligned.drop(columns=TARGET)
    values = aligned[[c for c in aligned if c.endswith("_pred")]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Invalid Package A predictions")
    return aligned, metrics
