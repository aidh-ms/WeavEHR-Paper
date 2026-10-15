"""Rebuild aki/aki_creatinine/aki_urine_output with correct hourly aggregation.

WeavEHR's aki/aki_creatinine/aki_urine_output concepts are continuous 0-3
KDIGO stages (a step function over time; confirmed by reading
weavehr/steps/concept/transformer/aki.py and the raw concept parquet
directly -- distinct values exactly {0.0, 1.0, 2.0, 3.0}).

The wide table built by run_yaib_wide.py aggregates every concept's
numeric_value to an hourly grid using "mean" by default (confirmed:
aki/aki_creatinine/aki_urine_output aren't in openicu-yaib's
RICU_TO_OPENICU mapping, so they always fall to the "mean" default
regardless of aggregation_mode). This produces clinically meaningless
fractional stage values (0.25, 0.333, 0.5, ...) instead of real KDIGO
stages.

KDIGO staging is a categorical severity classification (0-3), not a
continuous quantity -- averaging two stages (e.g. 1 and 2 -> 1.5) has no
defined clinical meaning, while taking the worse of two values does. The
KDIGO guideline itself applies exactly this "worse-of" rule when
combining the creatinine- and urine-output-derived stages into one overall
stage (Kellum et al. 2012, KDIGO Clinical Practice Guideline for Acute
Kidney Injury, Kidney International Supplements 2(1):1-138), and the
actual reference implementation this project validates against (fidelity
experiment) encodes it directly: YAIB-cohorts' ricu-extensions/callbacks/
callback-kdigo.R computes `kdigo := pmax(kdigo_crea, kdigo_urine, ...)` --
max, not mean. Neither source addresses the narrower question this script
actually faces (collapsing multiple sub-hourly readings of the *same*
criterion into one hourly grid value, a WeavEHR-pipeline-specific step, not
something ricu's own regularly-gridded input needs to do); this script
applies the same worse-of logic there by direct analogy, not by a
directly-citable rule for that exact scenario. Re-aggregates all three
concepts from the raw per-event concept parquet using max, reusing
openicu-yaib's own verified subject-to-stay join/windowing rather than its
ricu_meta/aggregation_mode machinery.

Deliberately format-agnostic: produces a corrected concept table usable for
an AKI cohort/label table -- it does not itself build a cohort or label.
"""

import json
import time

import polars as pl
from openicu_yaib import concept_root_from_output
from openicu_yaib.io import scan_dataset_stays, scan_openicu_subject_concept_hours
from openicu_yaib.stays import dataset_stay_spec, find_dataset_stay_file
from openicu_yaib.transform import map_subject_events_to_dataset_stays

from interoperability.paths import PROJECT_PATH, RESULTS_DIR

DATASET = "eicu-crd"
CONCEPT_ROOT = concept_root_from_output(PROJECT_PATH)
OUT_PATH = RESULTS_DIR / "weavehr_aki_concepts_corrected_eicu-crd.parquet"

CONCEPTS = ["aki", "aki_creatinine", "aki_urine_output"]

start = time.perf_counter()
start_wall = time.strftime("%Y-%m-%d %H:%M:%S")

spec = dataset_stay_spec(DATASET)
stays_path = find_dataset_stay_file(DATASET)
assert stays_path is not None, f"no stay file found for dataset {DATASET!r}"
stays = scan_dataset_stays(stays_path, spec)

tables = []
value_ranges = {}
for name in CONCEPTS:
    concept_path = CONCEPT_ROOT / name / "1.0.0" / f"{DATASET}.parquet"
    events = scan_openicu_subject_concept_hours(concept_path, numeric_scale_hours=spec.numeric_time_scale_hours)
    mapped = map_subject_events_to_dataset_stays(events, stays, filter_to_icu_window=True)
    hourly_max = (
        mapped.group_by("stay_id", "time")
        .agg(pl.col("numeric_value").max().alias(name))
        .select("stay_id", "time", name)
    )
    tables.append(hourly_max)

wide = tables[0]
for t in tables[1:]:
    wide = wide.join(t, on=["stay_id", "time"], how="full", coalesce=True)

wide = wide.select("stay_id", "time", *CONCEPTS).sort("stay_id", "time")
wide_df = wide.collect()
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
wide_df.write_parquet(OUT_PATH)

for name in CONCEPTS:
    distinct = wide_df.select(pl.col(name).drop_nulls().unique().sort()).to_series().to_list()
    value_ranges[name] = distinct

elapsed = time.perf_counter() - start
end_wall = time.strftime("%Y-%m-%d %H:%M:%S")

summary = {
    "output_path": str(OUT_PATH),
    "n_rows": wide_df.height,
    "n_stays": wide_df["stay_id"].n_unique(),
    "distinct_values_per_concept": value_ranges,
    "aggregation": "max (corrected from openicu-yaib's default mean)",
    "start_wall_time": start_wall,
    "end_wall_time": end_wall,
    "elapsed_seconds": round(elapsed, 1),
}

print(json.dumps(summary, indent=2))
(RESULTS_DIR / "weavehr_aki_concepts_corrected_summary_eicu-crd.json").write_text(json.dumps(summary, indent=2))
