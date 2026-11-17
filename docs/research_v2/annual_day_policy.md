# Annual Day-Measure Quality Policy

## Source-verified anomalies

Three extreme day values were checked against the original
OSHA ITA CSV files.

| Year | Establishment | Measure | Reported days | Source |
|---|---|---|---:|---|
| 2024 | South Texas - SCC | DAFW | 55,555,555 | ITA Data 2024.csv |
| 2018 | HSN Piney Flats | DJTR | 1,091,856 | ITA Data 2018.csv |
| 2019 | Men's Wearhouse - Addison DC | DJTR | 292,210 | ITA Data 2019.csv |

The reported values match the original source files.
They were not introduced during SafeShift processing.

Source verification does not establish that these values
are accurate. All three remain flagged for review.

## Current handling

- Preserve original source values without modification
- Do not automatically cap, trim, or impute extreme values
- Evaluate DAFW and DJTR separately
- Treat missing, negative, nonnumeric, and fractional
  day values as ineligible for their respective measures
- Count valid reported zeros as eligible values
- Treat unusually high days per case as a review signal,
  not an automatic exclusion rule

## Publication status

Both DAFW and DJTR day sums remain unpublished.

Current status: `blocked_review`

The annual summary exports empty day-sum fields until
the anomaly review and final disposition are documented.

Current eligibility counts reflect basic numeric validity
checks and are provisional pending anomaly review.

## Automated anomaly screening after the review patch

All day-review thresholds use total DART cases as the explicit broad screening
population. DAFW-classified cases may also contribute restricted days, so positive
restricted days with zero restricted-only cases do not alone enter the anomaly
queue. No review flag establishes an error or automatically removes a record.

The audit evaluates DAFW days, DJTR days, and their combined reported total. It
flags values above 180 times DART cases, positive days with zero DART cases, and
invalid/missing individual day values. The combined screen requires both day
fields to pass basic numeric validation. OSHA permits capping day tracking;
180 is a review threshold here, not a mandatory maximum or a clipping rule.

`reported_cases` preserves the corresponding original case count; the new
`review_case_count` is always `dart_count`, including for restricted days.
`high_days_per_case` and `positive_days_zero_cases` refer to this explicit DART
review denominator. `invalid_day_value` identifies basic invalidity/missingness.
The combined measure is an arithmetic total, not a measure of paid hours lost.

The revised supplied-snapshot audit contains 446 measure-level entries, rather
than the prior 4,351. The live output count and hashes are recorded in the generated
source/run manifest; a row can appear for more than one measure. This change
alters the review queue only. Counts, rates, numeric day-availability counts,
and both `blocked_review` publication statuses remain unchanged.

The three source-verified extreme values documented above retain pending
review status. Their final disposition is still needed before day totals or
burden findings can be displayed.
