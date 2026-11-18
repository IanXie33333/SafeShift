# Findings and limitations as shown in the Tableau dashboards (descriptive only)

All statements describe reported data; they do not show causes or which establishments are safer.

## Annual dashboard (OSHA ITA Form 300A, warehousing and storage, NAICS 4931, 2016-2025)

- Reported DART cases (primary scenario) rise from 20,191 in 2016 to a peak of 59,791 in 2022, then 57,703 (2023), 59,454 (2024) and 53,472 (2025). Part of this reflects more establishment-years reporting (4,463 input records in 2016, 9,885 in 2024), which is why establishment-years are shown beside the cases.
- Pooled DART cases per 100 full-time equivalents are highest for establishments with 1,000 or more employees (primary 2024: 5.134) and lowest for under 50 (2.186); 250-999 is 4.008 and 50-249 is 2.302. The pooled rate divides summed cases by summed reported hours; it is not an average of stored rates.
- 2025 primary hours contain one record of 100,551,000,000 hours, which pushes the 2025 rate for 50-249 employees to 0.017. Under the exposure-sensitivity scenario (employees > 0, 100 to 8,784 hours per employee) the same cell is 2.502. Treat the 2025 primary 50-249 point as an artefact of that record.
- Days away and restricted days are withheld (source status `blocked_review`).

## Case dashboard (provisional case export, 2023-2024 reports)

- Primary scenario, 115,174 reports across both years: overexertion / bodily reaction 55.7%, contact with objects/equipment 24.7%, falls/slips/trips 11.4%, transportation incidents 3.0%, unknown/missing mechanism 3.0%, harmful exposure 1.6%, other 0.6%. Unknown and Other are kept in the denominator.
- Transportation and material moving accounts for 76.8% of reports; unknown occupation 18.2%; office and administrative support 1.8%.
- Mean reported days per report with a valid value (all years, primary): days away 31.4 for transportation incidents, 19.7 for falls/slips/trips, 10.7 for overexertion; restricted/transfer days highest for overexertion (41.6) and falls (31.1). Means divide summed days by reports with a valid value.

## Limitations

- Case figures are from a provisional export, pending replacement by the WP2 owner's export.
- Reports are not workers and are not weighted to national totals; the 2023 and 2024 case files use different date and code conventions; mechanism groups come from a frozen year-specific Event-code map.
- Establishment-years are reporting records, not distinct establishments. Annual and case data describe different populations and are kept in separate sources, never joined or compared.
- 2024 shows 1,664 reports with the DAFW outcome but zero days (13 in 2023); reported as-is.
- Rates use reported hours and are not adjusted for job mix, shift, or other risk factors.
