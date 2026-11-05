# Package B: LightGBM Poisson Forecasting Results

## Objective
Predict next-year establishment DART counts (`dart_count_t1`) with a boosted-tree model (LightGBM, Poisson objective) using the same three permitted predictors and validation rows as Package A (`dart_count_t`, `employee_count_t`, `hours_worked_t`). Then compare it with Package A on a shared leaderboard.

## How to run
From the repository root, with SafeShift modeling v1 extracted to `data/processed/modeling_v1/`:

```bash
brew install libomp            # macOS only: OpenMP runtime LightGBM needs
uv run --locked --script src/forecasting/lightgbm_forecast.py \
  --package-a-dir artifacts/count_regression   # Package A's validation_predictions.csv + model_metrics.csv
```

- Dependencies are declared inline in the script (PEP 723) and pinned in `src/forecasting/lightgbm_forecast.py.lock` (LightGBM 4.7.0). The project `pyproject.toml` is untouched, so this PR can't conflict with Package A's dependency changes.
- Seed 42, `deterministic=True`, single thread. Two consecutive runs produce byte-identical predictions.
- Runtime is about 25 s CPU for the whole script (both runs, 24-config grid each). The final LightGBM fit takes 0.14 s.
- All settings and chosen hyperparameters are in `run_settings.json`.

## Method
- **Tuning never touches validation.** Train rows with `feature_year == 2022` (2022→2023 pairs) serve as an inner temporal holdout, and earlier training years are inner-train. A 24-config grid (`num_leaves` {7, 15, 31} × `learning_rate` {0.03, 0.1} × `min_child_samples` {20, 100} × `reg_lambda` {0, 1}) is searched with early stopping on Poisson loss and ranked by inner Poisson deviance (`tuning_*.csv`). The best config is refit on all 21,785 training rows.
- **Chosen model:** `num_leaves=15, learning_rate=0.03, min_child_samples=100, reg_lambda=0, n_estimators=341`.
- **Package A models** are scored from Package A's own validation predictions, joined on `pair_id`. The script asserts the rows and targets match exactly. Persistence is checked against `dart_count_t` and reproduces A's MAE of 3.4634 and RMSE of 11.6712.
- Poisson deviance clips predictions at 1e-10, the same as Package A. This is why persistence (which predicts 0 for 41% of rows) has an inflated deviance.
- Predictions are continuous expected counts.

## Validation leaderboard (2023→2024, 5,019 pairs)

| Model | MAE | RMSE | Poisson deviance | Mean pred (actual 8.34) | Fit time (s) |
|---|---:|---:|---:|---:|---:|
| Persistence | **3.463** | 11.671 | 12.650 | 8.60 | 0 |
| **LightGBM Poisson** | 3.597 | **11.602** | **3.508** | 8.66 | 0.14 |
| Negative Binomial (estimated alpha) | 4.557 | 16.221 | 4.039 | 10.48 | 0.09 |
| Negative Binomial (fixed alpha) | 4.654 | 16.697 | 4.109 | 10.60 | 0.02 |
| Poisson regression | 8.597 | 23.356 | 15.284 | 7.07 | 0.03 |

**Paired bootstrap (1,000 resamples of validation rows, LightGBM minus the other model; negative means LightGBM is better):**

| vs | MAE diff [95% CI] | Deviance diff [95% CI] |
|---|---|---|
| Persistence | +0.13 [−0.00, +0.26] | −9.14 [−10.14, −8.26] |
| NB (estimated alpha) | −0.96 [−1.27, −0.71] | −0.53 [−0.80, −0.29] |
| NB (fixed alpha) | −1.06 [−1.38, −0.79] | −0.60 [−0.89, −0.33] |
| Poisson regression | −5.00 [−5.53, −4.53] | −11.78 [−12.95, −10.64] |

## Sensitivity: exposure-flagged rows excluded
`forecasting_row_manifest.csv` flags **138 training and 29 validation rows** (`exposure_review_flag`; 8 of them are also possible field swaps). LightGBM was re-tuned and refit without them, and all models were scored on the 4,990 remaining validation rows. Package A's models are scored on the same rows but were *not* refit (only A can do that).

