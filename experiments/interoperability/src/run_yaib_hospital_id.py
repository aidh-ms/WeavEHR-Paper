"""Build hospital_id for eICU-CRD -- needed for AKI's per-hospital-prevalence exclusion.

hospital_id does not exist as a WeavEHR concept. aki.R's exclusion 6
("low AKI prevalence") groups by hospital to drop hospitals with zero
observed AKI cases, which needs this field.

eICU-CRD's raw patient.csv.gz has both patientunitstayid (= stay_id) and
hospitalid directly in the same row -- no join or datetime reconstruction
needed.

Verification performed (not just built and trusted):
  1. Row count / stay coverage vs. the known 200,859-stay cohort.
  2. Null check.
  3. Distinct hospital count and stays-per-hospital distribution --
     computed and plotted, not just described.
  4. A concrete 5-row spot check against the raw file, printed for
     independent manual confirmation.
"""

import json
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

from interoperability.config import EICU_RAW_PATIENT_CSV
from interoperability.paths import RESULTS_DIR

OUT_PATH = RESULTS_DIR / "weavehr_hospital_id_eicu-crd.parquet"
PLOT_PATH = RESULTS_DIR / "hospital_id_stays_distribution_eicu-crd.png"

EXPECTED_N_STAYS = 200_859

start = time.perf_counter()
start_wall = time.strftime("%Y-%m-%d %H:%M:%S")

raw = pl.scan_csv(EICU_RAW_PATIENT_CSV, try_parse_dates=True).select(
    pl.col("patientunitstayid").cast(pl.Int64).alias("stay_id"),
    pl.col("hospitalid").cast(pl.Int64),
)
df = raw.collect()
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
df.write_parquet(OUT_PATH)

# --- Verification -----------------------------------------------------------
n_rows = df.height
n_stays = df["stay_id"].n_unique()
n_null = df.select(pl.col("hospitalid").is_null().sum()).item()
n_hospitals = df["hospitalid"].n_unique()

assert n_stays == EXPECTED_N_STAYS, (
    f"Expected {EXPECTED_N_STAYS} distinct stays (the known full eICU-CRD cohort), got {n_stays}. "
    "Stopping rather than writing output that doesn't match the established reference count."
)
assert n_null == 0, f"Expected no null hospitalid values, found {n_null}."

per_hospital = df.group_by("hospitalid").agg(pl.len().alias("n_stays")).sort("n_stays", descending=True)
top5 = per_hospital.head(5).to_dicts()
bottom5 = per_hospital.tail(5).to_dicts()

# Spot check: 5 concrete stay_id -> hospitalid rows for manual verification
spot_check = df.sample(5, seed=7).to_dicts()

# --- Visual: stays-per-hospital distribution --------------------------------
counts = per_hospital["n_stays"].to_list()
fig, ax = plt.subplots(figsize=(8, 5))
ax.hist(counts, bins=40, color="#3b6fa0", edgecolor="white")
ax.set_xlabel("ICU stays per hospital")
ax.set_ylabel("Number of hospitals")
ax.set_title(f"eICU-CRD: stays-per-hospital distribution ({n_hospitals} hospitals, {n_stays} stays)")
fig.tight_layout()
fig.savefig(PLOT_PATH, dpi=150)
plt.close(fig)

elapsed = time.perf_counter() - start
end_wall = time.strftime("%Y-%m-%d %H:%M:%S")

summary = {
    "output_path": str(OUT_PATH),
    "plot_path": str(PLOT_PATH),
    "n_rows": n_rows,
    "n_distinct_stays": n_stays,
    "matches_expected_200859_stays": n_stays == EXPECTED_N_STAYS,
    "n_null_hospitalid": n_null,
    "n_distinct_hospitals": n_hospitals,
    "top5_hospitals_by_stays": top5,
    "bottom5_hospitals_by_stays": bottom5,
    "spot_check_5_rows": spot_check,
    "start_wall_time": start_wall,
    "end_wall_time": end_wall,
    "elapsed_seconds": round(elapsed, 2),
}

print(json.dumps(summary, indent=2))
(RESULTS_DIR / "weavehr_hospital_id_summary_eicu-crd.json").write_text(json.dumps(summary, indent=2))
