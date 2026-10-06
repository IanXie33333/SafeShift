# Work Package 2: Linkage and Forecasting Feasibility

## Matching Method

To figure out how establishments could be linked across consecutive years, I looked at several fields, including `id`, `establishment_id`, establishment name, street address, city, state, and ZIP code. From the initial inspection, I found that fields such as establishment name and address could change across years even when the records seemed to represent the same establishment.

Out of the fields I examined, `establishment_id` was the most consistent for tracking an establishment across different years. Because of this, I used `establishment_id` as the primary key for linking consecutive-year records. I then used normalized establishment name, street address, city, state, and ZIP code to check how reliable those links were.

## 2. Linkage Results

Using `establishment_id` as the primary identifier, I identified candidate transitions whenever the same establishment ID appeared in two consecutive years. The number of candidate transitions ranged from about 2,400 to 5,700 for each year pair. There was also a general increase over time, from 2,398 candidate transitions between 2016 and 2017 to 5,745 between 2024 and 2025.

| Year Pair | Candidate Transitions | Valid Transitions |
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

| Linkage Classification | Count | Percentage |
|---|---:|---:|
| High confidence | 32,169 | 89.69% |
| Uncertain | 3,683 | 10.27% |
| Failed validation | 13 | 0.04% |
| **Total** | **35,865** | **100%** |

After applying the linkage eligibility criteria, 35,865 valid consecutive-year transitions remained across the nine year pairs from 2016–2017 through 2024–2025. This gives us a substantial amount of linked establishment data to work with when we move into forecasting. However, the number of transitions alone does not tell us whether the data is reliable enough, so I also checked the quality of the matches.

Of the 35,865 valid transitions, 32,169 (about 89.7%) were classified as high-confidence matches. This means the establishment name, address, city, state, and ZIP code all agreed after normalization. Another 3,683 transitions (about 10.3%) were uncertain because some, but not all, of those fields agreed. Only 13 transitions (about 0.04%) failed all of the validation checks.

Based on these results, I am reasonably confident that `establishment_id` can be used as the main linkage key. The fact that almost 90% of the transitions passed every validation check supports using it across consecutive years. At the same time, the uncertain and failed cases show why the ID should still be checked against the other establishment information instead of assuming it is always correct.

## 3. Ambiguous and Unmatched Records

Not every transition was a clean high-confidence match. The 3,683 uncertain transitions had inconsistencies in at least one of the validation fields. For example, an establishment could have the same normalized name across two years but report a different address the following year. This could mean that the establishment moved, its information changed, or there was some other difference in how it was reported. Since the data does not always tell us why these changes happened, I treated these transitions as uncertain instead of automatically accepting or rejecting them.

The 13 failed-validation transitions were more suspicious because none of the validation fields agreed even though the records shared the same `establishment_id`. These cases show that `establishment_id` is useful, but it should not be treated as a perfectly reliable identifier on its own.

I also found duplicate establishment-year records during the analysis. These were excluded from linkage eligibility instead of choosing one of the duplicate records arbitrarily. There were also establishment IDs that appeared in one year but were unmatched in the following year. An unmatched ID only tells us that the same `establishment_id` was not found in the next year's linkage-eligible data. It does not tell us whether the establishment closed, changed IDs, stopped reporting, or disappeared for some other reason.

## 4. DART Distribution and Forecasting Feasibility

The DART count is the outcome that will eventually be forecast for each establishment. The distribution is heavily right-skewed. The mean DART count is 6.49, while the median is only 1. This suggests that most observations have relatively low DART counts, while a smaller number of very large values pull the mean upward.

The variance is 478.83, which is much larger than the mean of 6.49. This shows that the DART counts are highly spread out rather than being concentrated around the average. Also, 41.57% of the observations have a DART count of zero, while the maximum is 630. Together, these results show that the data contains many low or zero counts along with a much smaller number of very large counts.

Using the 1.5 × IQR rule, DART counts above 10 were identified as potential outliers. There were 8,884 observations above this cutoff, which is about 12.27% of the dataset. These observations are not necessarily errors, but they show that large DART counts are an important part of the distribution and will need to be considered when choosing and evaluating forecasting models.

| DART Statistic | Value |
|---|---:|
| Zero DART observations | 41.57% |
| Mean | 6.49 |
| Median | 1.00 |
| Variance | 478.83 |
| Maximum | 630 |
| Q1 | 0.00 |
| Q3 | 4.00 |
| IQR | 4.00 |
| 1.5 × IQR upper cutoff | 10.00 |
| Observations above cutoff | 8,884 |
| Percentage above cutoff | 12.27% |

## 5. Conclusion

Overall, I think the linkage results are strong enough to move forward. Out of 35,865 valid consecutive-year transitions, about 89.7% were high-confidence, about 10.3% were uncertain, and only 13 failed all of the validation checks. This supports using `establishment_id` as the main way to track establishments across consecutive years, while still using the other fields to check the reliability of each link.

The linked dataset also seems large enough to move forward with testing forecasting models. The number of linked transitions generally increased over time, giving us a substantial set of consecutive-year observations to work with. However, the DART distribution could make forecasting more difficult because there are many zero values, a large amount of variation, and a long right tail.

Based on this analysis, I think it makes sense to proceed to the forecasting stage. This does not mean that the models will necessarily predict DART counts accurately. Their actual performance will still need to be tested, and factors such as uncertain linkages, data quality, the unusual DART distribution, and model assumptions could affect the results.