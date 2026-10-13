# WP3: Narrative and OIICS feasibility audit

Owner: Steven. Reviewer: Ian. Status: automated audit complete; manual read-through of
sample narratives not yet done (see "Still open").

**Question:** Do we have enough understandable narratives and reliable OIICS Event or
Exposure labels to train (2023) and evaluate (2024) a classifier, then classify 2025?

**Short answer:** The narratives are usable. The labels are not usable as planned: the
two-digit Event codes do not mean the same thing in the 2023 and 2024 files, so training on
2023 and testing on 2024 with the raw codes would not be a valid test. The 2025 file has no
labels at all. Scope needs a decision (WP4); options are at the end.

## Reproduce

```bash
uv run python src/audit/wp3_narrative_audit.py --years 2023 2024 2025 --skip-profile
```

Reads `data/raw/**/Case Detail Data <year>.csv`. Writes to `data/interim/wp3_audit/`, which
is git-ignored (it includes a file of narrative samples). Column names are detected from the
file headers and printed; check them against the OSHA dictionary.

## Files and columns

| | 2023 | 2024 | 2025 |
|---|---|---|---|
| Rows (cases) | 890,934 | 688,649 | 697,201 |
| File encoding | cp1252 | cp1252 | utf-8 |
| Injuries dated in the file's own year | 890,372 | 687,706 | 696,724 |
| Label columns (`*_pred`) present | yes | yes | **no** |
| Text column names | `NEW_NAR_*`, `NEW_INCIDENT_DESCRIPTION` | same | `New_nar_*`, `New_incident_description` |

- Text fields combined for the audit: what happened, before the incident, injury or
  illness, object or substance, and the short incident description (the last is a separate
  summary of at most 263 characters, not a copy of the others).
- Label used: `event_code_pred`, reduced to its first two digits.
- Per OSHA's online case-detail data dictionary, the `*_pred` codes are machine-assigned
  (BLS SOII autocoder) at the two-digit level, not human-coded.
- Column capitalisation and encoding differ between years, so loaders must normalise both.

## Narrative quality

| | 2023 | 2024 | 2025 |
|---|---|---|---|
| Missing narrative | 2 | 6 | 14 |
| Fewer than 5 words | 454 | 253 | 266 |
| Median words | 44 | 45 | 46 |
| Identical narrative text repeated | 40,843 (4.6%) | 16,444 (2.4%) | 8,247 (1.2%) |
| Warehousing (NAICS 4931) cases | 58,618 | 56,578 | 50,037 |

The text itself is not a problem. Almost nothing is missing and a typical narrative is about
45 words.

Repeated establishment + case-number pairs: 64,748 (2023), 0 (2024), 36,675 (2025). Only 5,617
(2023) and 134 (2025) of those also have identical narrative text, so most are reused case
numbers on different injuries, not duplicate rows. Do not treat case number as a unique key.

## Labels

- Missing label: 85,324 cases in 2023 (9.6%) and 40,206 in 2024 (5.8%). These cannot be used
  for training or testing.
- No invalid code formats and no "nonclassifiable" codes in either year.
- **Codes change meaning between years.** Within a single year every code has exactly one title,
  but across 2023 and 2024 (33 codes appear in at least one year):

| Group | Codes | 2023 cases | 2024 cases |
|---|---|---|---|
| Same title both years | 21, 26, 27, 51, 52, 53, 54 | 37,098 (4.6%) | 28,569 (4.4%) |
| Title reworded, concept looks the same (judgment) | 11, 55, 56, 71, 72, 73 | 362,079 (44.9%) | 319,350 (49.2%) |
| Same code, different meaning | 12, 22, 23, 24, 25, 31, 32, 41, 43, 62, 63, 64, 65, 66 | 295,346 (36.7%) | 293,968 (45.3%) |
| Code exists in one year only | 13, 42, 44, 67 (2023); 57, 61 (2024) | 111,087 (13.8%) | 6,556 (1.0%) |

Percentages are of labeled cases (805,610 in 2023, 648,443 in 2024). About half of labeled
cases in each year carry a code whose meaning differs from the other year, or does not exist
there. Examples: code 42 is "Falls on same level" in 2023 (99,837 cases) and absent in 2024;
code 43 is "Falls to lower level" in 2023 and "Slip, trip, stumble or fall on same level" in
2024; code 66 grows from 11,125 to 112,726 cases; code 62 falls from 139,082 to 8,527.
Full table: `label_titles_by_year.csv` in the audit output folder.

**Cause not established.** OSHA's online dictionary does not explain this. The Drive
`dictionaries` folder has separate case-detail dictionaries for 2023-2024 and 2025-2026, which
should be read for a version note before anyone assumes a cause.

## Warehousing (NAICS 4931) class sizes

Largest classes by share of labeled warehousing cases:

- 2023: 71 overexertion involving outside sources 22,990 (40.0%); 62 8,243 (14.3%); 73 6,341
  (11.0%); 42 4,758 (8.3%); 63 3,777 (6.6%); 72 3,117 (5.4%).
- 2024: 71 overexertion while moving or manipulating external objects 23,855 (44.0%);
  66 8,051 (14.8%); 73 5,521 (10.2%); 43 5,457 (10.1%); 64 4,833 (8.9%); 72 2,366 (4.4%).

One class is over 40% in both years, so accuracy would be misleading; macro-F1 is the right
headline metric. Many warehousing classes have under 100 cases in a year (see
`class_counts.csv`, column `below_min_in_any_year`).

## Recommendation

1. Do not train on 2023 two-digit codes and test on 2024 two-digit codes as they stand.
2. Choose a label scheme (WP4 decision). Candidates:
   - Map both years to a common coarser label set by title, then check the mapping by hand.
     Likely the best option; the 14 changed codes and the one-year-only codes need explicit
     handling.
   - Keep only the 7 identically titled codes. Too small to be a useful classifier (about 4.5%
     of cases).
   - Train and evaluate inside one labeled year (random or by-establishment split) and drop
     the 2023-to-2024 temporal test.
3. Treat 2025 as unlabeled: it can be classified but not scored.
4. Remember the labels are machine-assigned, so a classifier here learns to reproduce another
   model's output. Reports should say so.

## Still open

- Manual read of `review_samples.csv` to judge whether narratives support their labels, and
  anonymised easy and hard example cases: not done.
- "Meaning" column of the draft data dictionary (`columns_<year>.csv`): not filled in.
- Reason for the code change between 2023 and 2024.
- Whether the 2025 file will later gain label columns.
