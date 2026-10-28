# WP3: Narrative and OIICS feasibility audit

Owner: Steven. Focused integration patch: Ian.

Status: revised audit code is ready for a local run. Corrected dataset counts and
manual-review evidence must be generated from the project's actual CSV files.
The final harmonized NLP target remains a WP4 decision.

## Reproduce and refresh this report

From the repository root, run a complete first pass:

```bash
uv run --locked python src/audit/wp3_narrative_audit.py \
    --years 2023 2024 2025 \
    --report docs/data/wp3_narrative_audit.md
```

This replaces this report with the actual run's quality checks, corrected duplicate
counts, broad candidate-class counts, group 1/6 flags, and manual-review status.
No newly computed dataset statistics are claimed before that run.

The first run generates `data/interim/wp3_audit/manual_review.csv`. Fill the
annotations there, then rerun the same command with `--skip-profile` to refresh
the report. Existing annotations and the older `review_samples.csv` are preserved.
Do not use the old sample as evidence that the new two-year warehouse review is complete.

## Focused revisions

- Repeated case keys require both establishment ID and case number, with nonmissing,
  nonblank values. Repeated-group rows and extra copies are separate measures.
- Full-row duplicate checks use all raw source columns and cover chunk boundaries.
  Hash candidates are verified by actual row equality.
- Candidate one-digit Event counts use nonempty, labeled NAICS 4931 narratives in
  2023 and 2024. Each year's own candidate cohort is the percentage denominator.
  Nonclassifiable labels are reported separately and excluded from this candidate.
- A group 1/6 table lists original year, division, two-digit code, title, count,
  and a title-based inspection flag. It performs no remapping.
- The new sample normally contains 30-38 cases, using five common candidate
  divisions in both years, short texts, and changed-code examples. Sampling does
  not remove duplicate cases or approve the final label scheme.
- Used-field definitions are populated from official OSHA definitions, paraphrased
  with source links. Unrecognized text fields require confirmation.
- Basic checks validate candidate divisions, label formats, and the expected lack
  of usable Event labels in the supplied 2025 snapshot.

## Manual review

For every sampled narrative, fill:

- `text_supports_label_y_n`: `y` or `n`, based on the original assigned label.
- `easy_or_difficult`: `easy` or `difficult`.
- `notes`: a brief explanation, including missing information or label disagreement.

For four representative cases, also supply a manually anonymized paraphrase in
`anonymized_example` and one of these values in `example_type`:
`easy`, `difficult`, `insufficient`, `label_disagreement`.
Mark an insufficient narrative as difficult and explain why in the notes.

The regenerated report stays explicit about incomplete review work. It includes
only manually supplied anonymized examples, rather than publishing raw sample text.
Keep all narrative CSVs in the git-ignored output directory.

## Sources and interpretation

- [OSHA 2023/2024 case-detail dictionary](https://www.osha.gov/sites/default/files/case_detail_data_dictionary.pdf)
- [OSHA current case-detail dictionary](https://www.osha.gov/sites/default/files/case_detail_data_dictionary_2026.pdf)
- [BLS OIICS revision explanation](https://www.bls.gov/iif/definitions/oiics-version-3-major-changes.htm)

The BLS revision documents movement of certain person/animal events between
divisions 1 and 6. This establishes a reason to inspect those categories, without
establishing the OIICS version actually used for each local file. The first-digit
target is still a candidate and must not be approved on counts alone.
