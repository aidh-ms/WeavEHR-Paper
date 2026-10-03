"""reprodICU full native catalogue (one dataset per run: MIMIC-IV or eICU-CRD).

Runs the same steps as reprodICU's build_all() (one timed step each).
reprodICU writes Parquet copies of large tables next to the source files, so it
gets a symlinked copy of the (read-only) input under /output/work. In demo mode
reprodICU expects uncompressed CSVs, so the demo files are gunzipped into that
copy instead. Step timings go to /output/steps.csv.

The magic concepts (build_magic_concepts) are not run: they set up the paths of
all seven reprodICU datasets and fail unless every one of them is present.
"""

import gzip
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

import yaml

OUT = Path("/output")
DEMO = os.environ.get("DEMO") == "1"
DATASET = os.environ["DATASET"]
REPRODICU_DATASET = {"mimic-iv": "MIMIC4", "eicu": "eICU"}[DATASET]
SOURCE = f"{OUT}/work/{DATASET}/"

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


def gunzip_or_link(src: str, dst: str) -> None:
    if DEMO and src.endswith(".gz"):
        with gzip.open(src) as fin, open(dst.removesuffix(".gz"), "wb") as fout:
            shutil.copyfileobj(fin, fout)
    else:
        os.symlink(src, dst)


shutil.copytree("/input", SOURCE, copy_function=gunzip_or_link)
# MIMIC-IV paths require a notes directory to exist; notes are not built here.
(OUT / "work" / "mimic-iv-note").mkdir(parents=True)

# reprodICU reads its paths from ~/.reprodICU/PATHS.yaml (HOME=/tmp).
# Paths are concatenated as strings, so the trailing slashes are required.
# Only the paths of the selected dataset are used.
paths_file = Path.home() / ".reprodICU" / "PATHS.yaml"
paths_file.parent.mkdir(parents=True, exist_ok=True)
paths_file.write_text(
    yaml.safe_dump(
        {
            "reprodICU_files_path": f"{OUT}/data/reprodICU/",
            "reprodICU_demo_files_path": f"{OUT}/data/reproDEMO/",
            "OMOP_vocab_path": f"{OUT}/work/omop/",  # only needed for OMOP export
            "mimic4_source_path": SOURCE,
            "mimic4_demo_source_path": SOURCE,
            "mimic4_notes_source_path": f"{OUT}/work/mimic-iv-note/",
            "eicu_source_path": SOURCE,
            "eicu_demo_source_path": SOURCE,
        }
    )
)

from reprodICU import build  # noqa: E402
from reprodICU.config import get_config_manager, reprodICUPaths  # noqa: E402

paths = reprodICUPaths(get_config_manager())
kwargs = {"paths": paths, "datasets": [REPRODICU_DATASET], "demo": DEMO}

with timed("patient_information"):
    build.build_patient_information(**kwargs, winsorize=False, add_availability=False)
with timed("diagnoses"):
    build.build_diagnoses(**kwargs)
with timed("procedures"):
    build.build_procedures(**kwargs)
with timed("medications"):
    build.build_medications(**kwargs)
with timed("timeseries"):
    build.build_timeseries(**kwargs, timeseries=None, winsorize=False, impute=False, resample=None)
with timed("patient_information_availability"):
    build.add_patient_information_availability(paths=paths, demo=DEMO, impute=False)
with timed("overview"):
    build.build_overview(paths=paths, demo=DEMO)
