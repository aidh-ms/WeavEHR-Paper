"""Convert the completed WeavEHR eICU-CRD output into a YAIB-wide parquet.

Runs write_all_concepts_wide() (openicu-yaib, Step 1 of its 5-step
workflow) against this experiment's own WeavEHR output. Pure Python/Polars
-- no R, no conda, independent of the YAIB-cohorts/RICU environment work
done in the fidelity experiment.
"""

import json
import shutil
import time

from openicu_yaib import concept_root_from_output, resolve_openicu_workspace, write_all_concepts_wide

from interoperability.paths import PROJECT_PATH, RESULTS_DIR

DATASET = "eicu-crd"

WORKSPACE = resolve_openicu_workspace(PROJECT_PATH)
CONCEPT_ROOT = concept_root_from_output(PROJECT_PATH)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

print(f"weavehr_project_root = {PROJECT_PATH}")
print(f"workspace             = {WORKSPACE}")
print(f"concept_root          = {CONCEPT_ROOT}")

start_wall = time.strftime("%Y-%m-%d %H:%M:%S")
start = time.perf_counter()

result = write_all_concepts_wide(
    dataset=DATASET,
    openicu_output=PROJECT_PATH,
    concept_root=CONCEPT_ROOT,
    stays_path=None,
    max_hours=None,
    ricu_concept_dict=None,
)

elapsed = time.perf_counter() - start
end_wall = time.strftime("%Y-%m-%d %H:%M:%S")

summary = {
    "dataset": DATASET,
    "output_path": str(result.output_path),
    "manifest_path": str(result.manifest_path),
    "n_concepts": len(result.concepts),
    "concepts": list(result.concepts),
    "n_rows": result.n_rows,
    "n_stays": result.n_stays,
    "start_wall_time": start_wall,
    "end_wall_time": end_wall,
    "elapsed_seconds": round(elapsed, 1),
}

print(json.dumps(summary, indent=2))
(RESULTS_DIR / f"weavehr_all_concepts_wide_summary_{DATASET}.json").write_text(json.dumps(summary, indent=2))

# Permanent copy in this experiment's own results/ (outside any workspace a
# future WeavEHR rerun could overwrite); downstream scripts (static, dyn
# rename comparisons) read it from here under its openicu-yaib-given name.
shutil.copy2(result.output_path, RESULTS_DIR / result.output_path.name)
shutil.copy2(result.manifest_path, RESULTS_DIR / result.manifest_path.name)
print(f"Permanent copy stored at: {RESULTS_DIR}")
