"""Tests for the Package C narrative classification script (small synthetic data only)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("sklearn")

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "nlp" / "narrative_models.py"
spec = importlib.util.spec_from_file_location("narrative_models", MODULE_PATH)
nm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nm)


def _toy_frame() -> pd.DataFrame:
    rows = []
    phrases = {
        "overexertion_bodily_reaction": "lifting heavy box strained back",
        "object_equipment_contact": "hand caught in conveyor roller",
        "falls_slips_trips": "slipped on wet floor and fell",
        "transportation": "forklift collided with truck",
        "harmful_exposure": "inhaled chemical fumes",
    }
    for i, (label, text) in enumerate(phrases.items()):
        for split in ("train", "validation", "final_test"):
            for k in range(3):
                rows.append(
                    {
                        "record_id": f"x:{i}{split[:2]}{k}",
                        "text": f"{text} case {k}",
                        "label": label,
                        "dataset_split": split,
                    }
                )
    return pd.DataFrame(rows)


def test_load_dev_drops_final_test(tmp_path):
    _toy_frame().to_csv(tmp_path / "nlp_labeled.csv", index=False)
    dev = nm.load_dev(tmp_path)
    assert set(dev["dataset_split"]) == {"train", "validation"}
    assert "final_test" not in nm.DEV_SPLITS


def test_load_dev_rejects_unknown_label(tmp_path):
    df = _toy_frame()
    df.loc[0, "label"] = "mystery"
    df.to_csv(tmp_path / "nlp_labeled.csv", index=False)
    with pytest.raises(ValueError):
        nm.load_dev(tmp_path)


def test_score_perfect_and_majority():
    y = ["a"] * 3
    labels_y = nm.LABELS[:1] * 3
    s = nm.score(labels_y, labels_y)
    assert s["accuracy"] == 1.0
    # one class correct out of five labels -> macro-F1 = 1/5
    assert s["macro_f1"] == pytest.approx(0.2)
    assert len(y) == 3


def test_grid_runs_and_is_reproducible(tmp_path):
    df = nm.load_dev(_write(tmp_path))
    train = df[df["dataset_split"] == "train"].reset_index(drop=True)
    val = df[df["dataset_split"] == "validation"].reset_index(drop=True)
    g1, _, _ = nm.run_grid(train, val, seed=1)
    g2, _, _ = nm.run_grid(train, val, seed=1)
    cols = ["family", "config", "macro_f1", "accuracy"]
    pd.testing.assert_frame_equal(g1[cols], g2[cols])
    best = nm.best_per_family(g1)
    assert best.loc[best["family"] == "logreg", "macro_f1"].iloc[0] == 1.0


def test_unique_narrative_scores_dedupes_text():
    val = pd.DataFrame(
        {
            "text": ["Same text", "same   TEXT", "other"],
            "label": [nm.LABELS[0], nm.LABELS[0], nm.LABELS[1]],
        }
    )
    import numpy as np

    out = nm.unique_narrative_scores(val, {"m": np.array([nm.LABELS[0]] * 3)})
    assert out.loc[0, "unique_narratives"] == 2


def _write(tmp_path: Path) -> Path:
    _toy_frame().to_csv(tmp_path / "nlp_labeled.csv", index=False)
    return tmp_path
