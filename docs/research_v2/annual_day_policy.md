
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

## Automated anomaly screening

Screening was performed on the primary cohort of
72,235 establishment-year records.

| Screening condition | DAFW | DJTR |
|---|---:|---:|
| More than 180 days per corresponding case | 159 | 677 |
| Positive days with zero corresponding cases | 19 | 3,496 |

The 180-day threshold is a review trigger, not an
automatic exclusion threshold.

Positive days with zero corresponding cases are also
flagged for investigation. In particular, DJTR days
can occur alongside DAFW-classified cases, even when
the reported DJTR case count is zero.

Notable records requiring review include:

- South Texas - SCC (2024): 55,555,555 DAFW days
- HSN Piney Flats (2018): 1,091,856 DJTR days
- Men's Wearhouse - Addison DC (2019): 292,210 DJTR days
- The Paper Store - 0097 - Warehouse (2025):
  679 DAFW days with zero DART cases

These screening results do not establish reporting
errors. No records have been automatically excluded
based solely on these flags.

Both day measures remain blocked from publication
pending final anomaly disposition.
