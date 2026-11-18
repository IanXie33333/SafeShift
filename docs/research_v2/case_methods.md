# Descriptive warehouse case profiles: 2023–2024

This implementation answers the case-report part of the revised SafeShift
question. It describes incident mechanisms, SOC major occupational groups, and
reported outcomes; it does not predict future injuries or labels. The case files
and annual establishment summaries are separate reporting populations.

## Inputs and provenance

Run `scripts/export_case_fields.py` against the original case CSVs to produce the
compact `safeshift_case_fields.zip`, or use the standalone exporter supplied by
the project lead. It filters six-digit NAICS codes beginning 4931, preserves source
IDs and record positions, and includes actual occupation/outcome/day fields. It
does not export establishment names, addresses, narratives, or free-text jobs.
The raw source filenames, SHA-256 hashes, encodings, all-industry row counts, and
warehouse row counts are recorded in its manifest. Raw files remain read-only.

The old narrow NLP exports do not contain the required occupation/outcome/day
values and are deliberately rejected as inputs to this implementation. Expected
historical warehouse counts are 58,618 in 2023 and 56,578 in 2024; actual counts
are checked against the compact export's source manifest rather than forced.

## Inclusion and identity

Parse 2023 incident dates as month/day/four-digit year and 2024 dates as day plus
English month abbreviation plus four-digit year. Primary analysis includes dates
aligned with the source year. Invalid dates and mismatched years are quarantined
and reconciled, not relabeled into another file. The earlier source version has
13 mismatches in 2023 and 9 in 2024, leaving 58,605 and 56,569 aligned reports.

A report's identity is source year plus original source ID, with a documented
source-row fallback for an absent ID. Repeated source IDs or source coordinates
are rejected for investigation. Repeated establishment/case-number pairs are
counted in the audit and retained; they do not establish duplicate reports.
Missing narrative, mechanism, occupation, or day values do not remove otherwise
eligible reports from frequency counts.

## Mechanism and occupation definitions

`reference/nlp_label_map.csv` is the existing year-specific crosswalk. Join by
source year and event code and validate the observed title. Unexpected codes or
titles create a mapping-issue audit and stop production export. The five existing
broad mechanisms are retained alongside distinct Other and Unknown groups.
Historical `candidate_rows` are not reused as current analysis counts.

The official SOC 2018 major-group reference supplies occupational labels.
Syntactically recognized codes with a valid major prefix are grouped at that level;
the implementation does not independently certify every detailed SOC assignment.
Missing, unassigned, uncodable, malformed, and review-status-conflicting occupations
remain visible as Unknown, with reasons retained in the audit. The older-release
SOC probability value 5 is an OSHA reassignment indicator, not a rejected probability.
Ordinary confidence values and review status are profiled without arbitrary drops.

These are occupations among reports, not occupational incidence or worker risk:
occupation-specific employee/hour denominators are unavailable. Establishment
hours and employees repeated on case rows are never summed for case rates.

## Outcomes, days, and scenarios

Source outcome 1 is death, 2 days away, 3 restriction/job transfer, and 4 other
recordable; invalid/missing values remain Unknown. The exclusive outcome counts
sum exactly to report count. A DAFW-classified case may also contain restricted days.

Individual day fields are known only when finite, numeric, nonnegative integers.
Zero is a known value; missing/invalid values are never changed into zero. Individual
or combined days above 180 create review flags, not errors, capping, or corrections.
Outcome/day inconsistencies are separately profiled for review.

- `primary`: every date-aligned eligible report.
- `day_review_sensitivity`: the primary population excluding the predefined
  individual/combined >180-day review flags. This is a stress test, not proof
  that the excluded reports are incorrect.

Day totals are blocked by default. To release a day measure, supply a reviewed
policy with the exact original raw source hashes, a substantive review note, and
`accept_reported_values` for that metric. Policy acceptance means a documented
decision to summarize supplied valid reported values, not certification of true
paid work time. Partial known-value coverage remains explicit. No clipping,
imputation, or selection of a favorable scenario occurs automatically.

## Public table and calculations

`case_pattern_summary.csv` has one observed year × mechanism × SOC major × scenario
cell. It contains report counts, exclusive outcome counts, accepted day sums,
known/invalid day denominators, review-flag counts, and day-publication status.
There are no subtotal rows, raw narratives, identifying fields, or repeated
population-denominator columns. `case_coverage.csv` reconciles inclusion steps.

Mean reported days, if cleared, is summed accepted days divided by the corresponding
known-value report count. A zero denominator returns missing. Shares retain
Unknown/Other and use the selected year/occupation/scenario population. Never
average cell means or medians to obtain a pooled statistic.

## Reproduction

```bash
uv run --locked python -m src.analysis.case_patterns \
  --case-fields-zip "$HOME/Downloads/safeshift_case_fields.zip"
```

Use fresh output directories or explicitly pass `--overwrite`. Classification,
mechanism/occupation totals, coverage, and the source/run manifest are regenerated
together. The default is a frequency/outcome handoff with day sums blocked.

## Sources

- https://www.osha.gov/sites/default/files/case_detail_data_dictionary.pdf
- https://www.osha.gov/laws-regs/regulations/standardnumber/1904/1904.7
- https://www.bls.gov/soc/2018/major_groups.htm
- The supplied source-year crosswalk and raw-field export manifests.
