"""Run the WeavEHR extraction + concept pipeline for eICU-CRD, as this
experiment's own input -- self-contained, same as the fidelity experiment's
copy of this script, so interoperability doesn't depend on another
experiment's output directory.
"""

import json
import time

from interoperability.render_config import render_extraction_config
from weavehr import ConceptStep, ExtractionStep, WeavEHRProject

from interoperability.paths import CONFIG_DIR, PROJECT_PATH

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
