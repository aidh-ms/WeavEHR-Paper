"""Evaluate native outcome algorithms after range filtering."""

import argparse
import runpy
import sys
from pathlib import Path

from src import conf

parser = argparse.ArgumentParser()

parser.add_argument(
    "--src",
    required=True,
    choices=["eicu-crd-ricu", "mimic-iv-ricu"],
)

parser.add_argument(
    "--task",
    required=True,
    choices=["aki", "sepsis"],
)

args = parser.parse_args()

root = Path.home() / "output/yaib-cohorts"

project = root / "weavehr-projects-ricu-fix" / args.src
output = root / "weavehr-native-outcomes-v2"

assert (project / "datasets/concept/.complete").is_file()

conf["weavehr_project_path"] = str(
    root / "weavehr-projects-ricu-fix/{src}"
)

conf["out_dir"] = str(output)

target = output / args.task / args.src

if target.exists():
    raise FileExistsError(target)

print("Dataset:", args.src, flush=True)
print("Task:", args.task, flush=True)
print("Project:", project, flush=True)
print("Output:", target, flush=True)

sys.argv = [f"{args.task}.py", "--src", args.src]

runpy.run_path(f"{args.task}.py", run_name="__main__")

assert target.is_dir()

print("OUTCOME_COMPLETE:", args.task, args.src, flush=True)
