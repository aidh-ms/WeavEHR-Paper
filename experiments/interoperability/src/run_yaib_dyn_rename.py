"""Rename the eICU-CRD dynamic table to YAIB's short (ricu-style) column names.

Runs openicu-yaib's build_and_write_yaib_wide_for_dataset() (the "Step 3"
function from its example notebook) against this experiment's own WeavEHR
eICU-CRD output.

ricu_concept_dict is pointed at a real but empty JSON file: passing None
does NOT bypass the lookup the way it does in write_all_concepts_wide --
default_dataset_paths() always substitutes its own default path when given
None, and that default path doesn't exist, raising FileNotFoundError. An
empty {} file loads cleanly as empty ricu metadata.

aggregation_mode is explicitly set to "mean" (not the function's own
default, "ricu"): with an empty ricu metadata dict, aggregation_mode="ricu"
silently falls back to "median" per hour, while the wide table built by
run_yaib_wide.py uses "mean". For single-reading-per-hour labs mean==median
so this would be invisible, but for frequently-sampled vitals (heart rate,
resp rate, temperature) it would produce a real discrepancy against that
table. Forcing "mean" here keeps both tables consistent with each other.
"""

import json
import shutil
import time
from pathlib import Path

from openicu_yaib import build_and_write_yaib_wide_for_dataset, concept_root_from_output, resolve_openicu_workspace

from interoperability.paths import PROJECT_PATH, RESULTS_DIR

DATASET = "eicu-crd"
# Bundled with the repo itself (not machine-specific), found relative to
# this script's own location.
EMPTY_CONCEPT_DICT = Path(__file__).resolve().parent.parent / "empty_concept_dict.json"

WORKSPACE = resolve_openicu_workspace(PROJECT_PATH)
CONCEPT_ROOT = concept_root_from_output(PROJECT_PATH)
DATASET_OUTPUT = WORKSPACE / "yaib" / DATASET
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

print(f"weavehr_project_root = {PROJECT_PATH}")
print(f"concept_root          = {CONCEPT_ROOT}")
print(f"output_root           = {DATASET_OUTPUT}")

start_wall = time.strftime("%Y-%m-%d %H:%M:%S")
start = time.perf_counter()

result = build_and_write_yaib_wide_for_dataset(
    dataset=DATASET,
    max_hours=None,
    output_root=DATASET_OUTPUT,
    concept_root=CONCEPT_ROOT,
    icustays_csv=None,
    ricu_concept_dict=EMPTY_CONCEPT_DICT,
    aggregation_mode="mean",
)

elapsed = time.perf_counter() - start
end_wall = time.strftime("%Y-%m-%d %H:%M:%S")

n_rows = int(result.summary["n_rows"][0])
n_stays = int(result.summary["n_stays"][0])

summary = {
    "dataset": DATASET,
    "output_path": str(result.output_path),
    "n_rows": n_rows,
    "n_stays": n_stays,
    "min_time": str(result.summary["min_time"][0]),
    "max_time": str(result.summary["max_time"][0]),
    "start_wall_time": start_wall,
    "end_wall_time": end_wall,
    "elapsed_seconds": round(elapsed, 1),
    "elapsed_human": f"{elapsed / 3600:.2f} hours",
}

print(json.dumps(summary, indent=2))
(RESULTS_DIR / f"weavehr_dyn_renamed_summary_{DATASET}.json").write_text(json.dumps(summary, indent=2))

shutil.copy2(result.output_path, RESULTS_DIR / result.output_path.name)
print(f"Permanent copy stored at: {RESULTS_DIR}")
print(f"Elapsed: {summary['elapsed_human']}")
