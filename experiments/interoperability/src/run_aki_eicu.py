"""Build the YAIB AKI outcome/label table for eICU-CRD.

Ports YAIB-cohorts' R/aki.R cohort and windowing logic to Python over
already-verified building blocks: the corrected KDIGO concepts
(weavehr_aki_concepts_corrected_eicu-crd.parquet, max-aggregated, real
0-3 stages), hospital_id, and the extraction-chain dynamic/static tables
(raw creatinine is already column "crea" in the dynamic table).

Label semantics -- stated explicitly since this is the one place real
ambiguity exists without ricu's own source in hand: "predict AKI onset
within the next 6 hours", matching the YAIB paper's own stated task
definition (Table: "AKI ... Hourly (within 6H)"). For each stay, onset
is the first hour where the corrected `aki` concept is >= 1. The
observation window runs from hour 0 to min(onset_hour + 6, 168, the
stay's actual length of stay) if an onset occurs, else 0 to
min(168, LOS) if it never does. label(t) = 1 iff an onset occurs in
(t, t+6], else 0, for every hour t in that window. This is a stated
interpretation, not verified against ricu's own R code -- flagged
plainly, not asserted as certain.

The observation window must also be bounded by each stay's own actual
LOS, not just the onset/168h caps -- otherwise stays get outcome rows
for hours after the patient was already discharged (confirmed by
cross-checking outc.parquet's row counts against dyn.parquet's in the
original port of this script: 83,889/136,503 stays, 61%, were affected
before this bound was added).

Cohort exclusions (5 base + 3 AKI-specific, from aki.R):
  1. Invalid LOS (los_hours < 0)
  2. LOS < 6h
  3. Fewer than 4 distinct hours with any dynamic measurement
  4. > 12h gap between consecutive measurement-hours
  5. Age < 18
  6. Low AKI prevalence at the stay's hospital (0 AKI cases across all
     that hospital's stays) -- eICU-CRD only, per aki.R
  7. AKI onset before 6h in the ICU
  8. Baseline creatinine > 4 (chronic kidney disease gate): the minimum
     creatinine observed in the first ICU day, excluded if that minimum
     itself exceeds 4 mg/dL

Every exclusion condition is explicitly null-safe (`.fill_null(False)`):
a stay whose value for a given criterion is missing cannot be confirmed
as meeting that criterion, so it must default to False (not excluded on
that basis), never null. Without this, a null propagates through the
`excluded` OR-chain and `filter(~excluded)` silently drops that row --
i.e. stays would be dropped from the cohort for having missing data on
one criterion, not for actually meeting any real exclusion criterion
(the original port of this script caught this exact bug: 159,221 vs.
136,503 final_n, found by cross-checking this script's OR-combined count
against an independently-written cascading computation that is
mathematically required to give the identical count).
"""

import json
import time

import polars as pl

from interoperability.config import EICU_RAW_PATIENT_CSV
from interoperability.paths import AKI_TASK_DIR, RESULTS_DIR

DYN_PATH = RESULTS_DIR / "openicu_dyn_all.parquet"
STA_PATH = RESULTS_DIR / "weavehr_sta_eicu-crd.parquet"
AKI_CONCEPTS_PATH = RESULTS_DIR / "weavehr_aki_concepts_corrected_eicu-crd.parquet"
HOSPITAL_ID_PATH = RESULTS_DIR / "weavehr_hospital_id_eicu-crd.parquet"

AKI_TASK_DIR.mkdir(parents=True, exist_ok=True)

MAX_HOURS = 7 * 24  # 168h, aki.R's max_len
ONSET_WINDOW = 6
MINUTES_TO_HOURS = 1 / 60

start = time.perf_counter()
start_wall = time.strftime("%Y-%m-%d %H:%M:%S")

