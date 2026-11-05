# Package C: narrative classification (validation results)

Author: Steven. Status: validation results only. Final test (2024) has **not** been scored.

**Question.** How can we reliably build a predictor from injury narrative text to predict the
category of future injuries? This note compares simple, fast baselines on SafeShift modeling
dataset v1 and says what the validation numbers do and do not support.

## Reproduce

```bash
uv run --with scikit-learn --with matplotlib python src/nlp/narrative_models.py \
    --data-dir data/processed/modeling_v1 --seed 42
```

- Reads only `nlp_labeled.csv`, rows with `dataset_split` of `train` or `validation`.
  `final_test` rows are dropped while the file is read and are never vectorised or scored.
- Runtime about 3 minutes on 2 CPU cores. Seed 42. `random_state` is set on every model.
- Committed numbers come from Python 3.13, scikit-learn 1.9.1, pandas 3.0.5, numpy 2.5.3 (see
  `artifacts/metrics/nlp_package_c_run_metadata.json`). A rerun on a second machine (macOS)
  matched the linear SVM exactly (0.9070) and logistic regression to within 0.001 (0.9070
  against 0.9076, 602 errors against 591). The solver ends at slightly different points on
  different numeric libraries even though it converges, so expect small differences, and the
  logistic regression / linear SVM order can flip. scikit-learn and matplotlib are not in
  `pyproject.toml`; `--with` avoids editing `uv.lock`. If the group adopts this package they
  should be added as dependencies.
- Tests: `uv run --with scikit-learn pytest tests/test_narrative_models.py` (skipped
  automatically if scikit-learn is missing).

## Setup

- Target: five machine-assigned categories (v1 label map). Feature: `text` only.
- Train 45,670 rows, validation 11,478 rows. Both come from 2023 and are split by a hash of the
  normalised narrative, so identical narratives never sit on both sides.
- Vectorisers are fitted on the training text only, then applied to validation text.
- Hyperparameters were chosen on validation macro-F1: 31 configurations in total
  (`nlp_package_c_grid.csv`).
- Macro-F1 is the headline metric because 57% of validation rows are overexertion. The
  majority-class baseline has 57.0% accuracy and 0.145 macro-F1.

## Results (validation)

| Model (best config) | Macro-F1 (95% interval) | Weighted F1 | Accuracy | Fit time |
|---|---|---|---|---|
| Logistic regression, word 1-2gram TF-IDF, C=10, balanced | **0.908** (0.897-0.916) | 0.949 | 0.949 | 13 s |
| Linear SVM, word 1-2gram TF-IDF, C=1, balanced | 0.907 (0.897-0.915) | 0.950 | 0.950 | 6 s |
| Linear SVM, character 3-5gram TF-IDF, C=0.5, balanced | 0.896 (0.887-0.905) | 0.940 | 0.940 | 28 s |
| Complement NB, word 1-2gram TF-IDF, alpha=0.1 | 0.824 (0.810-0.839) | 0.908 | 0.910 | 4 s |
| Majority class | 0.145 | 0.414 | 0.570 | under 1 s |

Intervals come from resampling the 11,478 validation rows 300 times. They capture row-level
noise only. They do **not** capture the effect of picking the best of 31 configurations on this
same validation set, or any difference between 2023 and 2024.

Per narrative scoring (one row per distinct normalised narrative, 11,177 of 11,478) changes
nothing material: logistic regression macro-F1 0.907.

Per-class results for the two leading models (logistic regression / linear SVM):

| Class | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| Overexertion / bodily reaction | 6,543 | 0.976 / 0.972 | 0.976 / 0.982 | 0.976 / 0.977 |
| Contact with objects / equipment | 2,959 | 0.933 / 0.933 | 0.921 / 0.922 | 0.927 / 0.927 |
| Falls, slips, trips | 1,381 | 0.911 / 0.919 | 0.917 / 0.915 | 0.914 / 0.917 |
| Transportation | 410 | 0.771 / 0.810 | 0.844 / 0.790 | 0.806 / 0.800 |
| Harmful exposure | 185 | 0.953 / 0.970 | 0.881 / 0.865 | 0.916 / 0.914 |

Figures: `artifacts/figures/nlp_package_c_model_comparison.png`,
`nlp_package_c_confusion_matrices.png`, `nlp_package_c_learning_curve.png`.
Validation predictions for every model (record ID, true label, predicted label, no text) are in
`artifacts/metrics/nlp_package_c_validation_predictions.csv`.

## Where the models go wrong

