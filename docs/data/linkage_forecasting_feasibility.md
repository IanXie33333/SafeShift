# Work Package 2: Linkage and Forecasting Feasibility

## Matching Method

To determine how establishments could be linked across consecutive years, several fields were examined, including `id`, `establishment_id`, establishment name, street address, city, state, and ZIP code. Initial inspection showed that fields such as establishment name and address could change across years even when the records appeared to represent the same establishment.

Of the fields examined, `establishment_id` was the most consistent for tracking an establishment across different years. Because of this, `establishment_id` was used as the primary key for linking consecutive-year records. Normalized establishment name, street address, city, state, and ZIP code were then used to evaluate the reliability of those links.

## 2. Linkage Results

Using `establishment_id` as the primary identifier, candidate transitions were identified whenever the same establishment ID appeared in two consecutive years. The number of candidate transitions ranged from about 2,400 to 5,700 for each year pair. There was also a general increase over time, from 2,398 candidate transitions between 2016 and 2017 to 5,745 between 2024 and 2025.

| Year Pair | Candidate Transitions | Linkage-Eligible Candidate Pairs |
|---|---:|---:|
| 2016–2017 | 2,398 | 2,398 |
| 2017–2018 | 3,072 | 3,072 |
| 2018–2019 | 3,514 | 3,514 |
| 2019–2020 | 3,573 | 3,557 |
| 2020–2021 | 3,621 | 3,612 |
| 2021–2022 | 4,063 | 4,034 |
| 2022–2023 | 4,621 | 4,620 |
| 2023–2024 | 5,339 | 5,337 |
| 2024–2025 | 5,745 | 5,721 |

| Year Pair | High Confidence | Uncertain | Failed Validation |
|---|---:|---:|---:|
| 2016–2017 | 2,328 | 70 | 0 |
| 2017–2018 | 2,863 | 209 | 0 |
| 2018–2019 | 3,071 | 443 | 0 |
| 2019–2020 | 3,251 | 305 | 1 |
| 2020–2021 | 3,062 | 546 | 4 |
| 2021–2022 | 3,319 | 711 | 4 |
| 2022–2023 | 3,895 | 724 | 1 |
| 2023–2024 | 5,019 | 317 | 1 |
| 2024–2025 | 5,361 | 358 | 2 |
| **Total** | **32,169** | **3,683** | **13** |

| Linkage Classification | Count | Percentage |
|---|---:|---:|
| High confidence | 32,169 | 89.69% |
| Uncertain | 3,683 | 10.27% |
| Failed validation | 13 | 0.04% |
| **Total** | **35,865** | **100%** |

After applying the linkage eligibility criteria, 35,865 candidate consecutive-year transitions remained across the nine year pairs from 2016–2017 through 2024–2025. These transitions were evaluated using normalized establishment names, street addresses, cities, states, and ZIP codes to determine linkage confidence. Of the candidate transitions, 32,169 were classified as high-confidence matches and retained for the primary forecasting dataset. The remaining 3,683 uncertain transitions were separated for review, while 13 failed-validation transitions were excluded.

Of the 35,865 candidate transitions, 32,169 (about 89.7%) were classified as high-confidence matches. This means the establishment name, address, city, state, and ZIP code all agreed after normalization. Another 3,683 transitions (about 10.3%) were uncertain because some, but not all, of those fields agreed. Only 13 transitions (about 0.04%) failed all of the validation checks.

These results provide reasonable support for using `establishment_id` as the main linkage key. The fact that almost 90% of the transitions passed every validation check supports its use across consecutive years. At the same time, the uncertain and failed cases show why the ID should still be checked against other establishment information rather than assumed to be correct in every case.

## 3. Ambiguous and Unmatched Records

Not every transition was a clean high-confidence match. The 3,683 uncertain transitions had inconsistencies in at least one of the validation fields. For example, an establishment could have the same normalized name across two years but report a different address in the following year. This could mean that the establishment moved, its information changed, or there was some other difference in how it was reported. Since the data does not always indicate why these changes occurred, these transitions were treated as uncertain rather than being automatically accepted or rejected. The 3,683 uncertain transitions were excluded from the primary forecasting dataset and exported separately to data/processed/forecasting_uncertain_pairs.csv for further review. This preserves potentially useful observations without introducing uncertain establishment matches into the primary modeling cohort.

