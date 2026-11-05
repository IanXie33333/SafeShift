# Modeling review fixes after PRs 6, 7, and 8

The submitted result files are historical experiment records. Keep every file in
`artifacts/count_regression`, `artifacts/lightgbm_forecast`, and the original
`artifacts/metrics/nlp_package_c_*` and `artifacts/figures/nlp_package_c_*` unchanged.
The old READMEs describe those old runs. This document describes the revised code.
New runs may produce different scores and write to new directories; the fixes do
not revise, replace, or relabel any submitted scores or figures.

## Package A

Run from the repository root after `uv sync --extra dev --locked`:

```bash
uv run --locked python -m src.forecasting.exposure_flag_audit
uv run --locked python -m src.forecasting.count_regression
```

Inputs default to `data/processed/modeling_v1`. Outputs go to
`artifacts/count_regression_review`. The primary cohort remains 21,785 train and
5,019 validation rows. The separate sensitivity cohort removes manifest exposure
review flags from both sets: 21,647 train and 4,990 validation rows. Every learned
model is independently refitted for that cohort.

The original raw-feature Poisson and both negative-binomial specifications remain
available. A supplemental log-feature Poisson searches regularization values
0, 0.01, 0.1, and 1 on the 2022-to-2023 holdout within training, selects by MAE,
and refits on all permitted training rows. Both NB models export their coefficients,
dispersion, calibration, and largest errors. Poisson deviance retains the shared
1e-10 prediction floor, explicitly recorded as an adjustment affecting persistence.
Zero probabilities use Poisson or fitted NB2 formulas; persistence has no fitted
count distribution. Poisson deviance evaluates mean predictions and does not
validate the NB2 distribution or its uncertainty estimates.

## Package B

```bash
uv run --locked --script src/forecasting/lightgbm_forecast.py
```

The existing script-specific lock remains unchanged. Its objective remains Poisson;
early stopping and inner-holdout selection now use MAE, matching the agreed primary
metric. The original deviance-selected model's submitted outputs stay untouched.
New outputs go to `artifacts/lightgbm_forecast_review`.

Package B requires Package A's separate corrected primary and refitted sensitivity
predictions. It rejects missing runs, differing IDs/outcomes, or training-cohort
sizes that do not match its own cohort. It also includes the supplemental log-feature
Poisson. Size groups now use left-closed intervals: 50 belongs to 50-249, 250 to
250-999, and 1,000 to 1,000+. NB zero probabilities use the supplied fitted dispersion.

## Package C

```bash
uv run --locked python src/nlp/narrative_models.py --seed 42
```

Use the merged project lock, including pandas below version 3, rather than unpinned
`--with` installs. The 31 candidate configurations are unchanged. New outputs go to
`artifacts/nlp_package_c_review/metrics` and `figures`, with the actual environment
and input hash recorded. The committed historical metadata, including its pandas
3 environment, stays unchanged. Small numerical differences between new and old
runs must be reported rather than edited away.

Development loading checks IDs, nonempty text, expected cohort sizes, and exact
normalized narrative separation. A paired LR-minus-SVM macro-F1 interval supplements
the individual intervals. It describes row-sampling uncertainty conditional on the
chosen configurations; it excludes selection and temporal-shift uncertainty and
does not establish formal equivalence. Probabilities support review prioritization
against provided machine labels, not independently verified expert correctness.
This task classifies an existing narrative after an incident; forecasting categories
before incidents remains a separate feasibility question.

## Preservation and evaluation

`scripts/verify_submitted_results.py` snapshots and verifies all original result
files, including binary figures. Use an external manifest path. Output guards reject
the original result directories. The source datasets and original dependency locks
are unchanged. No final-test fitting or scoring is added. Select models using the
corrected development results before any reserved final evaluation.