- The weakest class is transportation (about 0.80 F1). 12% of transportation cases are
  predicted as object/equipment contact (logistic regression). The largest single error pair
  by count is object/equipment contact predicted as overexertion (102 cases), then
  object/equipment contact predicted as transportation (78). See
  `nlp_package_c_top_confusions.csv`.
- Many of these are boundary cases in the label definitions. Examples from
  `nlp_package_c_error_examples_logreg.csv`: a pallet jack or tugger injury where the hand
  strikes a rack is labeled object contact but predicted transportation; a heavy box shifting
  onto an elbow is labeled object contact but predicted overexertion.
- 591 validation errors in total for logistic regression, 99 of them made with confidence of
  0.9 or more. The 60 most confident are in `nlp_package_c_suspected_label_issues.csv`.
  Reading the first dozen by hand (not a full audit): several look like the model is
  right and the machine label is debatable. For example, a worker who tripped while walking
  backwards carrying a tabletop is labeled object contact; one narrative that says "Slip trip
  fall at same level" in its own text is labeled overexertion. Others look like genuine model
  errors. A reviewer should judge these, which is the open manual-review item from WP3.
- Accuracy is lower on long narratives (0.958 under 30 words, 0.920 at 80 or more), but
  macro-F1 has no clear trend by length (`nlp_package_c_by_text_length.csv`).
- Confidence is usable: predictions at 0.97 or higher confidence (7,661 rows) are 99.5% correct,
  and below 0.5 (148 rows) are 49% correct (`nlp_package_c_logreg_confidence_bins.csv`).

## Recommendation for the Nov 4 discussion

1. **Primary: word 1-2gram TF-IDF with logistic regression** (C=10, balanced class weights).
   It ties the linear SVM on every headline metric, and its probabilities support a
   "send low-confidence cases to a person" rule.
2. **Challenger: word 1-2gram TF-IDF with a linear SVM.** Statistically indistinguishable on
   validation, faster to fit, no probabilities.
3. Do not spend more time on character n-grams or Complement NB here: character n-grams were
   lower and about five times slower to fit than the word SVM; Complement NB was clearly worse, mostly on transportation
   recall (0.46).
4. The ranking between the top two is not decided by this data (it flipped on a second machine). If the group wants one winner
   it should break the tie on something other than validation macro-F1.

## What the numbers do not show

- **This is not a temporal test.** Validation is a random-by-narrative split of 2023. The final
  test is 2024. Same-year validation is expected to be optimistic for a classifier that will
  label future years, because wording, establishments and, per WP3, upstream coding rules can
  shift between years. How much lower 2024 will be is unknown until it is scored once.
- **Labels are machine-assigned.** Scores measure agreement with the BLS autocoder's output, not
  with expert coders. A high score means we can reproduce that labeler, not that the
  categories are correct.
- **Still improving with data.** Macro-F1 on a linear SVM rises from 0.775 (5% of training) to
  0.890 (50%) to 0.907 (100%) and has not flattened (`nlp_package_c_learning_curve.csv`).
- **Rare classes are small.** Harmful exposure has 185 validation cases and transportation 410,
  so their per-class numbers move by a few points between resamples.
- **2025 is closed-set.** Out-of-scope injuries in 2025 will still be forced into one of five
  classes.

## Research answer: reliable text prediction of future injury categories

What this package measured, and what the references suggest should come next:

- *Measured here:* simple linear models on TF-IDF reach about 0.91 macro-F1 against the
  machine labels on same-year validation, and confidence scores separate reliable from
  unreliable predictions.
- *Suggested practice, not yet tested here:* evaluate on a later year than training (the
  temporal persistence of text classifiers is an active research topic, see Sources); report
  per-class results and an uncertainty interval rather than accuracy alone; keep a human
  review path for low-confidence cases; re-score every new year and watch for drift.
- *Context:* BLS has published research on automated injury coding, including deep neural
  network coders (see Sources). A more complex model than TF-IDF + linear is a possible next
  challenger, but only the final-test and review results can say whether it is worth it.

## Next steps

1. One-time final-test scoring of the selected model after the group chooses, refitting on
   train + validation as the dataset README specifies.
2. Manually review the suspected label issues and a random error sample to estimate how much
   of the remaining error is label noise.
3. Temporal sanity check on 2025 predictions (class mix by year) once a model is selected.

## Sources

- BLS, Automated coding of injury and illness narratives: <https://www.bls.gov/iif/automated-coding.htm>
- BLS, Deep neural networks for worker injury autocoding: <https://www.bls.gov/iif/automated-coding/deep-neural-networks.pdf>
- Building for Tomorrow: Assessing the Temporal Persistence of Text Classifiers: <https://arxiv.org/abs/2205.05435>
