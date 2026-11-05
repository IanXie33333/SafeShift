# Count Regression Results

## Objective
Predict next-year warehouse DART injury counts using previous-year DART counts, employee counts, and hours worked.

## Models Evaluated
- Persistence baseline
- Poisson regression
- Negative Binomial regression (fixed alpha = 1.0)
- Negative Binomial regression (estimated alpha = 0.6719)

## Validation Results

| Model | MAE | RMSE | Poisson Deviance |
|---|---:|---:|---:|
| Persistence | **3.4634** | **11.6712** | 12.6502 |
| Poisson | 8.5967 | 23.3562 | 15.2837 |
| Negative Binomial (fixed alpha) | 4.6536 | 16.6969 | 4.1094 |
| Negative Binomial (estimated alpha) | 4.5568 | 16.2206 | **4.0395** |

## Key Findings

**Persistence is the strongest model for absolute prediction accuracy.** It achieves the lowest validation MAE and RMSE.

The estimated-alpha Negative Binomial model outperforms the fixed-alpha version across all three reported validation metrics. Its estimated dispersion parameter is 0.6719.

Poisson regression performs substantially worse on MAE and RMSE. The training data is strongly overdispersed, with a mean target count of 6.66 and variance of 420.71.

The fixed-alpha Negative Binomial model overpredicts average DART counts across all five validation risk groups. The estimated-alpha model also overpredicts the overall validation mean (10.48 predicted versus 8.34 actual).

The largest estimated-alpha Negative Binomial errors involve high-count establishments, with absolute errors exceeding 200 injuries.

## Exposure Quality Audit

The forecasting reference dataset contains no exposure-flag columns and no missing, zero, or negative employee-count or hours-worked values.

An upstream audit identified 88 exposure-flagged warehouse records. None of these flagged establishment-year records appear in the 32,165 forecasting pairs. Consequently, excluding flagged records from the existing forecasting dataset removes no observations and cannot produce a meaningful before-and-after model comparison.

## Recommendation

**Retain persistence as the primary baseline and preferred model when minimizing MAE or RMSE.**

Use the estimated-alpha Negative Binomial model as the strongest regression alternative evaluated, particularly for further investigation of count-distribution fit.

Future improvements could include tuning Poisson regularization, investigating extreme-count prediction errors, and assessing calibration and zero-count probabilities more carefully.

All reported model comparisons use the validation split. The final test split remains untouched.

## Additional Model Diagnostics

### Training Runtime and Convergence

- Persistence: 0 seconds (no training required).
- Poisson regression: 0.0328 seconds.
- Negative Binomial (fixed alpha): 0.0245 seconds; converged successfully.
- Negative Binomial (estimated alpha): converged successfully; training runtime not yet recorded.

### Residual Dispersion

- Persistence residual variance: 136.15.
- Poisson residual variance: 543.90; Pearson dispersion: 26.09.
- Fixed-alpha Negative Binomial residual variance: 273.67; Pearson dispersion: 0.70.

The large Poisson Pearson dispersion indicates substantial overdispersion relative to the Poisson variance assumption.

### Coefficient Interpretation

The fixed-alpha Negative Binomial model uses log-transformed input features. Its coefficients are:

- Previous-year DART count: 0.7454.
- Employee count: 0.6452.
- Hours worked: -0.1942.

Holding other transformed predictors constant, a one-unit increase in a log-transformed predictor multiplies the expected count by the exponential of its coefficient. These associations should not be interpreted as causal effects.

### Zero-Count Diagnostic Caveat

The observed validation zero rate is 42.50%, compared with 40.75% for persistence. The Poisson and fixed-alpha Negative Binomial diagnostics report 0.00% and 10.56%, respectively, using a predicted-mean threshold of 0.5.

These threshold-based values are not model-implied probabilities of observing zero injuries. A proper probabilistic zero-rate comparison would require calculating the zero-count probability from each fitted count distribution.