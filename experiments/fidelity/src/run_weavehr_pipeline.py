"""Run the WeavEHR extraction + concept pipeline for eICU-CRD, as the fidelity
experiment's own input: the output this experiment compares against RICU.

Same two steps, same dataset, as the standalone sanity run that first
confirmed the current (post-migration, post-audit-fixes) WeavEHR codebase
runs to completion on real eICU-CRD data (91 concepts produced, ~7.5 minutes
on 16 CPUs). Kept here, inside the experiment, so the comparison is
reproducible end-to-end from this repo alone rather than depending on an
output directory that only exists on one machine.
"""

import json
import time

from fidelity.render_config import render_extraction_config
from weavehr import ConceptStep, ExtractionStep, WeavEHRProject

from fidelity.paths import CONFIG_DIR, PROJECT_PATH

render_extraction_config()

start = time.perf_counter()
start_wall = time.strftime("%Y-%m-%d %H:%M:%S")

with WeavEHRProject(PROJECT_PATH) as project:
    print("--- Extraction step ---")
    ExtractionStep.load(project, CONFIG_DIR / "extraction.yml").run()

    print("--- Concept step ---")
    ConceptStep.load(project, CONFIG_DIR / "concept.yml").run()

elapsed = time.perf_counter() - start
end_wall = time.strftime("%Y-%m-%d %H:%M:%S")

codes_path = PROJECT_PATH / "datasets" / "concept" / "metadata" / "codes.parquet"
summary = {
    "start_wall_time": start_wall,
    "end_wall_time": end_wall,
    "elapsed_seconds": round(elapsed, 1),
    "codes_parquet_exists": codes_path.exists(),
}
print(json.dumps(summary, indent=2))
(PROJECT_PATH.parent.parent / "run_summary.json").write_text(json.dumps(summary, indent=2))
