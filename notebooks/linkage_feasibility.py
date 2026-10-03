import pandas as pd

pd.set_option("display.max_columns", None)

# ============================================================
# 1. LOAD DATA
# ============================================================

warehouse_df = pd.read_csv("data/processed/warehouses_4931.csv")

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

linkage_df = warehouse_df_sorted[
    warehouse_df_sorted["candidate_for_linkage"]
].copy()

linkage_df = linkage_df.sort_values(["establishment_id", "year"])

linkage_df["previous_year"] = (
    linkage_df.groupby("establishment_id")["year"].shift(1)
)

linkage_df["consecutive_year"] = (
    linkage_df["year"] == linkage_df["previous_year"] + 1
)

valid_transitions = linkage_df[
    linkage_df["consecutive_year"]
]

transition_counts = (
    valid_transitions
    .groupby(["year", "previous_year"])
    .size()
)

print("Consecutive-year transition counts after candidate filtering:")
print(transition_counts)
print("Total consecutive-year transitions after candidate filtering:", len(valid_transitions))

linkage_df["previous_name"] = (
    linkage_df.groupby("establishment_id")["name_normalized"].shift(1)
)

same_name = (
    linkage_df["name_normalized"]
    == linkage_df["previous_name"]
)

linkage_df["same_name_consecutive"] = (
    same_name & linkage_df["consecutive_year"]
)

linkage_df["previous_city"] = (
    linkage_df.groupby("establishment_id")["city"].shift(1)
)

same_city = (
    linkage_df["city"]
    == linkage_df["previous_city"]
)

linkage_df["same_city_consecutive"] = (
    same_city & linkage_df["consecutive_year"]
)

linkage_df["previous_state"] = (
    linkage_df.groupby("establishment_id")["state"].shift(1)
)

same_state = (
    linkage_df["state"]
    == linkage_df["previous_state"]
)

linkage_df["same_state_consecutive"] = (
    same_state & linkage_df["consecutive_year"]
)

linkage_df["previous_zip_code"] = (
    linkage_df.groupby("establishment_id")["zip_code"].shift(1)
)

same_zip_code = (
    linkage_df["zip_code"]
    == linkage_df["previous_zip_code"]
)

linkage_df["same_zip_code_consecutive"] = (
    same_zip_code & linkage_df["consecutive_year"]
)

linkage_df["previous_address"] = (
    linkage_df.groupby("establishment_id")["address_normalized"].shift(1)
)

same_address = (
    linkage_df["address_normalized"]
    == linkage_df["previous_address"]
)

linkage_df["same_address_consecutive"] = (
    same_address & linkage_df["consecutive_year"]
)

# High confidence: all five identity fields match
high_confidence = (
    same_name
    & same_address
    & same_city
    & same_state
    & same_zip_code
    & linkage_df["consecutive_year"]
)

# Failed validation: all five identity fields differ
failed_validation = (
    linkage_df["consecutive_year"]
    & ~same_name
    & ~same_address
    & ~same_city
    & ~same_state
    & ~same_zip_code
)

# Uncertain confidence: some identity fields match
uncertain_confidence = (
    linkage_df["consecutive_year"]
    & ~high_confidence
    & ~failed_validation
)

print("High confidence:", high_confidence.sum())
print("Failed validation:", failed_validation.sum())
print("Uncertain confidence:", uncertain_confidence.sum())

# Check for duplicate records per establishment_id and year
id_year_record_counts = (
    warehouse_df_sorted
    .groupby(["establishment_id", "year"])
    .size()
)

print("Duplicate establishment-year record counts:")
print(id_year_record_counts[id_year_record_counts > 1])

# Count IDs present in one year but absent in the next after candidate filtering
for year in range(2016, 2025):
    ids_current = set(linkage_df[linkage_df["year"] == year]["establishment_id"])
    ids_next = set(linkage_df[linkage_df["year"] == year + 1]["establishment_id"])
    unmatched_ids = ids_current - ids_next
    print(f"Unmatched IDs {year} -> {year + 1}: {len(unmatched_ids)}")

# ============================================================
# 4. DART DISTRIBUTION AND FORECASTING FEASIBILITY
# ============================================================

zero_percentage = ((warehouse_df["dart_count"] == 0).sum() / len(warehouse_df)) * 100

print(f"Zero DART percentage: {zero_percentage:.2f}%")

dart_mean = warehouse_df["dart_count"].mean()

print(f"DART mean: {dart_mean:.2f}")

dart_variance = warehouse_df["dart_count"].var()

print(f"DART variance: {dart_variance:.2f}")

dart_median = warehouse_df["dart_count"].median()

print(f"DART median: {dart_median:.2f}")

dart_maximum = warehouse_df["dart_count"].max()

print(f"DART maximum: {dart_maximum:.2f}")

dart_q1 = warehouse_df["dart_count"].quantile(0.25)

dart_q3 = warehouse_df["dart_count"].quantile(0.75)

print(f"DART Q1: {dart_q1:.2f}")
print(f"DART Q3: {dart_q3:.2f}")

dart_iqr = dart_q3 - dart_q1

print(f"DART IQR: {dart_iqr:.2f}")

dart_upper_cutoff = dart_q3 + 1.5 * dart_iqr

print(f"DART upper cutoff: {dart_upper_cutoff:.2f}")

dart_outlier_count = (warehouse_df["dart_count"] > dart_upper_cutoff).sum()

print(f"DART outlier count: {dart_outlier_count}")

dart_outlier_percentage = (dart_outlier_count / len(warehouse_df)) * 100

print(f"DART outlier percentage: {dart_outlier_percentage:.2f}%")
