import argparse
import runpy
import sys
from pathlib import Path

import polars as pl

from src import conf
from src import weavehr as adapter

parser = argparse.ArgumentParser()
parser.add_argument("--src", required=True)
args = parser.parse_args()

src = args.src
root = Path.home() / "output/yaib-cohorts"

project_group = (
    "weavehr-projects-aki"
    if src in ("hirid", "aumc")
    else "weavehr-projects-final"
)

conf["weavehr_project_path"] = str(
    root / project_group / "{src}"
)

conf["out_dir"] = str(root / "weavehr-aki-first-onset")

project = Path(
    conf["weavehr_project_path"].format(src=src)
)

assert (project / "datasets/concept/.complete").is_file()
assert not (
    Path(conf["out_dir"]) / "aki" / src
).exists()

# Isolated sensitivity experiment.
# No changes to the YAIB source files.
adapter.OUTCOMES["aki"] = lambda src, interval: adapter._events(
    src,
    "aki",
    adapter._concept(src, "aki").filter(
        pl.col("numeric_value") >= 1
    ),
    interval,
    first=True,
)

print("Source:", src, flush=True)
print("Project:", project, flush=True)
print("Output:", conf["out_dir"], flush=True)

sys.argv = ["aki.py", "--src", src]
runpy.run_path("aki.py", run_name="__main__")
