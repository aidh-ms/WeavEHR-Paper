"""WeavEHR full native catalogue (one dataset per run: MIMIC-IV or eICU-CRD).

Runs the extraction step (all tables) and the concept step with every bundled
concept. Step timings are written to /output/steps.csv.
"""

import os
import time
from contextlib import contextmanager
from pathlib import Path

import yaml
from weavehr import ConceptStep, ExtractionStep, WeavEHRProject

OUT = Path("/output")
DEMO = os.environ.get("DEMO") == "1"
# WeavEHR dataset config (name, version) per benchmark dataset and demo flag.
NAME, VERSION = {
    ("mimic-iv", False): ("mimic-iv", "3.1"),
    ("mimic-iv", True): ("mimic-iv-demo", "2.2"),
    ("eicu", False): ("eicu-crd", "2.0"),
    ("eicu", True): ("eicu-demo", "2.0"),
}[os.environ["DATASET"], DEMO]

steps = (OUT / "steps.csv").open("w")
steps.write("step,seconds,status\n")


@contextmanager
def timed(step: str):
    start, status = time.perf_counter(), "error"
    try:
        yield
        status = "ok"
    finally:
        seconds = time.perf_counter() - start
        steps.write(f"{step},{seconds:.3f},{status}\n")
        steps.flush()
        print(f"[{step}] {seconds:.1f}s {status}", flush=True)


def write_config(name: str, config: dict) -> Path:
    path = OUT / "work" / f"{name}.yml"
    path.write_text(yaml.safe_dump(config))
    return path


extraction = write_config(
    "extraction",
    {
        "name": "Extraction",
        "version": "1.0.0",
        "config": {"data": [{"name": NAME, "version": VERSION, "path": "/input"}]},
    },
)
concept = write_config(
    "concept",
    {
        "name": "Concept",
        "version": "1.0.0",
        "config": {
            "extraction_step": "Extraction",
            "mapping_configs": [{"name": NAME, "version": VERSION}],
        },
    },
)

with WeavEHRProject(OUT / "data" / "project") as project:
    with timed("extraction"):
        ExtractionStep.load(project, extraction).run()
    with timed("concept"):
        ConceptStep.load(project, concept).run()
