"""SafeShift - Work Package 3: Narrative and OIICS feasibility audit.

Answers: "Do we have enough understandable narratives and reliable OIICS
Event/Exposure labels to train (2023) and evaluate (2024) a classifier?"

Reads the OSHA ITA *Case Detail* CSVs (NOT the "ITA Data YYYY" 300A summary
files - those belong to WP1/WP2) and writes everything to --out-dir:

    columns_<year>.csv           profile plus definitions for fields used (every column,
                                 % filled, example value)
    class_counts.csv             two-digit OIICS Event counts per year,
                                 all industries and NAICS 4931 only
    quality_checks.csv           missing/short/duplicate/invalid-code counts
    review_samples.csv           narratives from common classes + short ones,
                                 with separate, preserved manual annotations
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
import hashlib
import re
from pathlib import Path

import pandas as pd

DEFAULT_YEARS = [2023, 2024]
CHUNK = 200_000
MAJOR_TITLES = {
    "1": "Violence / person or animal events (version-dependent)",
    "2": "Transportation incidents",
    "3": "Explosions and fires",
    "4": "Falls, slips, and trips",
    "5": "Exposure to harmful substances or environments",
    "6": "Contact events (version-dependent)",
    "7": "Overexertion and bodily reaction",
}
DICTIONARY_URL = "https://www.osha.gov/sites/default/files/case_detail_data_dictionary.pdf"
CURRENT_DICTIONARY_URL = (
    "https://www.osha.gov/sites/default/files/case_detail_data_dictionary_2026.pdf"
)
BLS_CHANGES_URL = "https://www.bls.gov/iif/definitions/oiics-version-3-major-changes.htm"


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
        raise SystemExit(f"Several files match {year}; select a --raw-dir with one: {hits}")
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
    df["source_row"] = df.index
    if cols["event_title"]:
        df["event_title"] = df[cols["event_title"]]

    text = df[cols["text"][0]].fillna("").str.strip()
    for c in cols["text"][1:]:
        nxt = df[c].fillna("").str.strip()
        sep = ((text != "") & (nxt != "")).map({True: " | ", False: ""})
        text = text + sep + nxt
    df["text"] = text
    # Field separators are not narrative words.
    word_text = text.str.replace(" | ", " ", regex=False)
    df["n_words"] = word_text.str.split().str.len().fillna(0).astype(int)

    if cols["event_code"]:
        raw = df[cols["event_code"]].fillna("").str.strip().str.replace(r"\.0$", "", regex=True)
        df["event_code_raw"] = raw
        df["code_valid"] = raw.str.fullmatch(r"\d{2,4}")
        df["event_2d"] = raw.where(df["code_valid"]).str[:2]
    else:  # unlabeled file (e.g. the newest year): narratives only
        df["event_code_raw"] = ""
        df["code_valid"] = False
        df["event_2d"] = pd.NA

    df["event_major"] = df["event_2d"].astype("string").str[0]
    df["event_major_title"] = df["event_major"].map(MAJOR_TITLES)

    if cols["naics"]:
        df["is_4931"] = df[cols["naics"]].fillna("").str.startswith("4931")
    else:
        df["is_4931"] = False
    return df


def quality(df: pd.DataFrame, cols: dict, min_words: int) -> dict:
    n = len(df)
    norm = df["text"].str.lower().str.replace(r"\s+", " ", regex=True)
    # A single establishment can have many legitimate cases. Both keys are required.
    key = [cols["est_id"], cols["case_id"]] if cols["est_id"] and cols["case_id"] else []
    complete = pd.Series(False, index=df.index)
    if key:
        complete = df[key].notna().all(axis=1) & df[key].apply(
            lambda s: s.astype("string").str.strip().ne("").fillna(False)
        ).all(axis=1)
    keyed = df.loc[complete]
    keyed_text = keyed.loc[keyed["text"].ne("")]
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
        "rows_with_complete_case_key": int(complete.sum()) if key else None,
        "rows_with_incomplete_case_key": int((~complete).sum()) if key else None,
        "repeated_case_key_rows": int(keyed.duplicated(key, keep=False).sum()) if key else None,
        "repeated_case_key_extra_copies": int(keyed.duplicated(key).sum()) if key else None,
        "repeated_case_key_same_text_rows": int(
            keyed_text.duplicated([*key, "text"], keep=False).sum()
        ) if key else None,
        "repeated_narrative_rows": int(norm.loc[has_text].duplicated(keep=False).sum()),
        "repeated_narrative_extra_copies": int(norm.loc[has_text].duplicated().sum()),
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


def raw_duplicate_counts(path: Path, enc: str) -> dict:
    """Count identical parsed rows using ALL source columns, across chunks.

    Hashes locate candidates only; actual full-row equality verifies duplicates.
    These are duplicate records, not proof that two injuries are the same event.
    """
    # Match the profiling and narrative readers when source bytes cannot decode.
    kwargs = {"dtype": str, "encoding": enc, "encoding_errors": "replace", "chunksize": CHUNK}
    hashes = [pd.util.hash_pandas_object(c, index=False) for c in pd.read_csv(path, **kwargs)]
    counts = pd.concat(hashes, ignore_index=True).value_counts()
    repeated_hashes = counts.index[counts.gt(1)]
    if not len(repeated_hashes):
        return {"exact_duplicate_raw_rows": 0, "exact_duplicate_raw_extra_copies": 0}
    candidates = []
    for chunk in pd.read_csv(path, **kwargs):
        mask = pd.util.hash_pandas_object(chunk, index=False).isin(repeated_hashes)
        if mask.any():
            candidates.append(chunk.loc[mask])
    candidate_rows = pd.concat(candidates, ignore_index=True)
    return {
        "exact_duplicate_raw_rows": int(candidate_rows.duplicated(keep=False).sum()),
        "exact_duplicate_raw_extra_copies": int(candidate_rows.duplicated().sum()),
    }


def used_dictionary(cols: dict, year: int) -> pd.DataFrame:
    """Short paraphrases of the official definitions, only for detected fields."""
    source = DICTIONARY_URL if year < 2025 else CURRENT_DICTIONARY_URL
    meanings = {
        "event_code": "Code describing how the injury or illness was caused.",
        "event_title": "Description of the assigned Event code.",
        "naics": "Establishment industry classification under NAICS.",
        "est_id": "OSHA identifier for an establishment; not an individual case identifier.",
        "case_id": "Employer-assigned identifier for an injury or illness case.",
        "incident_date": "Date on which the incident occurred.",
    }
    text_meanings = {
        "new_nar_before_incident": "Employee activity immediately before the incident.",
        "new_nar_what_happened": "Account of the event that caused the injury.",
        "new_nar_injury_illness": "Description of the injury or illness.",
        "new_nar_object_substance": "Object or substance that directly harmed the employee.",
        "new_incident_description": "Brief description recorded in the OSHA 300 log.",
    }
    rows = []
    for role, value in cols.items():
        for column in value if isinstance(value, list) else ([value] if value else []):
            meaning = text_meanings.get(column.lower()) if role == "text" else meanings[role]
            rows.append({
                "column": column,
                "audit_role": role,
                "meaning_from_official_dictionary": meaning or "",
                "definition_source_url": source,
                "definition_status": "official paraphrase" if meaning else "needs confirmation",
            })
    return pd.DataFrame(rows)


def warehouse_cohort(all_df: pd.DataFrame) -> pd.DataFrame:
    # No duplicate removal or label harmonization is silently performed in this audit.
    return all_df.loc[
        all_df["year"].isin([2023, 2024]) & all_df["is_4931"]
        & all_df["text"].str.strip().ne("")
        & all_df["event_major"].isin(MAJOR_TITLES)
    ].copy()


def major_tables(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    grid = pd.MultiIndex.from_product(
        [[2023, 2024], list(MAJOR_TITLES)], names=["year", "event_major"]
    )
    counts = base.groupby(["year", "event_major"]).size().reindex(grid, fill_value=0)
    counts = counts.rename("count").reset_index()
    counts["event_major_title"] = counts["event_major"].map(MAJOR_TITLES)
    totals = counts.groupby("year")["count"].transform("sum")
    counts["percentage"] = (100 * counts["count"] / totals.where(totals.ne(0))).round(2)
    counts["percentage"] = counts["percentage"].fillna(0)
    detail = base.loc[base["event_major"].isin(["1", "6"])].copy()
    detail["event_title"] = detail["event_title"].fillna("(missing title)")
    detail = detail.groupby(["year", "event_major", "event_2d", "event_title"]).size()
    detail = detail.rename("count").reset_index()
    detail["possible_person_animal_category"] = detail["event_title"].str.contains(
        r"animal|nonviolent|non-violent|unintentional.*person|other person|intent unknown",
        case=False, regex=True, na=False,
    )
    return counts, detail


def validate_labels(all_df: pd.DataFrame) -> None:
    labeled = all_df["event_2d"].notna()
    assert all_df.loc[labeled, "event_2d"].str.fullmatch(r"[0-9]{2}").all()
    candidate = labeled & all_df["event_2d"].ne("99")
    assert all_df.loc[candidate, "event_major"].isin(MAJOR_TITLES).all(), (
        "Unexpected Event division; inspect codes before building the candidate target."
    )
    assert all_df.loc[all_df["year"].eq(2025), "event_2d"].isna().all(), (
        "2025 now has labels; reassess the documented inference-only assumption."
    )
    assert all_df.loc[all_df["year"].eq(2025), "event_code_raw"].fillna("").eq("").all(), (
        "2025 has nonempty raw Event values; inspect the snapshot before inference."
    )
    for year in [2023, 2024]:
        sub = all_df.loc[all_df["year"].eq(year)]
        if len(sub):
            assert sub["event_2d"].notna().any(), f"No usable Event labels detected for {year}"


def review_samples(
    df: pd.DataFrame, title_col: str | None, per_class: int, seed: int
) -> pd.DataFrame:
    """Usually 30-38 cases: five common broad divisions, plus targeted examples."""
    base = warehouse_cohort(df)
    support = base.groupby(["event_major", "year"]).size().unstack(fill_value=0)
    support = support.reindex(columns=[2023, 2024], fill_value=0)
    common = support.loc[support.gt(0).all(axis=1)].sum(axis=1).nlargest(5).index
    pieces, selected = [], set()

    def take(pool: pd.DataFrame, size: int, kind: str) -> None:
        pool = pool.loc[~pool.index.isin(selected)]
        sample = pool.sample(min(size, len(pool)), random_state=seed).assign(sample_type=kind)
        pieces.append(sample)
        selected.update(sample.index)

    changed = set()
    if title_col:
        by_code = base.groupby("event_2d")
        changed = set(by_code[title_col].nunique().loc[lambda s: s.gt(1)].index)
        changed.update(by_code["year"].nunique().loc[lambda s: s.lt(2)].index)
    for year in [2023, 2024]:
        sub = base.loc[base["year"].eq(year)]
        # Reserve targeted examples before filling the ordinary class sample.
        take(sub.loc[sub["n_words"].lt(5)], 2, "short_text")
        take(sub.loc[sub["event_2d"].isin(changed)], 2, "changed_code")
        for major in common:
            take(sub.loc[sub["event_major"].eq(major)], per_class, "common_major")
    keep = ["year", "source_row", "sample_type", "event_2d", "event_major",
            "event_code_raw", "text"]
    if title_col:
        keep.insert(-1, title_col)
    out = pd.concat(pieces, ignore_index=True)[keep]
    out["review_id"] = [hashlib.sha256(
        f"{r.year}:{r.source_row}:{r.event_code_raw}:{getattr(r, 'event_title', '')}:{r.text}".encode()
    ).hexdigest()[:24] for r in out.itertuples()]
    for col in ["text_supports_label_y_n", "easy_or_difficult", "notes",
                "example_type", "anonymized_example"]:
        out[col] = ""
    return out


def save_review_samples(samples: pd.DataFrame, out: Path) -> pd.DataFrame:
    samples.to_csv(out / "review_samples_generated.csv", index=False)
    manual = out / "manual_review.csv"
    # Exclusive creation preserves annotations, including on repeated or concurrent runs.
    try:
        with manual.open("x", encoding="utf-8", newline="") as f:
            samples.to_csv(f, index=False)
    except FileExistsError:
        print(f"Preserving existing annotations: {manual}")
    return pd.read_csv(manual, dtype=str, keep_default_na=False)


def md_table(df: pd.DataFrame) -> str:
    """Markdown table without needing the optional `tabulate` package."""
    df = df.astype(str).apply(
        lambda s: s.str.replace("|", r"\|", regex=False).str.replace("\n", " ", regex=False)
    )
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join(r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def audit_report(
    qdf: pd.DataFrame, majors: pd.DataFrame, details: pd.DataFrame,
    samples: pd.DataFrame, manual: pd.DataFrame, min_count: int,
) -> str:
    fields = ["review_id", "text_supports_label_y_n", "easy_or_difficult", "notes",
              "example_type", "anonymized_example"]
    if not set(fields).issubset(manual.columns):
        raise ValueError("manual_review.csv is missing required columns; preserve it and inspect.")
    if manual["review_id"].duplicated().any():
        raise ValueError("manual_review.csv has duplicate review_id values.")
    extra = int((~manual["review_id"].isin(samples["review_id"])).sum())
    reviewed = samples[["review_id", "year"]].merge(manual[fields], on="review_id", how="left")
    support = reviewed["text_supports_label_y_n"].fillna("").str.strip().str.lower()
    difficulty = reviewed["easy_or_difficult"].fillna("").str.strip().str.lower()
    done = support.isin(["y", "n"]) & difficulty.isin(["easy", "difficult"])
    done &= reviewed["notes"].fillna("").str.strip().ne("")
    reviewed["completed"] = done
    manual_counts = reviewed.groupby("year").agg(planned=("review_id", "size"),
                                                completed=("completed", "sum")).reset_index()
    example_types = ["easy", "difficult", "insufficient", "label_disagreement"]
    examples = reviewed.loc[done & reviewed["example_type"].isin(example_types)
                            & reviewed["anonymized_example"].fillna("").str.strip().ne("")]
    examples_complete = set(example_types).issubset(examples["example_type"])
    complete = len(samples) >= 30 and bool(done.all()) and extra == 0
    supported = majors.pivot(index="event_major", columns="year", values="count")
    supported_count = int(supported.ge(min_count).all(axis=1).sum())
    flagged = details.loc[details["possible_person_animal_category"]]
    text = (
        "# WP3: Narrative and OIICS feasibility audit\n\n"
        "Owner: Steven. Focused integration patch: Ian.\n\n"
        f"Manual-review evidence: **{'complete' if complete else 'pending'}**. "
        "Final NLP target approval: **pending WP4 decision**.\n\n"
        "## Reproduce\n\n```bash\n"
        "uv run --locked python src/audit/wp3_narrative_audit.py --years 2023 2024 2025 "
        "--report docs/data/wp3_narrative_audit.md\n```\n\n"
        "Run without `--skip-profile` first. Later reruns may add that option. "
        "Audit outputs and raw narrative samples belong in the git-ignored "
        "`data/interim/wp3_audit/` directory.\n\n"
        "## Quality and duplicate counts\n\n" + md_table(qdf.reset_index(names="check"))
        + "\n\nThese figures cover all industries. Raw-row duplicate measures compare all "
        "source columns as parsed by pandas, including verification of hash candidates. "
        "`*_rows` counts every member of a repeated group; `*_extra_copies` counts "
        "occurrences after the first. Case-key measures require both nonmissing, "
        "nonblank establishment ID and case number. Same-key/same-text counts exclude "
        "empty text. Narrative repetition ignores case and repeated whitespace. "
        "Counts identify patterns; they do not establish why records repeat. "
        "No duplicate removal is performed by this audit.\n\n"
        "Low missingness and adequate length establish text availability; manual "
        "review provides the evidence about whether narratives support classification.\n\n"
        "## Broad candidate Event divisions\n\n"
        "Cohort: 2023/2024 NAICS 4931 records with nonempty combined narratives and "
        "valid labels in candidate divisions 1-7. Missing/invalid/nonclassifiable labels "
        "are excluded; their source counts appear in the quality output. Each percentage "
        "uses that year's full candidate cohort as its denominator. "
        "The first-digit target is a candidate, without a cross-year mapping approval.\n\n"
        + md_table(majors) + "\n\n"
        f"**{supported_count} divisions have at least {min_count} cases in both years.** "
        "This is a sample-support check, not proof of label consistency or model quality. "
        f"The four-class support criterion is {'met' if supported_count >= 4 else 'not met'} "
        "at this threshold.\n\n"
        "## Group 1/6 exceptions\n\n"
        "The BLS revision moved certain person/animal events between divisions 1 and 6. "
        "That documents a possible cause of the observed changes, without proving "
        "which version was used to label each local file. "
        "`group_1_6_details.csv` includes every observed code/title in these divisions. "
        "The title-based flags below are inspection prompts, not an approved crosswalk.\n\n"
        + (md_table(flagged) if len(flagged) else "No title-based person/animal flags found. "
           "Inspect the full group 1/6 table before accepting that result.") + "\n\n"
        "## Manual narrative review\n\n" + md_table(manual_counts) + "\n\n"
        f"Completed annotations: {int(done.sum())}/{len(samples)}. "
        f"Saved annotations outside the current generated sample: {extra}. "
        f"All four requested example types supplied: {'yes' if examples_complete else 'no'}.\n\n"
        "Fill `manual_review.csv`: `text_supports_label_y_n` = y/n; "
        "`easy_or_difficult` = easy/difficult; add a brief reason in `notes`. "
        "Use difficult for insufficient text and explain the missing information. "
        "For four examples, also fill `example_type` (easy, difficult, insufficient, "
        "label_disagreement) and a manually anonymized paraphrase in `anonymized_example`. "
        "If no reviewed case supports an example type, record that limitation; do not invent one. "
        "The report includes only those supplied paraphrases, not raw narratives. "
        "Rerun to refresh this summary; existing manual annotations are never overwritten. "
        "If the generated sample changes, reconcile the review IDs explicitly.\n\n"
        + (md_table(examples[["year", "example_type", "anonymized_example"]])
           if len(examples) else "Anonymized examples have not yet been supplied.") + "\n\n"
        "## Modeling decision\n\n"
        "Raw two-digit codes must not be treated as an unchanged cross-year target. "
        "Ian must approve how to handle inconsistent divisions 1/6 before modeling. "
        "These are machine-assigned labels; classifier evaluation measures agreement "
        "with those labels. The supplied 2025 snapshot is inference-only and the script "
        "checks that its Event labels remain absent. Neither this patch nor completion "
        "of the audit freezes the final modeling dataset automatically.\n\n"
        "## Dictionary and sources\n\n"
        "Detected fields and short official-definition paraphrases are saved in "
        "`columns_used_<year>.csv`; unknown narrative fields are marked for confirmation. "
        "Full `columns_<year>.csv` profiles populate those same definitions on a first run.\n\n"
        f"- [OSHA 2023/2024 case-detail dictionary]({DICTIONARY_URL})\n"
        f"- [OSHA current case-detail dictionary]({CURRENT_DICTIONARY_URL})\n"
        f"- [BLS OIICS revision explanation]({BLS_CHANGES_URL})\n"
    )
    return text


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
    ap.add_argument("--per-class", type=int, default=3)
    ap.add_argument("--report", type=Path, help="also write the refreshed Markdown report here")
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
        if not cols["naics"]:
            raise SystemExit(f"No NAICS column detected for {year}; inspect the header.")
        if year in [2023, 2024] and not (cols["event_code"] and cols["event_title"]):
            raise SystemExit(f"Missing Event code/title column for labeled year {year}.")
        if not cols["event_code"]:
            print(
                "  NOTE: no OIICS event-code column in this file -> treating it as UNLABELED "
                "(narrative checks only). If that is wrong, pass --event-code-col."
            )
        cols_by_year[year] = cols

        dictionary = used_dictionary(cols, year)
        dictionary.to_csv(out / f"columns_used_{year}.csv", index=False)

        if not args.skip_profile:
            prof, n = profile_columns(path, enc)
            prof = prof.drop(columns="meaning_from_official_dictionary").merge(
                dictionary.drop(columns="audit_role"), on="column", how="left"
            )
            prof.to_csv(out / f"columns_{year}.csv", index=False)
            print(f"  profiled {len(prof)} columns over {n:,} rows")

        df = load_year(path, cols, year, enc)
        q = quality(df, cols, args.min_words)
        q.update(raw_duplicate_counts(path, enc))
        q["year"] = year
        q["file_encoding"] = enc
        qrows.append(q)
        frames.append(df)
        print("  " + ", ".join(f"{k}={v}" for k, v in q.items()))

    all_df = pd.concat(frames, ignore_index=True)
    validate_labels(all_df)
    qdf = pd.DataFrame(qrows).set_index("year").astype(object).T
    qdf.to_csv(out / "quality_checks.csv")

    labeled_years = [y for y, c in cols_by_year.items() if c["event_code"]]
    if not labeled_years:
        raise SystemExit("None of the requested years has an OIICS event-code column.")
    has_title = any(c["event_title"] for c in cols_by_year.values())
    title_col = "event_title" if has_title else None

    cc = class_counts(all_df, title_col, args.min_count)
    cc.to_csv(out / "class_counts.csv", index=False)

    base = warehouse_cohort(all_df)
    majors, details = major_tables(base)
    majors.to_csv(out / "major_class_counts.csv", index=False)
    details.to_csv(out / "group_1_6_details.csv", index=False)

    if title_col:
        tb = titles_by_year(all_df, title_col)
        tb.to_csv(out / "label_titles_by_year.csv", index=False)
        if "same_title_all_years" in tb:
            changed = tb.loc[~tb["same_title_all_years"], "event_2d"].tolist()
            print(f"Codes whose title differs between years (or missing in a year): {changed}")

    rs = review_samples(
        all_df, title_col, args.per_class, args.seed
    )
    manual = save_review_samples(rs, out)

    # Replace the legacy auto-summary with the current evidence and review status.
    report = audit_report(qdf, majors, details, rs, manual, args.min_count)
    (out / "wp3_summary.md").write_text(report, encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    print(f"\nDone. Outputs in {out.resolve()}")


if __name__ == "__main__":
    main()