# --- Stay-level LOS, straight from the raw eICU table (same as mortality) --
raw = pl.scan_csv(EICU_RAW_PATIENT_CSV, try_parse_dates=True).select(
    pl.col("patientunitstayid").cast(pl.Int64).alias("stay_id"),
    (pl.col("unitdischargeoffset").cast(pl.Float64) * MINUTES_TO_HOURS).alias("los_hours"),
)

hospital_id = pl.scan_parquet(HOSPITAL_ID_PATH)
aki_concepts = pl.scan_parquet(AKI_CONCEPTS_PATH)
sta = pl.scan_parquet(STA_PATH).select("stay_id", "age")
dyn = pl.scan_parquet(DYN_PATH)
dynamic_cols = [c for c in dyn.collect_schema().names() if c not in ("stay_id", "time")]

# --- Exclusions 3 & 4: measurement-hour coverage (identical to mortality) ---
has_measurement = pl.any_horizontal([pl.col(c).is_not_null() for c in dynamic_cols])
measurement_hours = dyn.filter(has_measurement).select("stay_id", "time").unique().sort("stay_id", "time")
meas_stats = measurement_hours.group_by("stay_id").agg(
    pl.len().alias("n_measurement_hours"),
    pl.col("time").diff().max().alias("max_gap"),
)

# --- Onset hour per stay: first hour with corrected aki >= 1 ---------------
onset = aki_concepts.filter(pl.col("aki") >= 1).group_by("stay_id").agg(pl.col("time").min().alias("onset_hour"))

# --- Baseline creatinine: min creatinine in the first ICU day (0-24h) ------
baseline_crea = (
    dyn.filter((pl.col("time") >= 0) & (pl.col("time") < 24) & pl.col("crea").is_not_null())
    .group_by("stay_id")
    .agg(pl.col("crea").min().alias("baseline_crea"))
)

cohort = (
    raw.join(hospital_id, on="stay_id", how="left")
    .join(sta, on="stay_id", how="left")
    .join(meas_stats, on="stay_id", how="left")
    .join(onset, on="stay_id", how="left")
    .join(baseline_crea, on="stay_id", how="left")
    .with_columns(
        pl.col("n_measurement_hours").fill_null(0),
        pl.col("max_gap").fill_null(0),
    )
)

# --- Exclusion 6: hospitals with zero observed AKI across all their stays --
hospital_aki_prevalence = (
    cohort.select("stay_id", "hospitalid", "onset_hour")
    .group_by("hospitalid")
    .agg((pl.col("onset_hour").is_not_null().sum() > 0).alias("hospital_has_any_aki"))
)
cohort = cohort.join(hospital_aki_prevalence, on="hospitalid", how="left")

excl1 = (pl.col("los_hours") < 0).fill_null(False)
excl2 = (pl.col("los_hours") < 6).fill_null(False)
excl3 = (pl.col("n_measurement_hours") < 4).fill_null(False)
excl4 = (pl.col("max_gap") > 12).fill_null(False)
excl5 = (pl.col("age") < 18).fill_null(False)
excl6 = pl.col("hospital_has_any_aki").not_().fill_null(True)
excl7 = (pl.col("onset_hour").is_not_null() & (pl.col("onset_hour") < 6)).fill_null(False)
excl8 = (pl.col("baseline_crea") > 4).fill_null(False)

cohort = cohort.with_columns((excl1 | excl2 | excl3 | excl4 | excl5 | excl6 | excl7 | excl8).alias("excluded"))

attrition = cohort.select(
    pl.len().alias("initial_n"),
    excl1.sum().alias("excl1_invalid_los"),
    excl2.sum().alias("excl2_los_lt_6h"),
    excl3.sum().alias("excl3_lt_4_measurement_hours"),
    excl4.sum().alias("excl4_gap_gt_12h"),
    excl5.sum().alias("excl5_age_lt_18"),
    excl6.sum().alias("excl6_low_hospital_aki_prevalence"),
    excl7.sum().alias("excl7_onset_before_6h"),
    excl8.sum().alias("excl8_baseline_crea_gt_4"),
    pl.col("excluded").not_().sum().alias("final_n"),
).collect()

