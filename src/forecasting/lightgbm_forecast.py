# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "lightgbm>=4.7,<5",
#     "matplotlib>=3.9",
#     "numpy>=2.0,<3",
#     "pandas>=2.2,<3",
#     "scikit-learn>=1.5",
# ]
# ///
"""Package B: LightGBM (Poisson objective) next-year DART forecaster, compared with Package A.

Run from the repository root (dependencies are pinned in lightgbm_forecast.py.lock):
  uv run --locked --script src/forecasting/lightgbm_forecast.py

Uses only train/validation rows of SafeShift modeling v1; the final-test split is never loaded.
"""

import argparse
import itertools
import json
import time
from pathlib import Path

import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance, root_mean_squared_error

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ["dart_count_t", "employee_count_t", "hours_worked_t"]
TARGET = "dart_count_t1"
SEED = 42
EPS = 1e-10  # same clip as Package A, so zero predictions (persistence) get a finite deviance
LGB_NAME = "LightGBM Poisson"
# Package A wide prediction columns -> display names; A's metrics-file names for runtime lookup
A_MODELS = {
    "persistence_pred": ("Persistence", "Persistence"),
    "poisson_pred": ("Poisson", "Poisson"),
    "negative_binomial_pred": ("Negative Binomial (fixed alpha)", "Negative Binomial"),
    "negative_binomial_estimated_pred": (
        "Negative Binomial (estimated alpha)", "Negative Binomial (Estimated Alpha)"),
}
MODELS = [LGB_NAME] + [name for name, _ in A_MODELS.values()]
COLORS = dict(zip(MODELS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]))
GRID = {
    "num_leaves": [7, 15, 31],
    "learning_rate": [0.03, 0.1],
    "min_child_samples": [20, 100],
    "reg_lambda": [0.0, 1.0],
}
BASE_PARAMS = {"objective": "poisson", "random_state": SEED, "deterministic": True,
                   "force_row_wise": True, "n_jobs": 1, "verbose": -1}
SIZE_BINS = ([0, 50, 250, 1000, np.inf], ["<50", "50-249", "250-999", "1000+"])
COUNT_BINS = ([-0.5, 0.5, 2.5, 9.5, 49.5, np.inf], ["0", "1-2", "3-9", "10-49", "50+"])


def load(data_dir):
    df = pd.read_csv(data_dir / "forecasting_reference.csv",
                     dtype={"pair_id": "string", "establishment_id": "string"})
    flags = pd.read_csv(data_dir / "forecasting_row_manifest.csv",
                        usecols=["pair_id", "exposure_review_flag"], dtype={"pair_id": "string"})
    df = df[df.dataset_split.isin(["train", "validation"])]
    df = df.merge(flags, on="pair_id", how="left", validate="one_to_one")
    assert df.exposure_review_flag.notna().all() and df.dataset_split.ne("final_test").all()
    return df[df.dataset_split.eq("train")], df[df.dataset_split.eq("validation")]


def tune_and_fit(train):
    """Grid-search on an inner temporal holdout (last training year), then refit on all train.

    Validation rows are never used for tuning, so the leaderboard comparison stays clean.
    """
    inner_fit = train[train.feature_year < 2022]
    inner_val = train[train.feature_year == 2022]
    rows = []
    for values in itertools.product(*GRID.values()):
        params = dict(zip(GRID, values))
        model = lgb.LGBMRegressor(n_estimators=3000, **params, **BASE_PARAMS)
        model.fit(inner_fit[FEATURES], inner_fit[TARGET],
                  eval_X=(inner_val[FEATURES],), eval_y=(inner_val[TARGET],), eval_metric="poisson",
                  callbacks=[lgb.early_stopping(100, verbose=False)])
        pred = model.predict(inner_val[FEATURES])
        rows.append({**params, "n_estimators": model.best_iteration_,
                     "inner_deviance": mean_poisson_deviance(inner_val[TARGET], pred),
                     "inner_mae": mean_absolute_error(inner_val[TARGET], pred)})
    tuning = pd.DataFrame(rows).sort_values("inner_deviance", ignore_index=True)
    best = tuning.iloc[0][list(GRID) + ["n_estimators"]].to_dict()
    best["num_leaves"], best["min_child_samples"], best["n_estimators"] = (
        int(best["num_leaves"]), int(best["min_child_samples"]), int(best["n_estimators"]))
    start = time.perf_counter()
    model = lgb.LGBMRegressor(**best, **BASE_PARAMS).fit(train[FEATURES], train[TARGET])
    return model, best, tuning, time.perf_counter() - start


