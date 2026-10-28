import pandas as pd

pd.set_option("display.max_columns", None)

def load_warehouse_data(path="data/processed/warehouses_4931.csv"):
    """Preserve cleaned identifiers and postal codes when reading the CSV."""
    return pd.read_csv(path, dtype={"establishment_id": "string", "zip_code": "string"})

def build_forecasting_pairs(warehouse_df_sorted):
    # Every member of an ambiguous establishment/year group must be excluded.
    eligible = warehouse_df_sorted["candidate_for_linkage"].fillna(False)
    duplicate_key = warehouse_df_sorted.duplicated(
        ["establishment_id", "year"], keep=False
    )
    if (eligible & duplicate_key).any():
        raise ValueError(
            "Duplicate establishment/year groups remain eligible; "
            "exclude all their rows in candidate_for_linkage before pairing."
        )
    linkage_df = warehouse_df_sorted.loc[eligible].copy()

    # Sort each establishemnt's records chronologically
    linkage_df = linkage_df.sort_values(["establishment_id", "year"])

    # Retrieve the preceding year's values for each establishment
    linkage_df["previous_year"] = (
        linkage_df.groupby("establishment_id")["year"].shift(1)
    )

    linkage_df["dart_count_t"] = (
        linkage_df.groupby("establishment_id")["dart_count"].shift(1)
    )

    linkage_df["employee_count_t"] = (
        linkage_df.groupby("establishment_id")["annual_average_employees"].shift(1)
    )

    linkage_df["hours_worked_t"] = (
        linkage_df.groupby("establishment_id")["total_hours_worked"].shift(1)
    )

    # Retrieve previous-year identity fields for linkage validation
    linkage_df["previous_name"] = (
        linkage_df.groupby("establishment_id")["name_normalized"].shift(1)
    )

    linkage_df["previous_address"] = (
        linkage_df.groupby("establishment_id")["address_normalized"].shift(1)
    )

    linkage_df["previous_city"] = (
        linkage_df.groupby("establishment_id")["city"].shift(1)
    )

    linkage_df["previous_state"] = (
        linkage_df.groupby("establishment_id")["state"].shift(1)
    )

    linkage_df["previous_zip_code"] = (
        linkage_df.groupby("establishment_id")["zip_code"].shift(1)
    )

    # Current record supplies the next-year forecasting target
    linkage_df["dart_count_t_plus_1"] = linkage_df["dart_count"]

    # Only consecutive years form forecasting pairs
    linkage_df["consecutive_year"] = (
        linkage_df["year"] == linkage_df["previous_year"] + 1
    )

    paired_df = linkage_df[linkage_df["consecutive_year"]].copy()

    paired_df["year_t"] = paired_df["previous_year"]
    paired_df["year_t_plus_1"] = paired_df["year"]

    # Standardized column names for the forecasting dataset
    paired_df["feature_year"] = paired_df["year_t"].astype(int)
    paired_df["target_year"] = paired_df["year_t_plus_1"].astype(int)
    paired_df["dart_count_t1"] = paired_df["dart_count_t_plus_1"]

    # Reserve 2024 -> 2025 pairs for holdout evaluation
    paired_df["dataset_split"] = "train_validation"

    paired_df.loc[
        paired_df["year_t_plus_1"] == 2025,
        "dataset_split"
    ] = "holdout_test"

    return paired_df

def classify_linkage(paired_df):
    classified_df = paired_df.copy()
    field_pairs = [
        ("name_normalized", "previous_name"),
        ("address_normalized", "previous_address"),
        ("city", "previous_city"),
        ("state", "previous_state"),
        ("zip_code", "previous_zip_code"),
    ]
    complete = pd.Series(True, index=classified_df.index)
    all_agree = pd.Series(True, index=classified_df.index)
    any_agree = pd.Series(False, index=classified_df.index)

    for current_col, previous_col in field_pairs:
        current = classified_df[current_col]
        previous = classified_df[previous_col]
        usable = (
            current.notna()
            & previous.notna()
            & current.astype("string").str.strip().ne("").fillna(False)
            & previous.astype("string").str.strip().ne("").fillna(False)
        )
        agrees = pd.Series(False, index=classified_df.index)
        agrees.loc[usable] = current.loc[usable].eq(previous.loc[usable]).fillna(False)
        complete &= usable
        all_agree &= agrees
        any_agree |= agrees

    # Missing identity evidence is uncertain, rather than agreement or a proven mismatch.
    classified_df["linkage_class"] = "uncertain_confidence"
    classified_df.loc[complete & all_agree, "linkage_class"] = "high_confidence"
    classified_df.loc[complete & ~any_agree, "linkage_class"] = "failed_validation"
    return classified_df
