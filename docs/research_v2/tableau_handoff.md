# SafeShift Tableau workbook and final application checks

`tableau/research_v2/SafeShift_Research.twbx` is a native packaged workbook with
two separate aggregate data sources, eight worksheets, and three dashboards.
It contains annual and case CSVs rather than raw case details. A plain `.twb`
and matching `Data/` directory are also generated for version control.

## Open and inspect

Open the `.twbx` in Tableau Desktop or Tableau Public on the Mac. The application
may upgrade its legacy-compatible workbook format on opening. Do not publish
automatically: first confirm the data sources, controls, displayed values, and
layout. If opening fails, preserve the exact error and share it with the lead;
a well-formed XML/ZIP check alone is not a successful Tableau application check.

The dashboards are Annual warehouse patterns, Mechanisms and occupations, and
Methods and limits. Annual controls choose exactly one scenario, one/all years,
and one/all size groups. The year control also includes a 2023–2024 comparison
range matching the QA references. Case controls choose exactly one scenario, one/both years,
and one/all occupation groups. Mechanism selection highlights rather than filters.
Both tables retain their own populations and are never joined on year.

## Required calculation behavior

- DART rate = 200,000 × SUM(DART cases) / SUM(hours), with a missing result for
  zero hours. It is never an average of site or group rates.
- Establishment counts across years mean establishment-years, not unique sites.
- Case shares use the entire selected year/occupation/scenario population,
  including Unknown and Other mechanisms. Highlighting leaves this denominator.
- A single-value scenario parameter and mandatory Boolean row filter appear on
  every worksheet; there is no combined-scenarios state.
- Day calculations use a global selected-population gate. Any selected blocked
  cell withholds the total, rather than allowing SUM to ignore missing cells.
- If days remain blocked, the fourth case panel counts reports involving days
  away. It does not substitute report frequency for duration. When the day
  policy clears DAFW days, rebuilding switches that panel to accepted days.

## Acceptance checklist in Tableau

Use `tableau_qa_references.csv` for exact reference counts, denominators, and rates.
Its observed-value cells intentionally remain blank until application readback.

1. Verify annual 2016, 2024, and 2025 separately under both scenarios.
2. Verify a size selection and the All-years pooled rate. Controls must change
   all annual charts consistently, without doubling counts.
3. Verify case 2023 and 2024 separately and together; then select one occupation.
4. Confirm mechanism shares sum to 100% before display rounding and remain
   unchanged when a mechanism is highlighted.
5. Confirm Unknown and Other remain distinct, and the two reporting populations
   are not presented as having equal coverage.
6. Confirm blocked day values do not appear as zero or partial totals. If day
   publication is cleared, check known-value coverage and selected-population gates.
7. Inspect laptop-sized labels, tooltips, units, all control lists, and an empty
   selection. The 2025 primary exposure anomaly must remain explained.

Counts must agree exactly; compare unrounded rates within 0.000001. Record the
Tableau version, opening result, observed values, and any layout adjustment.
Only then change the application-check status in the build manifest to passed.

## Presentation assets and public sharing

`artifacts/research_v2/presentation/` contains count/rate, size, mechanism,
occupation, and outcome figures plus reference tables and a slide outline.
These use the actual aggregates, not synthetic demonstration rows. The revised
question is descriptive/comparative, not focused on predictive analysis.

The packaged workbook contains aggregate values and standard group labels only.
Raw IDs, full text, addresses, and free-text job titles are excluded. Audit files
with provisional day totals are not dashboard measures. A public publication
would make the packaged data available for download and is a separate action.

Implementation references:
https://github.com/tableau/document-api-python
https://github.com/tableau/tableau-document-schemas
https://help.tableau.com/current/pro/desktop/en-us/examples_text.htm