def metrics(y, p):
    return {
        "mae": mean_absolute_error(y, p),
        "rmse": root_mean_squared_error(y, p),
        "poisson_deviance": mean_poisson_deviance(y, np.maximum(p, EPS)),
        "mean_pred": p.mean(),
        "mean_actual": y.mean(),
        "pred_to_actual_total": p.sum() / y.sum(),
        "poisson_p0_share": np.exp(-p).mean(),  # implied P(y=0) if counts were Poisson(mu=p)
        "observed_zero_share": (y == 0).mean(),
    }


def paired_bootstrap(y, p_ref, p_other, n=1000):
    """95% CI of mean(metric(ref) - metric(other)) over resampled validation rows."""
    rng = np.random.default_rng(SEED)
    d_mae = np.abs(y - p_ref) - np.abs(y - p_other)
    dev = lambda p: 2 * (np.where(y > 0, y * np.log(np.maximum(y, EPS) / np.maximum(p, EPS)), 0)
                         - y + p)
    d_dev = dev(p_ref) - dev(p_other)
    idx = rng.integers(0, len(y), (n, len(y)))
    return {
        "mae_diff": d_mae.mean(), "mae_lo": np.percentile(d_mae[idx].mean(1), 2.5),
        "mae_hi": np.percentile(d_mae[idx].mean(1), 97.5),
        "deviance_diff": d_dev.mean(), "deviance_lo": np.percentile(d_dev[idx].mean(1), 2.5),
        "deviance_hi": np.percentile(d_dev[idx].mean(1), 97.5),
    }


def evaluate(val, preds, runtimes):
    """preds: {model name: prediction array aligned with val}. Returns leaderboard + bootstrap."""
    y = val[TARGET].to_numpy()
    board = pd.DataFrame([{"model": m, **metrics(y, p), "runtime_seconds": runtimes.get(m)}
                          for m, p in preds.items()]).sort_values("mae", ignore_index=True)
    boot = pd.DataFrame([{"vs_model": m, **paired_bootstrap(y, preds[LGB_NAME], p)}
                         for m, p in preds.items() if m != LGB_NAME])
    return board, boot


