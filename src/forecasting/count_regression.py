"""Reviewed Package A runs. Original artifacts/count_regression stays unchanged.

Run: uv run --locked python -m src.forecasting.count_regression
"""

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

if __package__:
    from .review_utils import (
        EPS,
        FEATURES,
        RUNS,
        TARGET,
        cohort,
        fingerprints,
        implied_zero_probability,
        load_development,
        protect_submitted_outputs,
        run_file,
    )
else:
    from review_utils import (
        EPS,
        FEATURES,
        RUNS,
        TARGET,
        cohort,
        fingerprints,
        implied_zero_probability,
        load_development,
        protect_submitted_outputs,
        run_file,
    )

ROOT = Path(__file__).resolve().parents[2]
LOG_ALPHAS = [0.0, 0.01, 0.1, 1.0]


def poisson_pipeline(alpha=1.0, log_features=False):
    steps = [FunctionTransformer(np.log1p)] if log_features else []
    return make_pipeline(*steps, StandardScaler(), PoissonRegressor(alpha=alpha, max_iter=1000))


def tune_log_poisson(train):
    fit = train.loc[train.feature_year.lt(2022)]
    holdout = train.loc[train.feature_year.eq(2022)]
    if fit.empty or holdout.empty:
        raise ValueError("The inner temporal holdout requires training years before and in 2022")
    rows = []
    for alpha in LOG_ALPHAS:
        model = poisson_pipeline(alpha, log_features=True).fit(fit[FEATURES], fit[TARGET])
        prediction = model.predict(holdout[FEATURES])
        rows.append({"alpha": alpha,
                     "inner_mae": mean_absolute_error(holdout[TARGET], prediction),
                     "inner_deviance": mean_poisson_deviance(holdout[TARGET], prediction)})
    table = pd.DataFrame(rows).sort_values(["inner_mae", "inner_deviance", "alpha"])
    return float(table.iloc[0].alpha), table


def fit_models(train, validation):
    import statsmodels.api as sm

    predictions = {"persistence_pred": validation.dart_count_t.to_numpy()}
    details = {"Persistence": {"column": "persistence_pred", "family": "point",
                                "alpha": None, "training_seconds": 0.0}}
    coefficients = []
    best_alpha, tuning = tune_log_poisson(train)
    for name, column, alpha, log_features in [
        ("Poisson", "poisson_pred", 1.0, False),
        ("Poisson (log features)", "poisson_log_pred", best_alpha, True),
    ]:
        start = time.perf_counter()
        model = poisson_pipeline(alpha, log_features).fit(train[FEATURES], train[TARGET])
        seconds = time.perf_counter() - start
        predictions[column] = model.predict(validation[FEATURES])
        estimator = model[-1]
        if estimator.n_iter_ >= estimator.max_iter:
            raise RuntimeError(f"{name} reached its iteration limit; inspect convergence")
        details[name] = {"column": column, "family": "poisson", "alpha": None,
                         "regularization_alpha": alpha, "log_features": log_features,
                         "training_seconds": seconds, "converged": True}
        for feature, value in zip(["intercept"] + FEATURES,
                                  [estimator.intercept_, *estimator.coef_], strict=True):
            coefficients.append({"model": name, "feature": feature, "coefficient": value,
                                 "scale": "standardized log1p" if log_features else "standardized"})
    x_train = sm.add_constant(np.log1p(train[FEATURES]), has_constant="add")
    x_validation = sm.add_constant(np.log1p(validation[FEATURES]), has_constant="add")
    for estimated in [False, True]:
        name = "Negative Binomial (Estimated Alpha)" if estimated else "Negative Binomial"
        column = "negative_binomial_estimated_pred" if estimated else "negative_binomial_pred"
        start = time.perf_counter()
        if estimated:
            fit = sm.NegativeBinomial(train[TARGET], x_train, loglike_method="nb2").fit(
                method="bfgs", maxiter=1000, disp=False)
            converged = bool(fit.mle_retvals["converged"])
            alpha = float(fit.params["alpha"])
        else:
            fit = sm.GLM(train[TARGET], x_train,
                         family=sm.families.NegativeBinomial(alpha=1.0)).fit(maxiter=1000)
            converged, alpha = bool(fit.converged), 1.0
        seconds = time.perf_counter() - start
        if not converged:
            raise RuntimeError(f"{name} did not converge")
        predictions[column] = np.asarray(fit.predict(x_validation))
        details[name] = {"column": column, "family": "negative_binomial", "alpha": alpha,
                         "training_seconds": seconds, "converged": converged}
        for feature, value in fit.params.items():
            coefficients.append({"model": name, "feature": feature, "coefficient": value,
                                 "scale": "NB2 dispersion" if feature == "alpha" else "log1p"})
    return predictions, details, pd.DataFrame(coefficients), tuning


