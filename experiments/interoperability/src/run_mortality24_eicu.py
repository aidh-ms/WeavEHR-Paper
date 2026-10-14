"""Build the YAIB Mortality24 outcome/label table for eICU-CRD.

Replicates YAIB-cohorts' R/mortality.R exactly (documented from direct
source reading, cross-checked against the upstream repo at
github.com/rvandewater/YAIB-cohorts). Not a general-purpose label builder
-- this task's specific windowing/exclusion logic, ported to Python/Polars
over the extraction-chain's dynamic and static tables.

death_icu, not WeavEHR's own in_hospital_mortality concept
------------------------------------------------------------
WeavEHR's "in_hospital_mortality" concept maps to eICU's HOSPITAL_DISCHARGE
event (hospitaldischargestatus/hospitaldischargeoffset) -- that is
hospital-level mortality (ricu's death_hosp), not the ICU-level mortality
(death_icu) that YAIB-cohorts' Mortality24 task actually uses (mortality.R:
`load_step(dict["death_icu"], ...)`). Using WeavEHR's concept as-is would
silently build a different (related but not equivalent) task. death_icu is
built here directly from the raw eICU-CRD patient.csv.gz table instead
(unitdischargestatus == "Expired", at hour = unitdischargeoffset), matching
ricu's own eICU death_icu definition exactly -- the same raw file already
used for the static table's sex field.

Cohort logic (from mortality.R, base_cohort.R's canonical 5 + task's 2 --
the 7 base-cohort/task exclusions):
  1. Invalid length of stay (los_hours < 0)
  2. LOS < 6h
  3. Fewer than 4 distinct hours with any dynamic measurement
  4. > 12h gap between consecutive measurement-hours
  5. Age < 18
  6. Died within the first 30h of ICU admission (subset of #7, kept for
     fidelity to the original script)
  7. LOS < 30h

Label: death_icu (0/1), static per stay -- did the patient eventually die
in the ICU, for the retained (LOS >= 30h) cohort. Predictors: dynamic
table restricted to the first 24h (the Mortality24 observation window);
static table as built by run_yaib_static.py.

Output matches YAIB's expected contract: dyn.parquet, sta.parquet,
outc.parquet (label column), attrition.csv, under mortality24/eicu-crd/.
"""

import json
import time

import polars as pl

from interoperability.config import EICU_RAW_PATIENT_CSV
from interoperability.paths import MORTALITY24_TASK_DIR, RESULTS_DIR

DYN_PATH = RESULTS_DIR / "openicu_dyn_all.parquet"
STA_PATH = RESULTS_DIR / "weavehr_sta_eicu-crd.parquet"

MORTALITY24_TASK_DIR.mkdir(parents=True, exist_ok=True)

MAX_HOURS = 24  # Mortality24 observation window
MINUTES_TO_HOURS = 1 / 60  # eICU offsets are in minutes; hours(freq=1) grid elsewhere

start = time.perf_counter()
start_wall = time.strftime("%Y-%m-%d %H:%M:%S")

# --- Stay-level LOS and death_icu, straight from the raw eICU table ---------
raw = pl.scan_csv(EICU_RAW_PATIENT_CSV, try_parse_dates=True).select(
    pl.col("patientunitstayid").cast(pl.Int64).alias("stay_id"),
    (pl.col("unitdischargeoffset").cast(pl.Float64) * MINUTES_TO_HOURS).alias("los_hours"),
    (pl.col("unitdischargestatus") == "Expired").alias("death_icu"),
)

# --- Exclusion 3 & 4 inputs: distinct measurement-hours per stay -----------
dyn = pl.scan_parquet(DYN_PATH)
dynamic_cols = [c for c in dyn.collect_schema().names() if c not in ("stay_id", "time")]
has_measurement = pl.any_horizontal([pl.col(c).is_not_null() for c in dynamic_cols])
measurement_hours = dyn.filter(has_measurement).select("stay_id", "time").unique().sort("stay_id", "time")
meas_stats = measurement_hours.group_by("stay_id").agg(
    pl.len().alias("n_measurement_hours"),
    pl.col("time").diff().max().alias("max_gap"),
)

sta = pl.scan_parquet(STA_PATH).select("stay_id", "age")

cohort = (
    raw.join(meas_stats, on="stay_id", how="left")
    .join(sta, on="stay_id", how="left")
    .with_columns(
        pl.col("n_measurement_hours").fill_null(0),
        pl.col("max_gap").fill_null(0),
    )
)

excl1 = pl.col("los_hours") < 0
excl2 = pl.col("los_hours") < 6
excl3 = pl.col("n_measurement_hours") < 4
excl4 = pl.col("max_gap") > 12
excl5 = pl.col("age") < 18
excl6 = pl.col("death_icu") & (pl.col("los_hours") < 30)
excl7 = pl.col("los_hours") < 30

cohort = cohort.with_columns((excl1 | excl2 | excl3 | excl4 | excl5 | excl6 | excl7).alias("excluded"))

attrition = cohort.select(
    pl.len().alias("initial_n"),
    excl1.sum().alias("excl1_invalid_los"),
    excl2.sum().alias("excl2_los_lt_6h"),
    excl3.sum().alias("excl3_lt_4_measurement_hours"),
    excl4.sum().alias("excl4_gap_gt_12h"),
    excl5.sum().alias("excl5_age_lt_18"),
    excl6.sum().alias("excl6_died_before_30h"),
    excl7.sum().alias("excl7_los_lt_30h"),
    pl.col("excluded").not_().sum().alias("final_n"),
).collect()

retained = cohort.filter(~pl.col("excluded")).select("stay_id", "death_icu")

# --- Outcome table: static death_icu label for retained stays --------------
outc = retained.select(
    "stay_id",
    pl.col("death_icu").cast(pl.Int32).alias("label"),
).sort("stay_id")

# --- Dynamic table: retained stays, first 24h only --------------------------
dyn_out = (
    dyn.join(retained.select("stay_id"), on="stay_id", how="inner")
    .filter((pl.col("time") >= 0) & (pl.col("time") < MAX_HOURS))
    .sort("stay_id", "time")
)

# --- Static table: retained stays only --------------------------------------
sta_out = pl.scan_parquet(STA_PATH).join(retained.select("stay_id"), on="stay_id", how="inner").sort("stay_id")

outc_df = outc.collect()
dyn_df = dyn_out.collect()
sta_df = sta_out.collect()

outc_df.write_parquet(MORTALITY24_TASK_DIR / "outc.parquet")
dyn_df.write_parquet(MORTALITY24_TASK_DIR / "dyn.parquet")
sta_df.write_parquet(MORTALITY24_TASK_DIR / "sta.parquet")
attrition.write_csv(MORTALITY24_TASK_DIR / "attrition.csv")

elapsed = time.perf_counter() - start
end_wall = time.strftime("%Y-%m-%d %H:%M:%S")

n_final = int(attrition["final_n"][0])
n_positive = int(outc_df["label"].sum())

summary = {
    "task_dir": str(MORTALITY24_TASK_DIR),
    "attrition": attrition.to_dicts()[0],
    "n_stays_final": n_final,
    "n_positive_label": n_positive,
    "prevalence": round(n_positive / n_final, 4) if n_final else None,
    "dyn_rows": dyn_df.height,
    "sta_rows": sta_df.height,
    "outc_rows": outc_df.height,
    "start_wall_time": start_wall,
    "end_wall_time": end_wall,
    "elapsed_seconds": round(elapsed, 1),
}

print(json.dumps(summary, indent=2))
(MORTALITY24_TASK_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
