"""Build the YAIB static table (age, sex, height, weight) for eICU-CRD.

age/height/weight come from the wide table (openicu_all_concepts_wide.parquet,
run_yaib_wide.py) -- they're numeric and populated there.

sex does NOT work from that source or from WeavEHR's own patient_sex concept
file: WeavEHR stores that concept's value in text_value ("GENDER//Female"/
"GENDER//Male"), and openicu-yaib's wide-table builder only extracts
numeric_value, so patient_sex is silently all-null in every wide-table
output.

Read directly from the raw eICU-CRD patient.csv.gz table instead (the same
file openicu-yaib's own pipeline uses to resolve stay_id for age/height/
weight), which has patientunitstayid and gender in the same row -- no
subject_id/stay_id space mismatch possible (WeavEHR's subject_id for
eICU-CRD is patienthealthsystemstayid, the *hospital* stay, not
patientunitstayid, the *ICU* stay used as stay_id everywhere else;
confirmed via openicu_yaib.stays.dataset_stay_spec("eicu-crd")). Encoded
1=Male / 0=Female; "Other"/"Unknown"/blank left null and reported
explicitly rather than guessed.

Static values are constant per stay in the underlying data but repeated
across every hourly row in the wide table, so age/height/weight are reduced
with a per-stay "first non-null".
"""

import json
import time

import polars as pl

from interoperability.config import EICU_RAW_PATIENT_CSV
from interoperability.paths import RESULTS_DIR

WIDE_PATH = RESULTS_DIR / "openicu_all_concepts_wide.parquet"
OUT_PATH = RESULTS_DIR / "weavehr_sta_eicu-crd.parquet"

start = time.perf_counter()
start_wall = time.strftime("%Y-%m-%d %H:%M:%S")

wide = pl.scan_parquet(WIDE_PATH)
numeric_static = wide.group_by("stay_id").agg(
    pl.col("patient_age").drop_nulls().first().alias("age"),
    pl.col("patient_height").drop_nulls().first().alias("height"),
    pl.col("patient_weight").drop_nulls().first().alias("weight"),
)

raw_patient = pl.scan_csv(EICU_RAW_PATIENT_CSV, try_parse_dates=True).select("patientunitstayid", "gender")
sex_by_stay = raw_patient.select(
    pl.col("patientunitstayid").cast(pl.Int64).alias("stay_id"),
    pl.when(pl.col("gender") == "Male").then(1).when(pl.col("gender") == "Female").then(0).otherwise(None).alias("sex"),
)
unrecognized = raw_patient.filter(~pl.col("gender").is_in(["Male", "Female"])).select("gender").unique().collect()

static = (
    numeric_static.join(sex_by_stay, on="stay_id", how="left")
    .select("stay_id", "age", "sex", "height", "weight")
    .sort("stay_id")
    .collect()
)

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
static.write_parquet(OUT_PATH)

elapsed = time.perf_counter() - start
end_wall = time.strftime("%Y-%m-%d %H:%M:%S")

n_stays = static.height
counts = {c: int(static.select(pl.col(c).is_not_null().sum()).item()) for c in ["age", "sex", "height", "weight"]}

summary = {
    "output_path": str(OUT_PATH),
    "n_stays": n_stays,
    "non_null_counts": counts,
    "unrecognized_gender_values": unrecognized["gender"].to_list(),
    "start_wall_time": start_wall,
    "end_wall_time": end_wall,
    "elapsed_seconds": round(elapsed, 1),
}

print(json.dumps(summary, indent=2))
(RESULTS_DIR / "weavehr_sta_summary_eicu-crd.json").write_text(json.dumps(summary, indent=2))
