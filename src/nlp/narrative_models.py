"""Package C: narrative classification baselines for the SafeShift modeling dataset v1.

Trains on the ``train`` partition and scores on the ``validation`` partition of
``nlp_labeled.csv``. The ``final_test`` rows are dropped immediately after loading and are
never vectorised, predicted or scored. Hyperparameters are chosen on validation macro-F1.

Run (from the repository root)::

    uv run --locked python src/nlp/narrative_models.py \
        --data-dir data/processed/modeling_v1 --seed 42

New outputs go to ``artifacts/nlp_package_c_review``; submitted artifacts remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd

LABELS = [
    "overexertion_bodily_reaction",
    "object_equipment_contact",
    "falls_slips_trips",
    "transportation",
    "harmful_exposure",
]
DEV_SPLITS = ("train", "validation")  # final_test is deliberately absent
PREFIX = "nlp_package_c"
ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- data
def load_dev(data_dir: Path) -> pd.DataFrame:
    """Load train + validation rows only.

    The file is read in chunks and final-test rows are dropped chunk by chunk, so their text
    is filtered before any vectorization, prediction, or scoring.
    """
    chunks = pd.read_csv(
        data_dir / "nlp_labeled.csv", dtype=str, keep_default_na=False, chunksize=20_000
    )
    df = pd.concat([c[c["dataset_split"].isin(DEV_SPLITS)] for c in chunks], ignore_index=True)
    if set(df["dataset_split"]) != set(DEV_SPLITS):
        raise ValueError("Both development partitions are required")
    if df["record_id"].duplicated().any():
        raise ValueError("Narrative record IDs must be unique")
    if not df["text"].str.strip().ne("").all():
        raise ValueError("Development narratives must be nonempty")
    unknown = set(df["label"]) - set(LABELS)
    if unknown:
        raise ValueError(f"unexpected labels: {unknown}")
    return df


def validate_narrative_groups(dev):
    key = dev["text"].str.lower().str.split().str.join(" ")
    groups = pd.DataFrame({"key": key, "split": dev["dataset_split"]})
    if groups.groupby("key")["split"].nunique().gt(1).any():
        raise ValueError("Identical normalized narratives cross development partitions")


def protect_output(out_dir):
    output = out_dir.resolve()
    for folder in ["count_regression", "lightgbm_forecast", "metrics", "figures"]:
        original = (ROOT / "artifacts" / folder).resolve()
        if output == original or original in output.parents or output in original.parents:
            raise ValueError("Submitted artifacts are protected; choose a new --out-dir")
    return out_dir


def paired_macro_f1(y_true, left, right, n_boot, seed):
    """Paired row bootstrap of macro-F1 difference; no equivalence or selection correction."""
    encode = {name: i for i, name in enumerate(LABELS)}
    y = np.array([encode[v] for v in y_true])
    a = np.array([encode[v] for v in left])
    b = np.array([encode[v] for v in right])

    def f1(actual, predicted):
        matrix = np.bincount(actual * len(LABELS) + predicted,
                             minlength=len(LABELS) ** 2).reshape(len(LABELS), len(LABELS))
        denominator = matrix.sum(0) + matrix.sum(1)
        return np.divide(2 * np.diag(matrix), denominator,
                         out=np.zeros(len(LABELS)), where=denominator > 0).mean()

    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(n_boot):
        indices = rng.integers(0, len(y), len(y))
        differences.append(f1(y[indices], a[indices]) - f1(y[indices], b[indices]))
    lo, hi = np.percentile(differences, [2.5, 97.5])
    return {"left": "logreg", "right": "linear_svm", "macro_f1_difference": f1(y, a) - f1(y, b),
            "ci95_low": float(lo), "ci95_high": float(hi), "resamples": n_boot,
            "method": "paired row bootstrap; conditional on chosen configurations"}


def word_count(texts: pd.Series) -> pd.Series:
    return texts.str.split().str.len()


# ------------------------------------------------------------------------ metrics
def score(y_true, y_pred) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, f1_score

    return {
        "macro_f1": f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0),
        "weighted_f1": f1_score(y_true, y_pred, labels=LABELS, average="weighted", zero_division=0),
        "accuracy": accuracy_score(y_true, y_pred),
    }


def per_class_table(y_true, y_pred, model: str) -> pd.DataFrame:
    from sklearn.metrics import precision_recall_fscore_support

    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=LABELS, zero_division=0)
    return pd.DataFrame(
        {"model": model, "label": LABELS, "precision": p, "recall": r, "f1": f, "support": s}
    )


def bootstrap_macro_f1(y_true, y_pred, n_boot: int, seed: int) -> tuple[float, float]:
    """95% percentile interval for macro-F1 from resampling validation rows."""
    from sklearn.metrics import f1_score

    rng = np.random.default_rng(seed)
    yt, yp = np.asarray(y_true), np.asarray(y_pred)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(yt), len(yt))
        vals.append(f1_score(yt[idx], yp[idx], labels=LABELS, average="macro", zero_division=0))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


# ------------------------------------------------------------------------- models
def run_grid(train: pd.DataFrame, val: pd.DataFrame, seed: int):
    """Fit every configuration on train, score on validation.

    Vectorizers are fitted on training text only, then applied to validation text.
    Returns (grid_df, fitted) where fitted maps config id -> (estimator, X_val, preds).
    """
    from sklearn.dummy import DummyClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import ComplementNB
    from sklearn.svm import LinearSVC

    y_tr, y_va = train["label"].to_numpy(), val["label"].to_numpy()
    rows, fitted = [], {}

    def record(family, config, est, Xva, fit_s, vec_name, vec_s):
        t0 = time.perf_counter()
        pred = est.predict(Xva)
        pred_s = time.perf_counter() - t0
        row = {
            "family": family,
            "config": config,
            "vectorizer": vec_name,
            **score(y_va, pred),
            "fit_seconds": round(fit_s + vec_s, 2),
            "predict_seconds": round(pred_s, 3),
        }
        rows.append(row)
        fitted[(family, config)] = (est, Xva, pred)
        print(
            f"  {family:<18} {config:<40} macroF1={row['macro_f1']:.4f} "
            f"acc={row['accuracy']:.4f} ({row['fit_seconds']}s)",
            flush=True,
        )

    # 1. majority-class baseline (needs no text features)
    t0 = time.perf_counter()
    dummy = DummyClassifier(strategy="most_frequent").fit(np.zeros((len(y_tr), 1)), y_tr)
    record(
        "majority",
        "most_frequent",
        dummy,
        np.zeros((len(y_va), 1)),
        time.perf_counter() - t0,
        "none",
        0.0,
    )

    vec_specs = {
        "word_1gram_min2": {"analyzer": "word", "ngram_range": (1, 1), "min_df": 2},
        "word_1-2gram_min3": {"analyzer": "word", "ngram_range": (1, 2), "min_df": 3},
        "char_wb_3-5_min5": {"analyzer": "char_wb", "ngram_range": (3, 5), "min_df": 5},
    }
    mats = {}
    for name, spec in vec_specs.items():
        t0 = time.perf_counter()
        vec = TfidfVectorizer(lowercase=True, sublinear_tf=True, dtype=np.float32, **spec)
        Xtr = vec.fit_transform(train["text"])  # fitted on training text only
        Xva = vec.transform(val["text"])
        mats[name] = (Xtr, Xva, time.perf_counter() - t0, len(vec.vocabulary_))
        print(f"vectorizer {name}: {len(vec.vocabulary_):,} features", flush=True)

    for vname in ("word_1gram_min2", "word_1-2gram_min3"):
        Xtr, Xva, vsec, _ = mats[vname]
        for C in (1.0, 10.0):
            for cw in (None, "balanced"):
                t0 = time.perf_counter()
                est = LogisticRegression(
                    C=C, class_weight=cw, max_iter=300, solver="lbfgs", random_state=seed
                ).fit(Xtr, y_tr)
                record(
                    "logreg",
                    f"{vname}|C={C}|cw={cw}",
                    est,
                    Xva,
                    time.perf_counter() - t0,
                    vname,
                    vsec,
                )
        for C in (0.1, 0.5, 1.0):
            for cw in (None, "balanced"):
                t0 = time.perf_counter()
                est = LinearSVC(C=C, class_weight=cw, random_state=seed).fit(Xtr, y_tr)
                record(
                    "linear_svm",
                    f"{vname}|C={C}|cw={cw}",
                    est,
                    Xva,
                    time.perf_counter() - t0,
                    vname,
                    vsec,
                )
        for alpha in (0.1, 0.3, 1.0):
            t0 = time.perf_counter()
            est = ComplementNB(alpha=alpha).fit(Xtr, y_tr)
            record(
                "complement_nb",
                f"{vname}|alpha={alpha}",
                est,
                Xva,
                time.perf_counter() - t0,
                vname,
                vsec,
            )

    Xtr, Xva, vsec, _ = mats["char_wb_3-5_min5"]
    for C in (0.1, 0.5):
        for cw in (None, "balanced"):
            t0 = time.perf_counter()
            est = LinearSVC(C=C, class_weight=cw, random_state=seed).fit(Xtr, y_tr)
            record(
                "linear_svm_char",
                f"char_wb_3-5_min5|C={C}|cw={cw}",
                est,
                Xva,
                time.perf_counter() - t0,
                "char_wb_3-5_min5",
                vsec,
            )

    return pd.DataFrame(rows), fitted, mats


def best_per_family(grid: pd.DataFrame) -> pd.DataFrame:
    idx = grid.groupby("family")["macro_f1"].idxmax()
    return grid.loc[idx].sort_values("macro_f1", ascending=False).reset_index(drop=True)


# -------------------------------------------------------------------------- plots
BLUE_SEQ = ["#eef4fc", "#c5dcf6", "#8fbbec", "#5a97de", "#2a78d6", "#1a56a0", "#0f3a70"]
INK, INK2 = "#0b0b0b", "#52514e"


def plot_confusions(models: dict[str, np.ndarray], y_true, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from sklearn.metrics import confusion_matrix

    cmap = LinearSegmentedColormap.from_list("seq_blue", BLUE_SEQ)
    short = [
        name.replace("_", " ").replace("bodily reaction", "bodily\nreaction") for name in LABELS
    ]
    n = len(models)
    fig, axes = plt.subplots(1, n, figsize=(5.2 * n, 5.2), dpi=200, squeeze=False)
    for ax, (name, pred) in zip(axes[0], models.items(), strict=False):
        cm = confusion_matrix(y_true, pred, labels=LABELS)
        norm = cm / cm.sum(axis=1, keepdims=True)  # row-normalised: recall per true class
        ax.imshow(norm, cmap=cmap, vmin=0, vmax=1)
        for i in range(len(LABELS)):
            for j in range(len(LABELS)):
                ax.text(
                    j,
                    i,
                    f"{norm[i, j]:.0%}\n({cm[i, j]:,})",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if norm[i, j] > 0.55 else INK,
                )
        ax.set_xticks(range(len(LABELS)), short, fontsize=7, color=INK2, rotation=30, ha="right")
        ax.set_yticks(range(len(LABELS)), short, fontsize=7, color=INK2)
        ax.set_xlabel("Predicted", fontsize=8, color=INK2)
        ax.set_ylabel("True (machine-assigned label)", fontsize=8, color=INK2)
        ax.set_title(name, fontsize=10, color=INK, loc="left")
        for s in ax.spines.values():
            s.set_visible(False)
    fig.suptitle(
        "Validation confusion matrices (row-normalised; counts in brackets)",
        fontsize=11,
        color=INK,
        x=0.01,
        ha="left",
    )
    fig.tight_layout()
    fig.savefig(out, facecolor="white")
    plt.close(fig)


def plot_model_bars(best: pd.DataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = best.sort_values("macro_f1")
    fig, ax = plt.subplots(figsize=(7, 3.4), dpi=200)
    ax.barh(d["family"], d["macro_f1"], color="#2a78d6", height=0.55)
    for y, v in enumerate(d["macro_f1"]):
        ax.text(v + 0.008, y, f"{v:.3f}", va="center", fontsize=8, color=INK)
    ax.set_xlim(0, max(1.0, d["macro_f1"].max() + 0.1))
    ax.set_xlabel("Validation macro-F1 (best configuration per family)", fontsize=8, color=INK2)
    ax.tick_params(labelsize=8, colors=INK2)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_title("Model comparison on validation", fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(out, facecolor="white")
    plt.close(fig)


def plot_length_curve(tbl: pd.DataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 3.4), dpi=200)
    ax.plot(tbl["train_fraction"], tbl["macro_f1"], color="#2a78d6", lw=2, marker="o", ms=5)
    ax.set_xscale("log")
    ax.set_xticks(tbl["train_fraction"], [f"{f:.0%}" for f in tbl["train_fraction"]])
    ax.set_xlabel("Share of training data used", fontsize=8, color=INK2)
    ax.set_ylabel("Validation macro-F1", fontsize=8, color=INK2)
    ax.tick_params(labelsize=8, colors=INK2)
    ax.grid(axis="y", color="#e5e4e0", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title("Learning curve (word 1-2gram linear SVM)", fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(out, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------- analyses
def length_breakdown(val: pd.DataFrame, pred: np.ndarray) -> pd.DataFrame:
    wc = word_count(val["text"])
    bins = pd.cut(
        wc,
        [0, 29, 39, 49, 59, 79, 10_000],
        labels=["<30", "30-39", "40-49", "50-59", "60-79", "80+"],
    )
    out = []
    for b in bins.cat.categories:
        m = (bins == b).to_numpy()
        if m.sum() == 0:
            continue
        s = score(val["label"].to_numpy()[m], pred[m])
        out.append({"words": b, "n": int(m.sum()), **s})
    return pd.DataFrame(out)


def unique_narrative_scores(
    val: pd.DataFrame, pred_by_model: dict[str, np.ndarray]
) -> pd.DataFrame:
    """Score once per distinct normalised narrative (guards against repeated templates)."""
    key = val["text"].str.lower().str.split().str.join(" ")
    first = ~key.duplicated()
    rows = []
    for name, pred in pred_by_model.items():
        s = score(val["label"].to_numpy()[first.to_numpy()], pred[first.to_numpy()])
        rows.append({"model": name, "unique_narratives": int(first.sum()), **s})
    return pd.DataFrame(rows)


def confusion_pairs(val: pd.DataFrame, pred: np.ndarray, top: int = 10) -> pd.DataFrame:
    bad = pd.DataFrame({"true": val["label"].to_numpy(), "pred": pred})
    bad = bad[bad["true"] != bad["pred"]]
    t = bad.groupby(["true", "pred"]).size().reset_index(name="errors")
    totals = val["label"].value_counts()
    t["share_of_true_class"] = t.apply(lambda r: r["errors"] / totals[r["true"]], axis=1)
    return t.sort_values("errors", ascending=False).head(top)


def error_examples(val, pred, proba, per_pair: int, seed: int) -> pd.DataFrame:
    """Sample misclassified rows from the largest confusion pairs (text kept for review)."""
    df = val.assign(pred=pred, confidence=proba.max(axis=1))
    df = df[df["label"] != df["pred"]]
    pairs = df.groupby(["label", "pred"]).size().sort_values(ascending=False).head(6).index
    parts = []
    for t, p in pairs:
        sub = df[(df["label"] == t) & (df["pred"] == p)]
        parts.append(sub.sample(min(per_pair, len(sub)), random_state=seed))
    out = pd.concat(parts)
    out["text"] = out["text"].str.slice(0, 400)
    return out[["record_id", "label", "pred", "confidence", "text"]].rename(
        columns={"label": "machine_label", "pred": "model_prediction"}
    )


def suspected_label_issues(val, pred, proba, threshold: float, n: int) -> pd.DataFrame:
    """Rows where the model disagrees with the label AND is highly confident."""
    df = val.assign(pred=pred, confidence=proba.max(axis=1))
    df = df[(df["label"] != df["pred"]) & (df["confidence"] >= threshold)]
    df = df.sort_values("confidence", ascending=False).head(n).copy()
    df["text"] = df["text"].str.slice(0, 400)
    return df[["record_id", "label", "pred", "confidence", "text"]].rename(
        columns={"label": "machine_label", "pred": "model_prediction"}
    )


def calibration_table(y_true, proba, classes) -> pd.DataFrame:
    conf = proba.max(axis=1)
    pred = np.asarray(classes)[proba.argmax(axis=1)]
    hit = pred == np.asarray(y_true)
    bins = pd.cut(conf, [0, 0.5, 0.7, 0.9, 0.97, 1.0001], right=False)
    t = pd.DataFrame({"bin": bins, "conf": conf, "hit": hit})
    return (
        t.groupby("bin", observed=True)
        .agg(n=("hit", "size"), mean_confidence=("conf", "mean"), accuracy=("hit", "mean"))
        .reset_index()
        .astype({"bin": str})
    )


def learning_curve(train, val, best_cfg: dict, seed: int, fractions) -> pd.DataFrame:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.svm import LinearSVC

    rows = []
    for f in fractions:
        sub = train.sample(frac=f, random_state=seed) if f < 1 else train
        vec = TfidfVectorizer(
            lowercase=True, sublinear_tf=True, dtype=np.float32, **best_cfg["vec"]
        )
        Xtr = vec.fit_transform(sub["text"])
        est = LinearSVC(C=best_cfg["C"], class_weight=best_cfg["cw"], random_state=seed).fit(
            Xtr, sub["label"]
        )
        pred = est.predict(vec.transform(val["text"]))
        rows.append({"train_fraction": f, "n_train": len(sub), **score(val["label"], pred)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- main
def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data/processed/modeling_v1")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "artifacts/nlp_package_c_review")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-boot", type=int, default=300)
    ap.add_argument("--sample", type=int, default=0, help="debug: use only N train rows")
    args = ap.parse_args(argv)
    args.out_dir = protect_output(args.out_dir)
    if args.n_boot < 1:
        raise ValueError("--n-boot must be positive")

    import sklearn

    t_start = time.perf_counter()
    metrics_dir, fig_dir = args.out_dir / "metrics", args.out_dir / "figures"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    dev = load_dev(args.data_dir)
    validate_narrative_groups(dev)
    train = dev[dev["dataset_split"] == "train"].reset_index(drop=True)
    val = dev[dev["dataset_split"] == "validation"].reset_index(drop=True)
    if (len(train), len(val)) != (45670, 11478):
        raise ValueError("Expected frozen v1 NLP partitions: 45,670 train and 11,478 validation")
    if args.sample:
        train = train.sample(args.sample, random_state=args.seed).reset_index(drop=True)
    print(f"train={len(train):,} validation={len(val):,} (final_test rows dropped at load)")

    grid, fitted, _mats = run_grid(train, val, args.seed)
    grid.sort_values("macro_f1", ascending=False).to_csv(
        metrics_dir / f"{PREFIX}_grid.csv", index=False
    )
    best = best_per_family(grid)

    y_va = val["label"].to_numpy()
    preds, rows_pc, rows_pred = {}, [], []
    for _, r in best.iterrows():
        est, Xva, pred = fitted[(r["family"], r["config"])]
        preds[r["family"]] = pred
        rows_pc.append(per_class_table(y_va, pred, r["family"]))
        rows_pred.append(
            pd.DataFrame(
                {
                    "record_id": val["record_id"],
                    "true_label": y_va,
                    "predicted_label": pred,
                    "model": r["family"],
                }
            )
        )
    pd.concat(rows_pred).to_csv(metrics_dir / f"{PREFIX}_validation_predictions.csv", index=False)
    pd.concat(rows_pc).to_csv(metrics_dir / f"{PREFIX}_per_class.csv", index=False)

    ci = {
        f: bootstrap_macro_f1(y_va, p, args.n_boot, args.seed)
        for f, p in preds.items()
        if f != "majority"
    }
    best["macro_f1_ci95_low"] = best["family"].map(lambda f: ci.get(f, (np.nan, np.nan))[0])
    best["macro_f1_ci95_high"] = best["family"].map(lambda f: ci.get(f, (np.nan, np.nan))[1])
    best.to_csv(metrics_dir / f"{PREFIX}_comparison.csv", index=False)
    pd.DataFrame([paired_macro_f1(y_va, preds["logreg"], preds["linear_svm"],
                                  args.n_boot, args.seed)]).to_csv(
        metrics_dir / f"{PREFIX}_paired_comparison.csv", index=False)
    print(
        "\nBest per family:\n",
        best[["family", "config", "macro_f1", "weighted_f1", "accuracy"]].to_string(index=False),
    )

    unique_narrative_scores(val, preds).to_csv(
        metrics_dir / f"{PREFIX}_unique_narrative_scores.csv", index=False
    )

    # Diagnostics model: fixed to logistic regression (it gives real probabilities). The top
    # two families have similar validation scores; their order can flip between environments.
    sel = best[best["family"] == "logreg"].iloc[0]
    sel_pred = preds[sel["family"]]
    est, Xva, _ = fitted[(sel["family"], sel["config"])]
    print(f"\nSelected for diagnostics: {sel['family']} :: {sel['config']}")

    # Confidence scores: LR probabilities, else softmax of SVM decision values (not calibrated).
    if hasattr(est, "predict_proba"):
        est.predict_proba(Xva)
    else:
        softmax(est.decision_function(Xva))
    classes = est.classes_
    assert list(classes) == sorted(LABELS) or set(classes) == set(LABELS)

    # Probabilities are assessed against provided machine labels, not expert correctness.
    lr_rows = best[best["family"] == "logreg"]
    if len(lr_rows):
        lr_est, lr_X, lr_pred = fitted[("logreg", lr_rows.iloc[0]["config"])]
        lr_proba = lr_est.predict_proba(lr_X)
        calibration_table(y_va, lr_proba, lr_est.classes_).to_csv(
            metrics_dir / f"{PREFIX}_logreg_confidence_bins.csv", index=False
        )
        suspected_label_issues(val, lr_pred, lr_proba, 0.9, 60).to_csv(
            metrics_dir / f"{PREFIX}_suspected_label_issues.csv", index=False
        )
        error_examples(val, lr_pred, lr_proba, 5, args.seed).to_csv(
            metrics_dir / f"{PREFIX}_error_examples_logreg.csv", index=False
        )
        n_conf = int(((lr_pred != y_va) & (lr_proba.max(axis=1) >= 0.9)).sum())
        print(f"LR errors at confidence >= 0.9: {n_conf} of {(lr_pred != y_va).sum()}")

    confusion_pairs(val, sel_pred).to_csv(metrics_dir / f"{PREFIX}_top_confusions.csv", index=False)
    length_breakdown(val, sel_pred).to_csv(
        metrics_dir / f"{PREFIX}_by_text_length.csv", index=False
    )

    # Learning curve for the selected model if it is a word/char linear SVM; else for best SVM.
    svm_row = best[best["family"].isin(["linear_svm", "linear_svm_char"])].iloc[0]
    parts = svm_row["config"].split("|")
    vec_name = parts[0]
    vec_cfg = {
        "word_1gram_min2": {"analyzer": "word", "ngram_range": (1, 1), "min_df": 2},
        "word_1-2gram_min3": {"analyzer": "word", "ngram_range": (1, 2), "min_df": 3},
        "char_wb_3-5_min5": {"analyzer": "char_wb", "ngram_range": (3, 5), "min_df": 5},
    }[vec_name]
    cw = None if parts[2].split("=")[1] == "None" else parts[2].split("=")[1]
    lc = learning_curve(
        train,
        val,
        {"vec": vec_cfg, "C": float(parts[1].split("=")[1]), "cw": cw},
        args.seed,
        (0.05, 0.1, 0.25, 0.5, 1.0),
    )
    lc.to_csv(metrics_dir / f"{PREFIX}_learning_curve.csv", index=False)
    plot_length_curve(lc, fig_dir / f"{PREFIX}_learning_curve.png")

    shown = {f: preds[f] for f in ("majority", "logreg", "linear_svm") if f in preds}
    plot_confusions(shown, y_va, fig_dir / f"{PREFIX}_confusion_matrices.png")
    plot_model_bars(best, fig_dir / f"{PREFIX}_model_comparison.png")

    meta = {
        "seed": args.seed,
        "data_dir": str(args.data_dir),
        "n_train": len(train),
        "n_validation": len(val),
        "final_test_used": False,
        "selected_family": sel["family"],
        "selected_config": sel["config"],
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "source_sha256": hashlib.sha256((args.data_dir / "nlp_labeled.csv").read_bytes()).hexdigest(),
        "labels": "provided machine-assigned categories; not expert ground truth",
        "confidence_note": "Scores support review prioritization; probabilities are not validated expert correctness",
        "bootstrap_note": "Row resampling excludes tuning and temporal-shift uncertainty",
        "total_seconds": round(time.perf_counter() - t_start, 1),
    }
    (metrics_dir / f"{PREFIX}_run_metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"\nDone in {meta['total_seconds']}s. Outputs in {args.out_dir}")


if __name__ == "__main__":
    main()