| Model | MAE | RMSE | Poisson deviance |
|---|---:|---:|---:|
| Persistence | **3.475** | 11.704 | 12.635 |
| LightGBM Poisson | 3.601 | **11.643** | **3.498** |
| NB (estimated alpha) | 4.525 | 16.113 | 3.963 |
| NB (fixed alpha) | 4.616 | 16.544 | 4.021 |
| Poisson regression | 8.624 | 23.422 | 15.337 |

The ranking is unchanged, and no metric moves by more than 0.04 MAE. The flagged rows don't drive the results.

Note: Package A's exposure audit reports "0 flagged records used in forecasting". That audit checked 88 upstream warehouse records, not the 167 dev rows flagged in this release's manifest, so the team should reconcile the two.

## Diagnostics

**Calibration** (`calibration.png`, `calibration.csv`). LightGBM's total predicted/observed ratio is 1.04, versus 1.26 for both NB models. The top prediction decile is close (63.9 predicted vs. 64.9 observed), while NB(est) overshoots it (83.0 vs. 65.4). Like NB, LightGBM over-predicts the lowest deciles by about 0.15–0.25 cases, because a Poisson mean can't sit at 0 for establishments that will report 0.

**Errors by establishment size** (`error_by_size.png`):

| Employees | n | LightGBM MAE | Persistence | NB (est) | LightGBM bias | NB (est) bias |
|---|---:|---:|---:|---:|---:|---:|
| <50 | 2,188 | 0.76 | 0.66 | 0.77 | +0.22 | +0.24 |
| 50–249 | 1,932 | 2.20 | 2.10 | 2.03 | +0.73 | +0.37 |
| 250–999 | 686 | 8.78 | 8.45 | 8.83 | +0.69 | +1.31 |
| 1000+ | 213 | 28.71 | 28.52 | 52.60 | −3.32 | **+40.37** |

The NB models' MAE gap comes almost entirely from large establishments, where their log-linear exposure terms blow up. LightGBM matches persistence there.

**Errors by observed count** (`error_by_count.png`). LightGBM beats persistence for observed counts of 1–2, 3–9, and 10–49, and roughly ties at 50+. It loses at **0** (MAE 1.13 vs. 0.59, n = 2,133). That bin alone explains why persistence wins on overall MAE: persistence predicts exactly 0 for repeat-zero establishments, while a Poisson mean is always positive.

**Feature importance** (`feature_importance.png`). `dart_count_t` dominates (95% of gain, mean |SHAP| 0.85 on log μ), then `employee_count_t` (4%, 0.50), then `hours_worked_t` (1%, 0.09). Hours add little once employees are known.

**Error examples** (`error_examples.csv`). The ten largest LightGBM errors are all surges at large sites, for example 158 → 431 cases (1,681 employees) and 9 → 191 (660 employees). Every model misses these, because nothing in three lagged predictors signals a jump. Typical errors are ±1 case at small sites.

## Recommendation
**LightGBM Poisson is the strongest learned forecaster and the best expected-count model.** It has the lowest Poisson deviance (3.51 vs. 4.04 for the best NB, significant by bootstrap), the lowest RMSE, the best overall calibration, and it beats both NB models on MAE by about 1 case (significant). The extra complexity is small: it fits in 0.14 s and is deterministic.

**On the agreed primary metric (MAE), persistence still wins by 0.13 cases**, and that difference is borderline (95% CI just touches 0). The whole gap comes from true-zero establishments.

Suggested selection:
- If the team needs one point forecast scored by MAE, keep **persistence** as the primary model.
- Use **LightGBM Poisson** as the expected-count/risk model, and as the one to carry forward. It is the only learned model that is competitive with persistence on MAE while also being properly calibrated.

## Limitations and open concerns
- Only one validation year (2023→2024). The bootstrap resamples rows, not years, so year-to-year variation is not captured.
- Three predictors only. Surges at large sites are unpredictable with this feature set.
- MAE rewards median-like forecasts, while a Poisson objective targets the mean. An L1/quantile or hurdle objective could close the zero-bin gap. That wasn't tried here (out of scope for Package B).
- Persistence deviance depends on the 1e-10 clip, so compare deviance among the continuous models only.
- The sensitivity run did not refit Package A's models.
- The exposure-flag discrepancy with Package A's audit (above) is unresolved.
- The final test split was not loaded or used.