# Function testing happens later, after warehouse_df_sorted is created.

# ============================================================
# 1. LOAD DATA
# ============================================================

warehouse_df = load_warehouse_data()

print("\n========== DATASET COLUMNS ==========")
print(warehouse_df.columns.tolist())
print("========== END DATASET COLUMNS ==========")

print(f"Dataset shape: {warehouse_df.shape}")

# ============================================================
# 2. ESTABLISHMENT ID EXPLORATION AND NORMALIZATION
# ============================================================

# Count the number of years each establishment ID appears
id_year_counts = warehouse_df.groupby("establishment_id")["year"].nunique()

# Count establishments by number of years observed
year_count_distribution = id_year_counts.value_counts().sort_index()

print("Establishment IDs by number of years observed:")
print(year_count_distribution)

# Count the number of unique establishment names per establishment ID
id_name_counts = warehouse_df.groupby("establishment_id")["establishment_name"].nunique()

# Count establishments by number of unique names
name_count_distribution = id_name_counts.value_counts().sort_index()

print("Establishment IDs by number of unique names:")
print(name_count_distribution)

# Count candidate consecutive-year transitions before linkage filtering
for year in range(2016, 2025):
    ids_current = set(warehouse_df[warehouse_df["year"] == year]["establishment_id"])
    ids_next = set(warehouse_df[warehouse_df["year"] == year + 1]["establishment_id"])
    consecutive_transitions = ids_current & ids_next
    print(f"Candidate transitions from {year} to {year + 1}: {len(consecutive_transitions)}")

# Identify establishment IDs associated with multiple names
multi_name_ids = id_name_counts[id_name_counts > 1]

print(f"Number of IDs with more than one name: {len(multi_name_ids)}")

# Normalize names for case, punctuation, and spacing
warehouse_df["name_normalized"] = (
    warehouse_df["establishment_name"]
    .str.lower()
    .str.replace(r'[^\w\s]', " ", regex=True)
    .str.replace(r'\s+', " ", regex=True)
    .str.strip()
)

# Summarize name consistency using the final normalization
id_name_counts_normalized = warehouse_df.groupby("establishment_id")["name_normalized"].nunique()

name_count_distribution_normalized = id_name_counts_normalized.value_counts().sort_index()

print("Establishment IDs by number of unique normalized names:")
print(name_count_distribution_normalized)

multi_name_ids_normalized = id_name_counts_normalized[id_name_counts_normalized > 1]

print(f"Number of IDs with more than one normalized name: {len(multi_name_ids_normalized)}")

# Evaluate ZIP-code consistency
id_zip_counts = warehouse_df.groupby("establishment_id")["zip_code"].nunique()

# Count number of ZIP codes for each establishment ID
id_zip_distribution = id_zip_counts.value_counts().sort_index()

print("Establishment IDs by number of unique ZIP codes:")
print(id_zip_distribution)

# Evaluate raw address consistency
id_address_counts = warehouse_df.groupby("establishment_id")["street_address"].nunique()

id_address_distribution = id_address_counts.value_counts().sort_index()

print("Establishment IDs by number of unique raw addresses:")
print(id_address_distribution)

# Normalize street addresses
warehouse_df["address_normalized"] = (
    warehouse_df["street_address"]
    .str.lower()
    .str.replace(r'[^\w\s]', " ", regex=True)
    .str.replace(r'\bst\b', 'street', regex=True)
    .str.replace(r'\s+', " ", regex=True)
    .str.strip()
)

# Re-evaluate unique addresses after normalization
id_address_counts_normalized = warehouse_df.groupby("establishment_id")["address_normalized"].nunique()

id_address_distribution_normalized = id_address_counts_normalized.value_counts().sort_index()

print("Establishment IDs by number of unique normalized addresses:")
print(id_address_distribution_normalized)

warehouse_df_sorted = warehouse_df.sort_values(["establishment_id", "year"])