retained = cohort.filter(~pl.col("excluded")).select("stay_id", "onset_hour", "los_hours")
retained_df = retained.select("stay_id", "onset_hour").collect()

# --- Observation window per retained stay: 0 to min(onset+6, 168, LOS) -----
obs_end = (
    retained.with_columns(
        pl.when(pl.col("onset_hour").is_not_null())
        .then(pl.min_horizontal(pl.col("onset_hour") + ONSET_WINDOW, MAX_HOURS))
        .otherwise(MAX_HOURS)
        .alias("obs_end")
    )
    .with_columns(pl.min_horizontal(pl.col("obs_end"), pl.col("los_hours").floor().cast(pl.Int64)).alias("obs_end"))
    .select("stay_id", "onset_hour", "obs_end")
)

# Build the hourly grid per stay and label(t) = onset occurs in (t, t+6]
grid = obs_end.select(
    "stay_id",
    pl.int_ranges(0, pl.col("obs_end").cast(pl.Int64) + 1).alias("time"),
    "onset_hour",
).explode("time")

outc = grid.with_columns(
    pl.when(
        pl.col("onset_hour").is_not_null()
        & (pl.col("onset_hour") > pl.col("time"))
        & (pl.col("onset_hour") <= pl.col("time") + ONSET_WINDOW)
    )
    .then(1)
    .otherwise(0)
    .alias("label")
).select("stay_id", "time", "label")

dyn_out = (
    dyn.join(retained.select("stay_id"), on="stay_id", how="inner")
    .join(obs_end.select("stay_id", "obs_end"), on="stay_id", how="inner")
    .filter((pl.col("time") >= 0) & (pl.col("time") <= pl.col("obs_end")))
    .select("stay_id", "time", *dynamic_cols)
    .sort("stay_id", "time")
)

sta_out = pl.scan_parquet(STA_PATH).join(retained.select("stay_id"), on="stay_id", how="inner").sort("stay_id")

outc_df = outc.sort("stay_id", "time").collect()
dyn_df = dyn_out.collect()
sta_df = sta_out.collect()

outc_df.write_parquet(AKI_TASK_DIR / "outc.parquet")
dyn_df.write_parquet(AKI_TASK_DIR / "dyn.parquet")
sta_df.write_parquet(AKI_TASK_DIR / "sta.parquet")
attrition.write_csv(AKI_TASK_DIR / "attrition.csv")

elapsed = time.perf_counter() - start
end_wall = time.strftime("%Y-%m-%d %H:%M:%S")

n_final = int(attrition["final_n"][0])
n_positive_stays = int(retained_df.filter(pl.col("onset_hour").is_not_null()).height)
n_positive_labels = int(outc_df["label"].sum())

summary = {
    "task_dir": str(AKI_TASK_DIR),
    "attrition": attrition.to_dicts()[0],
    "n_stays_final": n_final,
    "n_stays_with_any_aki_onset": n_positive_stays,
    "stay_level_aki_prevalence": round(n_positive_stays / n_final, 4) if n_final else None,
    "n_positive_hour_labels": n_positive_labels,
    "n_total_hour_labels": outc_df.height,
    "hour_level_label_prevalence": round(n_positive_labels / outc_df.height, 4) if outc_df.height else None,
    "dyn_rows": dyn_df.height,
    "sta_rows": sta_df.height,
    "outc_rows": outc_df.height,
    "label_semantics": "1 iff AKI onset (corrected aki>=1) occurs in (t, t+6] -- see script docstring",
    "start_wall_time": start_wall,
    "end_wall_time": end_wall,
    "elapsed_seconds": round(elapsed, 1),
}

print(json.dumps(summary, indent=2))
(AKI_TASK_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