def style(ax, title):
    ax.set_title(title, loc="left", fontsize=11, color="#0b0b0b")
    ax.set_facecolor("#fcfcfb")
    ax.grid(color="#e4e3df", linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#a9a8a2")
    ax.tick_params(colors="#52514e", labelsize=9)


def save(fig, path):
    fig.patch.set_facecolor("#fcfcfb")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def sliced_errors(val, preds, column, bins, labels):
    groups = pd.cut(val[column], bins=bins, labels=labels)
    rows = []
    for m, p in preds.items():
        err = pd.DataFrame({"g": groups.values, "e": p - val[TARGET].to_numpy()})  # keeps bin order
        for g, part in err.groupby("g", observed=True):
            rows.append({"model": m, "bin": g, "n": len(part), "mae": part.e.abs().mean(),
                         "bias_pred_minus_actual": part.e.mean()})
    return pd.DataFrame(rows)


def plot_slices(table, title, xlabel, path):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bins = table.bin.unique()
    width = 0.8 / len(MODELS)
    for i, m in enumerate(MODELS):
        part = table[table.model.eq(m)].set_index("bin").reindex(bins)
        ax.bar(np.arange(len(bins)) + (i - 2) * width, part.mae, width * 0.9,
               color=COLORS[m], label=m)
    ax.set_xticks(np.arange(len(bins)), [f"{b}\n(n={n})" for b, n in
                                         table[table.model.eq(LGB_NAME)][["bin", "n"]].values])
    ax.set_yscale("log")
    ax.set_xlabel(xlabel, color="#52514e")
    ax.set_ylabel("MAE (log scale)", color="#52514e")
    style(ax, title)
    ax.legend(frameon=False, fontsize=8)
    save(fig, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/processed/modeling_v1")
    parser.add_argument("--package-a-dir", type=Path, default=ROOT / "artifacts/count_regression",
                        help="Package A artifact folder (validation_predictions.csv, model_metrics.csv)")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/lightgbm_forecast")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    train, val = load(args.data_dir)
    assert (len(train), len(val)) == (21785, 5019)
    a_preds = pd.read_csv(args.package_a_dir / "validation_predictions.csv",
                          dtype={"pair_id": "string"})
    a_runtime = pd.read_csv(args.package_a_dir / "model_metrics.csv").set_index("model")
    a = val[["pair_id", TARGET]].merge(a_preds, on="pair_id", how="left", validate="one_to_one")
    assert a.actual_count.notna().all() and np.allclose(a.actual_count, a[TARGET]), \
        "Package A predictions do not cover the same validation rows"
    assert np.allclose(a.persistence_pred, val.dart_count_t), "Package A persistence mismatch"

    runs, outputs = {}, {}
    for run, keep_train, keep_val in [
        ("primary", np.ones(len(train), bool), np.ones(len(val), bool)),
        ("sensitivity_excl_exposure_flags",
         ~train.exposure_review_flag.to_numpy(), ~val.exposure_review_flag.to_numpy()),
    ]:
        tr, va, a_run = train[keep_train], val[keep_val], a[keep_val]
        model, best, tuning, fit_seconds = tune_and_fit(tr)
        preds = {LGB_NAME: model.predict(va[FEATURES])}
        preds.update({name: a_run[col].to_numpy() for col, (name, _) in A_MODELS.items()})
        runtimes = {LGB_NAME: fit_seconds}
        runtimes.update({name: a_runtime.loc[key, "training_seconds"]
                         for name, key in A_MODELS.values() if key in a_runtime.index})
        board, boot = evaluate(va, preds, runtimes)
        runs[run] = {"train_rows": len(tr), "validation_rows": len(va), "best_params": best,
                         "final_fit_seconds": fit_seconds}
        outputs[run] = (tr, va, model, preds, board, boot, tuning)
        board.to_csv(args.out / f"leaderboard_{run}.csv", index=False)
        boot.to_csv(args.out / f"bootstrap_lightgbm_vs_others_{run}.csv", index=False)
        tuning.to_csv(args.out / f"tuning_{run}.csv", index=False)
        print(f"\n=== {run}: train {len(tr)}, validation {len(va)}; best {best}")
        print(board.round(4).to_string(index=False))
        print(boot.round(4).to_string(index=False))

    (args.out / "run_settings.json").write_text(json.dumps(
        {"seed": SEED, "features": FEATURES, "target": TARGET, "grid": GRID,
         "base_params": BASE_PARAMS, "tuning_holdout": "train rows with feature_year == 2022",
         "deviance_clip": EPS, "lightgbm_version": lgb.__version__, "runs": runs}, indent=2))

    pd.concat([
        pd.DataFrame({"pair_id": va.pair_id.to_numpy(), "y_true": va[TARGET].to_numpy(),
                      "y_pred": p, "model": m, "run": run})
        for run, (_, va, _, preds, *_) in outputs.items() for m, p in preds.items()
    ]).to_csv(args.out / "validation_predictions.csv", index=False)

    # Diagnostics on the primary run only
    tr, va, model, preds, board, _, _ = outputs["primary"]
    y = va[TARGET].to_numpy()

    calib = []
    for m, p in preds.items():
        decile = pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False) + 1
        frame = pd.DataFrame({"decile": decile, "pred": p, "actual": y})
        calib.append(frame.groupby("decile").agg(n=("pred", "size"), mean_pred=("pred", "mean"),
                                                 mean_actual=("actual", "mean"))
                     .reset_index().assign(model=m))
    calib = pd.concat(calib)
    calib.to_csv(args.out / "calibration.csv", index=False)
    fig, ax = plt.subplots(figsize=(6, 5.2))
    lim = [0.05, calib[["mean_pred", "mean_actual"]].max().max() * 1.3]
    ax.plot(lim, lim, color="#a9a8a2", linewidth=1, linestyle="--", label="Perfect calibration")
    for m in MODELS:
        part = calib[calib.model.eq(m)]
        ax.plot(part.mean_pred.clip(lower=0.05), part.mean_actual, marker="o", markersize=5,
                linewidth=2, color=COLORS[m], label=m)
    ax.set(xscale="log", yscale="log", xlim=lim, ylim=lim)
    ax.set_xlabel("Mean predicted count (decile of prediction)", color="#52514e")
    ax.set_ylabel("Mean observed count", color="#52514e")
    style(ax, "Calibration by prediction decile (validation)")
    ax.legend(frameon=False, fontsize=8)
    save(fig, args.out / "calibration.png")

    by_size = sliced_errors(va, preds, "employee_count_t", *SIZE_BINS)
    by_count = sliced_errors(va, preds, TARGET, *COUNT_BINS)
    by_size.to_csv(args.out / "error_by_size.csv", index=False)
    by_count.to_csv(args.out / "error_by_count.csv", index=False)
    plot_slices(by_size, "MAE by establishment size (validation)", "Employees in year t",
                args.out / "error_by_size.png")
    plot_slices(by_count, "MAE by observed next-year DART count (validation)",
                "Observed DART count in t+1", args.out / "error_by_count.png")

    booster = model.booster_
    shap = model.predict(va[FEATURES], pred_contrib=True)[:, :-1]  # last column is the bias
    importance = pd.DataFrame({
        "feature": FEATURES,
        "gain": booster.feature_importance("gain"),
        "split": booster.feature_importance("split"),
        "mean_abs_shap_log_mu": np.abs(shap).mean(0),
    }).sort_values("mean_abs_shap_log_mu", ascending=False)
    importance["gain_share"] = importance.gain / importance.gain.sum()
    importance.to_csv(args.out / "feature_importance.csv", index=False)
    fig, ax = plt.subplots(figsize=(6, 2.6))
    ax.barh(importance.feature[::-1], importance.mean_abs_shap_log_mu[::-1], height=0.5,
            color=COLORS[LGB_NAME])
    for i, v in enumerate(importance.mean_abs_shap_log_mu[::-1]):
        ax.text(v, i, f" {v:.2f}", va="center", fontsize=9, color="#52514e")
    ax.set_xlabel("Mean |SHAP| on log expected count", color="#52514e")
    style(ax, "LightGBM feature importance (validation)")
    save(fig, args.out / "feature_importance.png")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharex=True, sharey=True)
    for ax, m in zip(axes, [LGB_NAME, "Persistence"]):
        ax.scatter(np.log1p(y), np.log1p(preds[m]), s=8, alpha=0.35, color=COLORS[m],
                   edgecolors="none")
        top = np.log1p(max(y.max(), preds[m].max()))
        ax.plot([0, top], [0, top], color="#a9a8a2", linewidth=1, linestyle="--")
        ax.set_xlabel("log(1 + observed)", color="#52514e")
        style(ax, f"{m}: MAE {board.set_index('model').loc[m, 'mae']:.3f}")
    axes[0].set_ylabel("log(1 + predicted)", color="#52514e")
    save(fig, args.out / "pred_vs_actual.png")

    wide = va[["pair_id", "employee_count_t", "hours_worked_t", "dart_count_t", TARGET]].copy()
    for m, p in preds.items():
        wide[m] = p
    wide["lightgbm_abs_error"] = (wide[LGB_NAME] - wide[TARGET]).abs()
    median_err = wide.lightgbm_abs_error.median()
    examples = pd.concat([
        wide.nlargest(10, "lightgbm_abs_error").assign(example="largest LightGBM error"),
        wide.iloc[(wide.lightgbm_abs_error - median_err).abs().argsort()[:5]]
        .assign(example="typical (near-median) LightGBM error"),
    ])
    examples.to_csv(args.out / "error_examples.csv", index=False)
    print(f"\nWrote outputs to {args.out}")


if __name__ == "__main__":
    main()
