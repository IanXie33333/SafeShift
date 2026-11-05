"""Regression checks for cohort symmetry, output protection, and evaluation fixes."""

import importlib.util
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.forecasting import count_regression as count
from src.forecasting import lightgbm_forecast as boosted
from src.forecasting.review_utils import (
    FEATURES,
    RUNS,
    TARGET,
    cohort,
    implied_zero_probability,
    protect_original_output,
    read_package_a_run,
    run_file,
)
from src.nlp import narrative_models as narrative


class ModelingReviewTests(unittest.TestCase):
    def test_output_protection_rejects_original_and_overlapping_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "artifacts" / "count_regression"
            for target in [original, original / "nested", original.parent]:
                with self.assertRaises(ValueError):
                    protect_original_output(target, original)
            self.assertEqual(protect_original_output(original.with_name("review"), original),
                             original.with_name("review").resolve())
        with self.assertRaises(ValueError):
            narrative.protect_output(narrative.ROOT / "artifacts")

    def test_sensitivity_removes_flagged_rows_from_both_partitions(self):
        train = pd.DataFrame({"pair_id": ["a", "b"], "exposure_review_flag": [True, False]})
        validation = pd.DataFrame({"pair_id": ["c", "d"],
                                   "exposure_review_flag": [False, True]})
        clean_train, clean_validation = cohort(train, validation, RUNS[1])
        self.assertEqual(clean_train.pair_id.tolist(), ["b"])
        self.assertEqual(clean_validation.pair_id.tolist(), ["c"])
        self.assertEqual(len(cohort(train, validation, "primary")[0]), 2)
        self.assertEqual(len(train), 2)

    def test_shared_comparison_rejects_wrong_training_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            run = RUNS[1]
            validation = pd.DataFrame({"pair_id": pd.Series(["a"], dtype="string"), TARGET: [2]})
            pd.DataFrame({"pair_id": ["a"], "actual_count": [2], "run": [run],
                          "persistence_pred": [1]}).to_csv(
                directory / run_file("validation_predictions", run), index=False)
            path = directory / run_file("model_metrics", run)
            pd.DataFrame({"model": ["Persistence"], "train_rows": [10],
                          "validation_rows": [1]}).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "refitted"):
                read_package_a_run(directory, run, validation, train_rows=9)
            aligned, _ = read_package_a_run(directory, run, validation, train_rows=10)
            self.assertEqual(aligned.pair_id.tolist(), ["a"])
            with self.assertRaises(FileNotFoundError):
                read_package_a_run(directory, "primary", validation, train_rows=10)

    def test_size_boundaries_match_the_labels(self):
        frame = pd.DataFrame({"employee_count_t": [49, 50, 249, 250, 999, 1000],
                              TARGET: [0, 0, 0, 0, 0, 0]})
        result = boosted.sliced_errors(frame, {"m": np.zeros(6)},
                                       "employee_count_t", *boosted.SIZE_BINS)
        self.assertEqual(dict(zip(result.bin, result.n, strict=True)),
                         {"<50": 1, "50-249": 2, "250-999": 2, "1000+": 1})

    def test_zero_probabilities_use_the_fitted_distribution(self):
        p = np.array([0.0, 1.0, 2.0])
        np.testing.assert_allclose(implied_zero_probability(p, "poisson"), np.exp(-p))
        np.testing.assert_allclose(implied_zero_probability(p, "negative_binomial", 1), 1 / (1+p))
        self.assertTrue(np.isnan(implied_zero_probability(p, "point")).all())
        with self.assertRaises(ValueError):
            implied_zero_probability(p, "negative_binomial", -1)

    def test_log_poisson_tuning_does_not_receive_validation(self):
        frame = pd.DataFrame({"feature_year": [2020, 2021, 2022],
                              TARGET: [1.0, 1.0, 1.0],
                              **{f: [1.0, 2.0, 3.0] for f in FEATURES}})
        fits, predicted = [], []

        class Model:
            def __init__(self, alpha):
                self.alpha = alpha

            def fit(self, x, y):
                fits.append(x.index.tolist())
                return self

            def predict(self, x):
                predicted.append(x.index.tolist())
                return np.full(len(x), 1.0 + self.alpha)

        with patch.object(count, "poisson_pipeline", side_effect=lambda a, **kw: Model(a)):
            alpha, table = count.tune_log_poisson(frame)
        self.assertEqual(alpha, 0.0)
        self.assertEqual(len(table), 4)
        self.assertTrue(all(indices == [0, 1] for indices in fits))
        self.assertTrue(all(indices == [2] for indices in predicted))

    def test_lightgbm_uses_mae_for_early_stopping_and_selection(self):
        frame = pd.DataFrame({"feature_year": [2020, 2021, 2022], TARGET: [1.0, 2.0, 3.0],
                              **{f: [1.0, 2.0, 3.0] for f in FEATURES}})
        calls = []

        class Model:
            def __init__(self, **kwargs):
                self.best_iteration_ = 5
                calls.append(kwargs)

            def fit(self, x, y, **kwargs):
                if kwargs:
                    if kwargs["eval_metric"] != "l1":
                        raise AssertionError("Early stopping must monitor MAE")
                    if x.index.tolist() != [0, 1]:
                        raise AssertionError("Inner fitting must use earlier training years")
                return self

            def predict(self, x):
                return np.full(len(x), 2.0)

        fake = types.SimpleNamespace(LGBMRegressor=Model,
                                     early_stopping=lambda *a, **kw: kw)
        with patch.dict("sys.modules", {"lightgbm": fake}):
            _, best, tuning, _ = boosted.tune_and_fit(frame)
        self.assertEqual(len(tuning), 24)
        self.assertEqual(best["n_estimators"], 5)
        self.assertTrue(all(c["objective"] == "poisson" and c["metric"] == "l1" for c in calls))

    def test_narrative_group_leakage_is_rejected(self):
        data = pd.DataFrame({"text": ["Same TEXT", "same   text"],
                             "dataset_split": ["train", "validation"]})
        with self.assertRaisesRegex(ValueError, "cross"):
            narrative.validate_narrative_groups(data)

    def test_paired_f1_interval_is_zero_for_identical_predictions(self):
        labels = narrative.LABELS * 3
        result = narrative.paired_macro_f1(labels, labels, labels, 20, 42)
        self.assertEqual(result["macro_f1_difference"], 0)
        self.assertEqual(result["ci95_low"], 0)
        self.assertEqual(result["ci95_high"], 0)

    def test_artifact_inventory_detects_content_changes(self):
        script = Path(__file__).resolve().parents[1] / "scripts/verify_submitted_results.py"
        spec = importlib.util.spec_from_file_location("verify_results", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "artifacts/count_regression"
            folder.mkdir(parents=True)
            file = folder / "model_metrics.csv"
            file.write_text("original")
            before = module.inventory(root)
            file.write_text("different")
            self.assertNotEqual(before, module.inventory(root))

    def test_count_exports_include_estimated_nb_and_consumer_metadata(self):
        frame = pd.DataFrame({"pair_id": [f"pair-{i}" for i in range(5)],
                              TARGET: [0, 1, 2, 3, 4],
                              **{f: [1, 2, 3, 4, 5] for f in FEATURES}})
        columns = ["persistence_pred", "poisson_pred", "poisson_log_pred",
                   "negative_binomial_pred", "negative_binomial_estimated_pred"]
        names = ["Persistence", "Poisson", "Poisson (log features)", "Negative Binomial",
                 "Negative Binomial (Estimated Alpha)"]
        predictions = {c: np.arange(1, 6, dtype=float) for c in columns}
        details = {}
        for i, (name, column) in enumerate(zip(names, columns, strict=True)):
            details[name] = {"column": column, "training_seconds": 0.0,
                             "family": "point" if i == 0 else
                                       "negative_binomial" if i > 2 else "poisson",
                             "alpha": 0.5 if i > 2 else None}
        coefficients = pd.DataFrame({"model": names, "coefficient": [1] * 5})
        tuning = pd.DataFrame({"alpha": [1.0]})
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(count, "fit_models", return_value=(
                    predictions, details, coefficients, tuning)):
                count.evaluate_run(frame, frame, RUNS[1], Path(directory))
            calibration = pd.read_csv(Path(directory) / run_file("calibration", RUNS[1]))
            self.assertIn(names[-1], calibration.model.tolist())
            _, metrics = read_package_a_run(Path(directory), RUNS[1], frame, 5)
            self.assertEqual(metrics.loc[names[-1], "alpha"], 0.5)


if __name__ == "__main__":
    unittest.main()