# Compare each record with the previous address within its establishment ID
warehouse_df_sorted["previous_address"] = (
    warehouse_df_sorted.groupby("establishment_id")["address_normalized"].shift(1)
)

warehouse_df_sorted["address_changed"] = (
    warehouse_df_sorted["previous_address"].notna()
    & (warehouse_df_sorted["address_normalized"] != warehouse_df_sorted["previous_address"])
)

warehouse_df_sorted["previous_year"] = (
    warehouse_df_sorted.groupby("establishment_id")["year"].shift(1)
)

warehouse_df_sorted["consecutive_year"] = (
    warehouse_df_sorted["year"] == warehouse_df_sorted["previous_year"] + 1
)

warehouse_df_sorted["same_address_consecutive"] = (
    warehouse_df_sorted["consecutive_year"]
    & ~warehouse_df_sorted["address_changed"]
)

# Summarize consecutive-year observations and address consistency
# Calculate the percentage of establishments with consecutive years
total_ids = warehouse_df["establishment_id"].nunique()

consecutive_ids = warehouse_df_sorted[
    warehouse_df_sorted["consecutive_year"]
]["establishment_id"].nunique()

consecutive_id_percentage = (consecutive_ids / total_ids) * 100

print(f"Establishments with at least one consecutive-year observation: {consecutive_id_percentage:.2f}%")

# Calculate the percentage of consecutive transitions with the same address
total_consecutive_transitions = warehouse_df_sorted["consecutive_year"].sum()

same_address_transitions = warehouse_df_sorted["same_address_consecutive"].sum()

same_address_percentage = (same_address_transitions / total_consecutive_transitions) * 100

print(f"Consecutive-year transitions with the same address: {same_address_percentage:.2f}%")

# Calculate the percentage of consecutive transitions with a changed address
changed_consecutive_transitions = total_consecutive_transitions - same_address_transitions

changed_address_percentage = (changed_consecutive_transitions / total_consecutive_transitions) * 100

print(f"Consecutive-year transitions with a changed address: {changed_address_percentage:.2f}%")

# ============================================================
# 3. CONSECUTIVE-YEAR LINKAGE ANALYSIS
# ============================================================

paired_df = classify_linkage(
    build_forecasting_pairs(warehouse_df_sorted)
)

# Validate consecutive-year forecasting pairs
assert (
    paired_df["target_year"] == paired_df["feature_year"] + 1
).all()

# Ensure each establishment has at most one pair per year transition
assert not paired_df.duplicated(
    ["establishment_id", "feature_year", "target_year"]
).any()

# Ensure high-confidence pairs have nonmissing forecasting targets
high_confidence_pairs = paired_df[
    paired_df["linkage_class"] == "high_confidence"
].copy()

assert not high_confidence_pairs["dart_count_t1"].isna().any()

# Select uncertain pairs for separate review
uncertain_pairs = paired_df[
    paired_df["linkage_class"] == "uncertain_confidence"
].copy()

# Select columns needed for forecasting
forecast_columns = [
    "establishment_id",
    "feature_year",
    "target_year",
    "employee_count_t",
    "hours_worked_t",
    "dart_count_t",
    "dart_count_t1",
    "linkage_class",
    "dataset_split",
]

# Explort high-confidence forecasting pairs
high_confidence_pairs[forecast_columns].to_csv(
    "data/processed/forecasting_high_confidence_pairs.csv",
    index=False
)

# Export uncertain pairs separately
uncertain_pairs[forecast_columns].to_csv(
    "data/processed/forecasting_uncertain_pairs.csv",
    index=False
)

print("Forecasting CSV exports completed!")

print("\n" + "=" * 50)
print("STEP 1 PAIR VALIDATION OUTPUT")
print("=" * 50)

print (
    paired_df [
        [
            "establishment_id",
            "year_t",
            "year_t_plus_1",
            "dart_count_t",
            "dart_count_t_plus_1"
        ]
    ].head(10).to_string(index=False)
)

print("\n========== DATASET SPLIT VALIDATION ==========")

print(
    paired_df.groupby("dataset_split").size()
)

print("========== END DATASET SPLIT VALIDATION ==========")

# Count candidate transitions by feature year and target year
transition_counts = (
    paired_df
    .groupby(["year_t", "year_t_plus_1"])
    .size()
)

