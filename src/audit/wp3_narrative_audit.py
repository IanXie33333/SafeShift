"""SafeShift - Work Package 3: Narrative and OIICS feasibility audit.

Answers: "Do we have enough understandable narratives and reliable OIICS
Event/Exposure labels to train (2023) and evaluate (2024) a classifier?"

Reads the OSHA ITA *Case Detail* CSVs (NOT the "ITA Data YYYY" 300A summary
files - those belong to WP1/WP2) and writes everything to --out-dir:

    columns_<year>.csv           draft narrative-data dictionary (every column,
                                 % filled, example value)
    class_counts.csv             two-digit OIICS Event counts per year,
                                 all industries and NAICS 4931 only
    quality_checks.csv           missing/short/duplicate/invalid-code counts
    review_samples.csv           narratives from common classes + short ones,
                                 with blank columns for your manual read-through
    wp3_summary.md               the numbers above in one readable page

Usage (from the repo root):
    uv run python src/audit/wp3_narrative_audit.py --years 2023 2024 2025
    # if auto-detection picks the wrong columns, override them:
    uv run python src/audit/wp3_narrative_audit.py --raw-dir data/raw \
        --text-cols NEW_NAR_BEFORE_INCIDENT NEW_NAR_WHAT_HAPPENED \
        --event-code-col event_code --event-title-col event_title

Column names are detected from the file headers, not hard-coded, because the
case-detail layout should be confirmed against the 2023-2024 Case Detail data
dictionary. ALWAYS check the "Detected columns" printout before trusting results.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

DEFAULT_YEARS = [2023, 2024]
CHUNK = 200_000


# --------------------------------------------------------------------------- #
# File + column discovery
# --------------------------------------------------------------------------- #
def find_raw_dir(arg: str | None) -> Path:
    candidates = [Path(arg)] if arg else [Path("data/raw"), Path("raw")]
    for c in candidates:
        if c.is_dir():
            return c
    raise SystemExit(f"Raw folder not found. Tried: {[str(c) for c in candidates]}")


def find_case_file(raw_dir: Path, year: int) -> Path:
    hits = sorted(raw_dir.rglob(f"*Case Detail*{year}*.csv"))
    if not hits:
        raise SystemExit(f"No Case Detail CSV for {year} in {raw_dir}")
    if len(hits) > 1:
        print(f"  [warn] several files match {year}; using {hits[0].name}")
    return hits[0]


def detect_encoding(path: Path) -> str:
    """Return 'utf-8' if the whole file decodes as UTF-8, else 'cp1252'.

    Some OSHA exports contain Windows-1252 characters (e.g. curly quotes, byte 0x94),
    which make pandas' default UTF-8 reader crash.
    """
    import codecs

    dec = codecs.getincrementaldecoder("utf-8")()
    with open(path, "rb") as f:
        try:
            while block := f.read(16 * 1024 * 1024):
                dec.decode(block)
            dec.decode(b"", final=True)
            return "utf-8"
        except UnicodeDecodeError:
            return "cp1252"


def pick(cols: list[str], must: list[str], avoid: tuple[str, ...] = ()) -> str | None:
    """First column whose lowercase name contains every token in `must`."""
    for c in cols:
        lc = c.lower()
        if all(t in lc for t in must) and not any(a in lc for a in avoid):
            return c
    return None


def detect_columns(cols: list[str], args) -> dict:
    lc = {c: c.lower() for c in cols}
    text_cols = args.text_cols or [
        c for c in cols if re.search(r"(^|_)nar(_|$)", lc[c]) or "incident_description" in lc[c]
    ]
    return {
        "text": text_cols,
        "event_code": args.event_code_col or pick(cols, ["event", "code"]),
        "event_title": args.event_title_col or pick(cols, ["event", "title"]),
        "naics": pick(cols, ["naics"]),
        "case_id": pick(cols, ["case", "number"]),
        "est_id": pick(cols, ["establishment", "id"], avoid=("name", "type")),
        "incident_date": pick(cols, ["date", "incident"]),
    }


# --------------------------------------------------------------------------- #
# Pass 1: profile every column (chunked, low memory) -> draft data dictionary
# --------------------------------------------------------------------------- #
def profile_columns(path: Path, enc: str) -> tuple[pd.DataFrame, int]:
    filled: dict[str, int] = {}
    example: dict[str, str] = {}
    maxlen: dict[str, int] = {}
    n = 0
    for chunk in pd.read_csv(
        path,
        dtype=str,
        chunksize=CHUNK,
        keep_default_na=True,
        encoding=enc,
        encoding_errors="replace",
    ):
        n += len(chunk)
        for c in chunk.columns:
            s = chunk[c].dropna()
            s = s[s.str.strip() != ""]
            filled[c] = filled.get(c, 0) + len(s)
            if c not in example and len(s):
                example[c] = s.iloc[0][:80]
            if len(s):
                maxlen[c] = max(maxlen.get(c, 0), int(s.str.len().max()))
    prof = pd.DataFrame(
        {
            "column": list(filled),
            "pct_filled": [round(100 * filled[c] / max(n, 1), 1) for c in filled],
            "max_chars": [maxlen.get(c, 0) for c in filled],
            "example_value": [example.get(c, "") for c in filled],
            "meaning_from_official_dictionary": "",  # fill in by hand
        }
    )
    return prof, n


# --------------------------------------------------------------------------- #
# Pass 2: load only the columns WP3 needs
# --------------------------------------------------------------------------- #
def load_year(path: Path, cols: dict, year: int, enc: str) -> pd.DataFrame:
    use = [
        c
        for c in [
            *cols["text"],
            cols["event_code"],
            cols["event_title"],
            cols["naics"],
            cols["case_id"],
            cols["est_id"],
            cols["incident_date"],
        ]
        if c
    ]
    df = pd.read_csv(
        path, dtype=str, usecols=list(dict.fromkeys(use)), encoding=enc, encoding_errors="replace"
    )
    df["year"] = year
    if cols["event_title"]:
        df["event_title"] = df[cols["event_title"]]

    text = df[cols["text"][0]].fillna("").str.strip()
    for c in cols["text"][1:]:
        nxt = df[c].fillna("").str.strip()
        sep = ((text != "") & (nxt != "")).map({True: " | ", False: ""})
        text = text + sep + nxt
    df["text"] = text
    df["n_words"] = df["text"].str.split().str.len().fillna(0).astype(int)

    if cols["event_code"]:
        raw = df[cols["event_code"]].fillna("").str.strip().str.replace(r"\.0$", "", regex=True)
        df["event_code_raw"] = raw
        df["code_valid"] = raw.str.fullmatch(r"\d{2,4}")
        df["event_2d"] = raw.where(df["code_valid"]).str[:2]
    else:  # unlabeled file (e.g. the newest year): narratives only
        df["event_code_raw"] = ""
        df["code_valid"] = False
        df["event_2d"] = pd.NA

    if cols["naics"]:
        df["is_4931"] = df[cols["naics"]].fillna("").str.startswith("4931")
    else:
        df["is_4931"] = False
    return df


def quality(df: pd.DataFrame, cols: dict, min_words: int) -> dict:
    n = len(df)
    norm = df["text"].str.lower().str.replace(r"\s+", " ", regex=True)
    key = [c for c in (cols["est_id"], cols["case_id"]) if c]
    dup_cases = int(df.duplicated(subset=key).sum()) if key else None
    has_text = df["text"] != ""
    labeled = bool(cols["event_code"])
    na = "no label column in file"
    return {
        "rows": n,
        "missing_narrative": int((~has_text).sum()),
        f"short_narrative_lt_{min_words}_words": int(
            (has_text & (df["n_words"] < min_words)).sum()
        ),
        "missing_label": int((df["event_code_raw"] == "").sum()) if labeled else na,
        "invalid_label_format": (
            int(((df["event_code_raw"] != "") & ~df["code_valid"]).sum()) if labeled else na
        ),
        "nonclassifiable_99xx": int((df["event_2d"] == "99").sum()) if labeled else na,
        "duplicate_case_keys": dup_cases,
        # same establishment + case number AND identical narrative = likely resubmitted copy
        "duplicate_case_keys_same_text": int(df.duplicated(subset=[*key, "text"]).sum())
        if key
        else None,
        "duplicate_narrative_text": int((norm.duplicated() & has_text).sum()),
        "median_words": float(df.loc[has_text, "n_words"].median()) if has_text.any() else 0,
        "rows_naics_4931": int(df["is_4931"].sum()),
        # which calendar year do the injuries actually happen in? (file name may differ)
        "incident_years_top3": (
            "; ".join(
                f"{y}:{c}"
                for y, c in pd.to_datetime(df[cols["incident_date"]], errors="coerce")
                .dt.year.value_counts()
                .head(3)
                .items()
            )
            if cols["incident_date"]
            else "no date column found"
        ),
    }


def titles_by_year(all_df: pd.DataFrame, title_col: str) -> pd.DataFrame:
    """For each two-digit code, the most common title in each year.

    If the same code has a different title in different years, the code meant
    different things in different files and cannot be compared across years.
    """
    g = (
        all_df.dropna(subset=["event_2d"])
        .groupby(["year", "event_2d", title_col])
        .size()
        .rename("n")
        .reset_index()
        .sort_values("n", ascending=False)
    )
    top = g.drop_duplicates(["year", "event_2d"])
    tot = g.groupby(["year", "event_2d"])["n"].sum().rename("n_total")
    top = top.merge(tot, on=["year", "event_2d"])
    top["top_title_share"] = (top["n"] / top["n_total"]).round(3)
    wide = top.pivot(
        index="event_2d", columns="year", values=[title_col, "n_total", "top_title_share"]
    )
    wide.columns = [f"{a.replace('_pred', '')}_{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    tcols = [c for c in wide.columns if c.startswith("event_title")]
    if len(tcols) >= 2:
        wide["same_title_all_years"] = wide[tcols].nunique(axis=1, dropna=True).eq(1) & wide[
            tcols
        ].notna().all(axis=1)
    return wide.sort_values("event_2d")


def class_counts(all_df: pd.DataFrame, title_col: str | None, min_count: int) -> pd.DataFrame:
    usable = all_df[(all_df["text"] != "") & all_df["event_2d"].notna()]
    out = []
    for scope, sub in [("all_industries", usable), ("naics_4931", usable[usable["is_4931"]])]:
        t = sub.pivot_table(
            index="event_2d", columns="year", values="text", aggfunc="size", fill_value=0
        )
        t.columns = [f"n_{c}" for c in t.columns]
        for c in list(t.columns):
            t[c.replace("n_", "pct_")] = (100 * t[c] / max(t[c].sum(), 1)).round(2)
        t["scope"] = scope
        out.append(t.reset_index())
    res = pd.concat(out, ignore_index=True)

    if title_col:
        ex = usable.groupby("event_2d")[title_col].agg(
            lambda s: "; ".join(s.value_counts().head(3).index)
        )
        res["example_full_titles"] = res["event_2d"].map(ex)
    ncols = [c for c in res.columns if c.startswith("n_")]
    res["below_min_in_any_year"] = (res[ncols] < min_count).any(axis=1)
    return res.sort_values(["scope", ncols[0]], ascending=[True, False])


def review_samples(
    df: pd.DataFrame, title_col: str | None, per_class: int, seed: int
) -> pd.DataFrame:
    base = df[(df["text"] != "") & df["event_2d"].notna()]
    top = base["event_2d"].value_counts().head(8).index
    common = (
        base[base["event_2d"].isin(top)]
        .sample(frac=1, random_state=seed)
        .groupby("event_2d")
        .head(per_class)
        .sort_values("event_2d")
        .assign(sample_type="common_class")
    )
    short = base[base["n_words"] < 5]
    short = short.sample(min(20, len(short)), random_state=seed).assign(sample_type="short_text")
    keep = ["year", "sample_type", "event_2d", "event_code_raw", "text"]
    if title_col:
        keep.insert(4, title_col)
    out = pd.concat([common, short])[keep]
    out["text_supports_label_y_n"] = ""
    out["easy_or_difficult"] = ""
    out["notes"] = ""
    return out


def md_table(df: pd.DataFrame) -> str:
    """Markdown table without needing the optional `tabulate` package."""
    df = df.astype(str)
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join(r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--raw-dir")
    ap.add_argument("--out-dir", default="data/interim/wp3_audit")
    ap.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS)
    ap.add_argument("--text-cols", nargs="+")
    ap.add_argument("--event-code-col")
    ap.add_argument("--event-title-col")
    ap.add_argument("--min-words", type=int, default=5)
    ap.add_argument(
        "--min-count",
        type=int,
        default=100,
        help="flag classes with fewer examples than this in any year",
    )
    ap.add_argument("--per-class", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--skip-profile",
        action="store_true",
        help="skip the slow all-column profile once you have it",
    )
    args = ap.parse_args()

    raw_dir = find_raw_dir(args.raw_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    frames, qrows, cols_by_year = [], [], {}
    for year in args.years:
        path = find_case_file(raw_dir, year)
        print(f"\n=== {year}: {path.name} ===")
        enc = detect_encoding(path)
        print(f"  file encoding: {enc}")
        header = list(pd.read_csv(path, nrows=0, encoding=enc, encoding_errors="replace").columns)
        cols = detect_columns(header, args)
        print("Detected columns (CHECK THESE against the official dictionary):")
        for k, v in cols.items():
            print(f"  {k:12s} -> {v}")
        if not cols["text"]:
            print("All columns in file:", header)
            raise SystemExit("Could not find narrative columns; pass --text-cols explicitly.")
        if not cols["event_code"]:
            print(
                "  NOTE: no OIICS event-code column in this file -> treating it as UNLABELED "
                "(narrative checks only). If that is wrong, pass --event-code-col."
            )
        cols_by_year[year] = cols

        if not args.skip_profile:
            prof, n = profile_columns(path, enc)
            prof.to_csv(out / f"columns_{year}.csv", index=False)
            print(f"  profiled {len(prof)} columns over {n:,} rows")

        df = load_year(path, cols, year, enc)
        q = quality(df, cols, args.min_words)
        q["year"] = year
        q["file_encoding"] = enc
        qrows.append(q)
        frames.append(df)
        print("  " + ", ".join(f"{k}={v}" for k, v in q.items()))

    all_df = pd.concat(frames, ignore_index=True)
    qdf = pd.DataFrame(qrows).set_index("year").astype(object).T
    qdf.to_csv(out / "quality_checks.csv")

    labeled_years = [y for y, c in cols_by_year.items() if c["event_code"]]
    if not labeled_years:
        raise SystemExit("None of the requested years has an OIICS event-code column.")
    has_title = any(c["event_title"] for c in cols_by_year.values())
    title_col = "event_title" if has_title else None

    cc = class_counts(all_df, title_col, args.min_count)
    cc.to_csv(out / "class_counts.csv", index=False)

    if title_col:
        tb = titles_by_year(all_df, title_col)
        tb.to_csv(out / "label_titles_by_year.csv", index=False)
        if "same_title_all_years" in tb:
            changed = tb.loc[~tb["same_title_all_years"], "event_2d"].tolist()
            print(f"Codes whose title differs between years (or missing in a year): {changed}")

    rs = review_samples(
        all_df[all_df["year"] == labeled_years[0]], title_col, args.per_class, args.seed
    )
    rs.to_csv(out / "review_samples.csv", index=False)

    with open(out / "wp3_summary.md", "w") as f:
        f.write("# WP3 narrative & OIICS feasibility - auto summary\n\n")
        f.write("## Columns used\n\n")
        for y, c in cols_by_year.items():
            f.write(f"\n### {y}\n\n")
            for k, v in c.items():
                f.write(f"- **{k}**: {v}\n")
        f.write(
            "\nLabeled years: "
            + ", ".join(map(str, labeled_years))
            + "; unlabeled years: "
            + (", ".join(str(y) for y in cols_by_year if y not in labeled_years) or "none")
            + "\n"
        )
        f.write("\n## Quality checks\n\n" + md_table(qdf.reset_index(names="check")) + "\n")
        f.write("\n## Two-digit OIICS Event classes\n\n" + md_table(cc) + "\n")
        f.write(
            "\n## Still to do by hand\n\n"
            "- Fill `meaning_from_official_dictionary` in columns_<year>.csv\n"
            "- Read review_samples.csv; mark whether the text supports the label\n"
            "- Decide which classes are modelable (enough examples in BOTH years)\n"
        )
    print(f"\nDone. Outputs in {out.resolve()}")


if __name__ == "__main__":
    main()