The 13 failed-validation transitions were more suspicious because none of the validation fields agreed even though the records shared the same `establishment_id`. These cases show that `establishment_id` is useful, but it should not be treated as a perfectly reliable identifier on its own. All 13 failed-validation transitions were excluded from both the primary forecasting dataset and the uncertain-pair review dataset.

Duplicate establishment-year records were also identified during the analysis. These were excluded from linkage eligibility rather than selecting one of the duplicate records arbitrarily. There were also establishment IDs that appeared in one year but were unmatched in the following year. An unmatched ID only indicates that the same `establishment_id` was not found in the next year's linkage-eligible data. It does not indicate whether the establishment closed, changed IDs, stopped reporting, or disappeared for some other reason.

## 4. Forecasting Dataset Construction

The forecasting dataset was constructed by pairing consecutive-year observations for each linkage-eligible establishment. Each row represents an establishment observed in year t and the same establishment's reported DART count in year t+1.

Previous-year values were retrieved using `groupby("establishment_id").shift(1)`. The forecasting features include the establishment's annual average employee count (`employee_count_t`), total hours worked (`hours_worked_t`), and DART count (`dart_count_t`) in year t. The prediction target is the following year's DART count (`dart_count_t1`).

The primary forecasting dataset contains 32,169 high-confidence establishment-year pairs. Of these, 26,808 pairs with target years before 2025 were assigned to the training/validation cohort. The remaining 5,361 pairs, representing 2024–2025 transitions, were reserved for holdout evaluation.

The primary dataset was exported to `data/processed/forecasting_high_confidence_pairs.csv`. Uncertain matches were exported separately for review, and failed-validation matches were excluded.

Three validation assertions were applied to confirm that target years immediately follow feature years, establishment-year transition keys are unique, and high-confidence forecasting targets are nonmissing. All three assertions passed.


## 5. DART Distribution and Forecasting Feasibility

The DART distribution was evaluated using the next-year forecasting target (`dart_count_t1`) from 26,808 high-confidence training/validation pairs. The 2024–2025 holdout observations were excluded from this analysis to preserve their use for future model evaluation.

The target distribution is heavily right-skewed. The mean DART count is 6.97, while the median is 1.00. This indicates that most observations have relatively low DART counts, while a smaller number of large values increase the mean.

The variance is 503.27, substantially exceeding the mean. Additionally, 38.50% of the observations have a DART count of zero, and the maximum observed count is 487. These characteristics indicate substantial variation in establishment-level injury outcomes.

Using the 1.5 × IQR rule, DART counts above 10 were identified as potential outliers. There were 3,545 observations above this cutoff, representing 13.22% of the development dataset. These observations are not necessarily errors, but they demonstrate the importance of accounting for extreme values during model development and evaluation.

| DART Statistic | Value |
|---|---:|
| Sample size | 26,808 |
| Zero DART observations | 38.50% |
| Mean | 6.97 |
| Median | 1.00 |
| Variance | 503.27 |
| Maximum | 487 |
| Q1 | 0.00 |
| Q3 | 4.00 |
| IQR | 4.00 |
| 1.5 × IQR upper cutoff | 10.00 |
| Observations above cutoff | 3,545 |
| Percentage above cutoff | 13.22% |

## 6. Conclusion

The linkage analysis identified 35,865 candidate consecutive-year transitions across the 2016–2025 reporting period. Of these, 32,169 (89.69%) were classified as high-confidence matches, 3,683 (10.27%) were classified as uncertain, and 13 (0.04%) failed validation. These findings support using `establishment_id` as the primary linkage key while validating matches against establishment names and location information.

The resulting high-confidence forecasting dataset contains 26,808 training/validation pairs and 5,361 holdout pairs. Uncertain matches were excluded from the primary modeling cohort and retained separately for further review, while failed-validation matches were excluded.

The development target distribution presents several modeling challenges. Approximately 38.50% of DART counts are zero, and the variance substantially exceeds the mean. The distribution also contains a long right tail, with 13.22% of observations exceeding the 1.5 × IQR upper cutoff.

Overall, the linkage results support proceeding to the forecasting stage using the high-confidence dataset. However, linkage confidence does not guarantee forecasting accuracy. Model performance must be evaluated using appropriate validation procedures, with the 2024–2025 holdout reserved for final evaluation.