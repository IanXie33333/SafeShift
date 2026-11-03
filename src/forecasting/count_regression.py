from pathlib import Path
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_poisson_deviance
import pandas as pd
import numpy as np
import statsmodels.api as sm
import time

# Load the forecasting reference data from the processed CSV file
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "forecasting_reference.csv"
df = pd.read_csv(DATA_PATH)

# Split the data into training and validation sets based on the "dataset_split" column
train = df[df["dataset_split"] == "train"].copy()
features = ["dart_count_t", "employee_count_t", "hours_worked_t"]
X_train = train[features]
Y_train = train["dart_count_t1"]

# Prepare the validation data for evaluation
val = df[df["dataset_split"] == "validation"].copy()
val_pred = val["dart_count_t"]

# Evaluate the persistence baseline (using the previous count as the prediction)
errors = val["dart_count_t1"] - val_pred
mae = errors.abs().mean()
rmse = np.sqrt((errors ** 2).mean())

print("Persistence Baseline Results")
print("MAE:", mae)
print("RMSE:", rmse)

# Fit a Poisson regression model on the training data
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
poisson_model = PoissonRegressor(max_iter=1000)
poisson_start = time.perf_counter()
poisson_model.fit(X_train_scaled, Y_train)
poisson_runtime = time.perf_counter() - poisson_start
print("Poisson regression training complete")

# Evaluate the Poisson regression model on the validation data
X_val = val[features]
Y_val = val["dart_count_t1"]

# Scale the validation features using the fitted scaler
X_val_scaled = scaler.transform(X_val)
poisson_pred = poisson_model.predict(X_val_scaled)

# Calculate the evaluation metrics for the Poisson regression model
poisson_mae = np.abs(Y_val - poisson_pred).mean()
poisson_rmse = np.sqrt(((Y_val - poisson_pred) ** 2).mean())

print("\nPoisson Regression Results")
print("MAE:", poisson_mae)
print("RMSE:", poisson_rmse)

# Debugging: Print the first 10 predictions and actual counts for the Poisson model
print("First 10 Poisson predictions:", poisson_pred[:10])
print("First 10 actual counts:", Y_val.iloc[:10].to_numpy())

print("\nPoisson Coefficients:")
for feature, coefficient in zip(features, poisson_model.coef_):
    print(feature, coefficient)

print("Intercept:", poisson_model.intercept_)

print("\nTraining target distribution")
print(Y_train.describe())
print("Training zero rate:", (Y_train == 0).mean())
print("Training variance:", Y_train.var())

# Negative-binomial regression with log-transfomred features
X_train_nb = np.log1p(X_train)
X_train_nb = sm.add_constant(X_train_nb)

nb_model = sm.GLM(
    Y_train,
    X_train_nb,
    family=sm.families.NegativeBinomial(alpha=1.0)
)

nb_start = time.perf_counter()
nb_results = nb_model.fit(maxiter=1000)
nb_runtime = time.perf_counter() - nb_start

print("\nNegative Binomial regression training complete")
print("Converged:", nb_results.converged)

print("\nScaled training feature ranges:")
for i, feature in enumerate(features):
    print(feature,
          "min:", X_train_scaled[:, i].min(),
          "max:", X_train_scaled[:, i].max())

# Evalulate negative-binomial regression model on the validation data
X_val_nb = np.log1p(X_val)
X_val_nb = sm.add_constant(X_val_nb, has_constant="add")

nb_pred = nb_results.predict(X_val_nb)

nb_mae = np.abs(Y_val - nb_pred).mean()
nb_rmse = np.sqrt(((Y_val - nb_pred) ** 2).mean())

print("\nNegative Binomial Regression Results")
print("MAE:", nb_mae)
print("RMSE:", nb_rmse)


# Compare Poisson deviance across all three models
epsilon = 1e-10

print("\nPoisson Deviance Comparison")
print("Persistence:", mean_poisson_deviance(Y_val, np.maximum(val_pred, epsilon)))
print("Poisson:", mean_poisson_deviance(Y_val, np.maximum(poisson_pred, epsilon)))
print("Negative Binomial:", mean_poisson_deviance(Y_val, np.maximum(nb_pred, epsilon)))