print("\n========== CANDIDATE TRANSITION COUNTS ==========")
print(transition_counts)
print("Total candidate transitions:", len(paired_df))
print("========== END CANDIDATE TRANSITION COUNTS ==========")

# Verify the results
print("\n========== LINKAGE CLASS VALIDATION ==========")

print(
    paired_df.groupby(
        ["dataset_split", "linkage_class"]
    ).size()
)

print("========== END LINKAGE CLASS VALIDATION ==========")

# Select high-confidence pairs for the primary forecasting cohort
eligible_pairs = paired_df[
    paired_df["linkage_class"] == "high_confidence"
].copy()

# Separate historical training/validation from held-out evaluation
training_pairs = eligible_pairs [
    eligible_pairs["dataset_split"] == "train_validation"
].copy()

holdout_pairs = eligible_pairs [
    eligible_pairs["dataset_split"] == "holdout_test"
].copy()

print("\n========== ELIGIBLE FORECASTING PAIRS ==========")

print("Training/validation:", len(training_pairs))
print("Holdout test:", len(holdout_pairs))

print("========== END ELIGIBLE FORECASTING PAIRS ==========")

# Select next-year DART outcomes from eligilbe training pairs
dart_target = training_pairs["dart_count_t_plus_1"]

# Calculate DART distribution statistics
dart_mean = dart_target.mean()
dart_variance = dart_target.var()
dart_median = dart_target.median()
dart_max = dart_target.max()

dart_zero_percentage = (dart_target == 0).mean() * 100

dart_q1 = dart_target.quantile(0.25)
dart_q3 = dart_target.quantile(0.75)

dart_iqr = dart_q3 - dart_q1
dart_upper_cutoff = dart_q3 + 1.5 * dart_iqr

dart_outlier_count = (dart_target > dart_upper_cutoff).sum()
dart_outlier_percentage = (dart_outlier_count / len(dart_target)) * 100

print("\n========== TRAINING DART DISTRIBUTION ==========")

print(f"Sample size: {dart_target.count()}")
print(f"Zero DART percentage: {dart_zero_percentage:.2f}%")
print(f"DART mean: {dart_mean:.2f}")
print(f"DART variance: {dart_variance:.2f}")
print(f"DART median: {dart_median:.2f}")
print(f"DART maximum: {dart_max:.2f}")
print(f"DART Q1: {dart_q1:.2f}")
print(f"DART Q3: {dart_q3:.2f}")
print(f"DART IQR: {dart_iqr:.2f}")
print(f"DART upper cutoff: {dart_upper_cutoff:.2f}")
print(f"DART outlier count: {dart_outlier_count}")
print(f"DART outlier percentage: {dart_outlier_percentage:.2f}%")

print("========== END TRAINING DART DISTRIBUTION ==========")

# Count linkage classifications for each consecutive-year transition
print("\n========== YEARLY LINKAGE CLASS COUNTS ==========")

yearly_linkage_counts = (
    paired_df.groupby(
        ["year_t", "year_t_plus_1", "dataset_split", "linkage_class"]
    )
    .size()
    .unstack(fill_value=0)
)

print(yearly_linkage_counts.to_string())

print("========== END YEARLY LINKAGE CLASS COUNTS ==========")

print("High confidence:", (paired_df["linkage_class"] == "high_confidence").sum())
print("Failed validation:", (paired_df["linkage_class"] == "failed_validation").sum())
print("Uncertain confidence:", (paired_df["linkage_class"] == "uncertain_confidence").sum())

# Check for duplicate records per establishment_id and year
id_year_record_counts = (
    warehouse_df_sorted
    .groupby(["establishment_id", "year"])
    .size()
)

print("Duplicate establishment-year record counts:")
print(id_year_record_counts[id_year_record_counts > 1])

# Count IDs present in one year but absent in the next
# using records eligible for linkage
candidate_records = warehouse_df_sorted[
    warehouse_df_sorted["candidate_for_linkage"]
].copy()

for year in range(2016, 2025):
    ids_current = set(
        candidate_records[
            candidate_records["year"] == year
        ]["establishment_id"]
    )

    ids_next = set(
        candidate_records[
            candidate_records["year"] == year + 1
        ]["establishment_id"]
    )

    unmatched_ids = ids_current - ids_next

    print(f"Unmatched IDs {year} -> {year + 1}: {len(unmatched_ids)}")