def evaluate_run(train, validation, run, output):
    predictions, settings, coefficients, tuning = fit_models(train, validation)
    saved = validation[["pair_id", TARGET]].rename(columns={TARGET: "actual_count"}).copy()
    saved["run"] = run
    y = validation[TARGET].to_numpy()
    rows, calibration, errors = [], [], []
    for name, config in settings.items():
        p = np.asarray(predictions[config["column"]], dtype=float)
        if not np.isfinite(p).all() or (p < 0).any():
            raise RuntimeError(f"{name} produced invalid predictions")
        saved[config["column"]] = p
        zero = implied_zero_probability(p, config["family"], config["alpha"])
        rows.append({"model": name, "run": run, "train_rows": len(train),
                     "validation_rows": len(validation),
                     "mae": mean_absolute_error(y, p), "rmse": np.mean((y - p) ** 2) ** 0.5,
                     "poisson_deviance": mean_poisson_deviance(y, np.maximum(p, EPS)),
                     "mean_pred": p.mean(), "mean_actual": y.mean(),
                     "implied_zero_share": float(zero.mean()),
                     "observed_zero_share": float((y == 0).mean()),
                     "alpha": config["alpha"], "training_seconds": config["training_seconds"]})
        groups = pd.qcut(pd.Series(p).rank(method="first"), 5, labels=False)
        part = pd.DataFrame({"risk_group": groups, "actual": y, "predicted": p})
        calibration.append(part.groupby("risk_group").agg(
            actual_mean=("actual", "mean"), predicted_mean=("predicted", "mean"),
            count=("actual", "size")).reset_index().assign(model=name))
        part = validation[["pair_id", *FEATURES]].copy()
        part["actual_count"], part["prediction"] = y, p
        part["absolute_error"] = np.abs(y - p)
        errors.append(part.nlargest(5, "absolute_error").assign(model=name))
    saved.to_csv(output / run_file("validation_predictions", run), index=False)
    table = pd.DataFrame(rows)
    table.to_csv(output / run_file("model_metrics", run), index=False)
    coefficients.to_csv(output / run_file("coefficients", run), index=False)
    tuning.to_csv(output / run_file("poisson_log_tuning", run), index=False)
    pd.concat(calibration).to_csv(output / run_file("calibration", run), index=False)
    pd.concat(errors).to_csv(output / run_file("largest_prediction_errors", run), index=False)
    print(f"\n{run}: train={len(train)}, validation={len(validation)}")
    print(table[["model", "mae", "rmse", "poisson_deviance"]].to_string(index=False))
    return {"train_rows": len(train), "validation_rows": len(validation), "models": settings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/processed/modeling_v1")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/count_regression_review")
    args = parser.parse_args()
    output = protect_submitted_outputs(args.out, ROOT)
    train, validation = load_development(args.data_dir)
    output.mkdir(parents=True, exist_ok=True)
    runs = {}
    for run in RUNS:
        tr, va = cohort(train, validation, run)
        runs[run] = evaluate_run(tr, va, run, output)
    import sklearn
    import statsmodels

    metadata = {
        "python": platform.python_version(), "numpy": np.__version__,
        "pandas": pd.__version__, "sklearn": sklearn.__version__,
        "statsmodels": statsmodels.__version__, "features": FEATURES, "target": TARGET,
        "final_test_scored": False, "runs": runs, "poisson_log_alpha_grid": LOG_ALPHAS,
        "tuning_holdout": "feature_year 2022 within training; select by MAE",
        "poisson_deviance_floor": EPS,
        "deviance_note": "Persistence deviance uses predictions clipped to this floor; "
                         "it depends on the floor and does not validate a count distribution.",
        "source_sha256": fingerprints([args.data_dir / "forecasting_reference.csv",
                                       args.data_dir / "forecasting_row_manifest.csv"]),
    }
    (output / "run_settings.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