# training runtime comparison for all three models 
print("\nTraining Runtime Comparison")
print("Persistence: 0 seconds (no training required)")
print("Poisson:", round(poisson_runtime, 4), "seconds")
print("Negative Binomial:", round(nb_runtime, 4), "seconds")

# Save validation predicitons for all three models
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "count_regression"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

predictions = val[["pair_id", "dart_count_t1"]].copy()
predicitons = predictions.rename(columns={"dart_count_t1": "actual_count"})

predicitons["persistence_pred"] = val_pred
predicitons["poisson_pred"] = poisson_pred
predicitons["negative_binomial_pred"] = nb_pred

predicitons.to_csv(
    OUTPUT_DIR / "validation_predictions.csv", 
    index=False
)

print("\nValidation predictions saved successfully")

# Save model evaluation metrics
metrics = pd.DataFrame([
    {
        "model": "Persistence",
        "mae": mae,
        "rmse": rmse,
        "poisson_deviance": mean_poisson_deviance(
            Y_val, np.maximum(val_pred, epsilon)
        ),
        "training_seconds": 0.0
    },
    {
        "model": "Poisson",
        "mae": poisson_mae,
        "rmse": poisson_rmse,
        "poisson_deviance": mean_poisson_deviance(
            Y_val, np.maximum(poisson_pred, epsilon)
        ),
        "training_seconds": round(poisson_runtime, 4)
    },
    {
        "model": "Negative Binomial",
        "mae": nb_mae,
        "rmse": nb_rmse,
        "poisson_deviance": mean_poisson_deviance(
            Y_val, np.maximum(nb_pred, epsilon)
        ),
        "training_seconds": round(nb_runtime, 4)
    }
])

metrics.to_csv(
    OUTPUT_DIR / "model_metrics.csv",
    index=False
)

print("\nValidation metrics saved successfully")

# Compare observed and predicted zero rates
print("\nZero Rate Comparison")
print("Actual:", (Y_val == 0).mean())
print("Persistence:", (val_pred == 0).mean())
print("Poisson:", (poisson_pred < 0.5).mean())
print("Negative Binomial:", (nb_pred < 0.5).mean())

# Calculate residual variance for each model
print("\nResidual Dispersion Comparison")
print("Persistence:",
      np.var(Y_val.to_numpy() - val_pred.to_numpy()))

print("Poisson:",
      np.var(Y_val.to_numpy() - poisson_pred))

print("Negative Binomial:",
      np.var(Y_val.to_numpy() - nb_pred))

# Pearson dispersion diagnostics
n = len(Y_val)
p = len(features) + 1

poisson_pearson = np.sum(
    (Y_val.to_numpy() - poisson_pred) ** 2 
    / np.maximum(poisson_pred, epsilon)
) / (n - p)

nb_variance = nb_pred + 1.0 * nb_pred ** 2

nb_pearson = np.sum(
    (Y_val.to_numpy() - nb_pred) ** 2
    / np.maximum(nb_variance, epsilon)
) / (n - p)

print("\nPearson Dispersion Comparison")
print("Poisson:", poisson_pearson)
print("Negative Binomial:", nb_pearson)

# Compare average predicted and actual injury counts
print("\nMean Calibration Comparison")
print("Actual mean:", Y_val.mean())
print("Persistence mean:", val_pred.mean())
print("Poisson mean:", poisson_pred.mean())
print("Negative Binomial mean:", nb_pred.mean())

# Calibration analysis for the Negative Binomial model
calibration = pd.DataFrame({
    "actual": Y_val.to_numpy(),
    "predicted": nb_pred
})

calibration["risk_group"] = pd.qcut (
    calibration["predicted"],
    q=5,
    labels=False,
    duplicates="drop"
)

calibration_summary = calibration.groupby("risk_group").agg(
    actual_mean=("actual", "mean"),
    predicted_mean=("predicted", "mean"),
    count=("actual", "size")
)

print("\nNegative Binomial Calibration by Risk Group")
print(calibration_summary)

calibration_summary.to_csv(
    OUTPUT_DIR / "negative_binomial_calibration.csv"
)

print("Calibration results saved successfully")

# Identify exposure-related columns in the dataset
print("\nExposure-related columns:")
print([
    col for col in df.columns
    if "exposure" in col.lower() or "flag" in col.lower()
])
print("\nAll dataset columns:")
print(df.columns.tolist())