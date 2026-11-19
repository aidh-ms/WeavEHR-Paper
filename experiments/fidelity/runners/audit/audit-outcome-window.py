"""Compare old and corrected outcome windowing without writing cohorts."""

import argparse
import ast
import runpy
import sys
from pathlib import Path

import pandas as pd
import polars as pl

from src import conf
from src import cohort_utils
from src import weavehr as adapter

parser = argparse.ArgumentParser()
parser.add_argument("--task", choices=["aki", "sepsis"], required=True)
parser.add_argument("--src", required=True)
parser.add_argument(
    "--variant",
    choices=["native", "creatinine", "combined", "benchmark"],
    default="native",
)
args = parser.parse_args()

root = Path.home() / "output/yaib-cohorts"

projects = {
    "native": "weavehr-projects-final",
    "creatinine": "weavehr-projects-aki",
    "combined": "weavehr-projects-aki-combined",
    "benchmark": "weavehr-projects-aki-combined",
}

conf["weavehr_project_path"] = str(
    root / projects[args.variant] / "{src}"
)

if args.variant == "benchmark":
    path = (Path(__file__).resolve().parents[1] / "compatibility/run-aki-hirid-benchmark.py")
    tree = ast.parse(path.read_text())

    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "benchmark_aki"
    )

    module = ast.Module(body=[function], type_ignores=[])
    namespace = {"pl": pl, "pd": pd, "adapter": adapter}

    exec(compile(module, str(path), "exec"), namespace)
    adapter.OUTCOMES["aki"] = namespace["benchmark_aki"]


class AuditComplete(Exception):
    pass


def audit_window(window, outc_name="label"):
    def compare(x):
        labels = x[outc_name]
        groups = x["stay_id"]

        forward = labels.groupby(groups).ffill(limit=window)

        old = forward.bfill(limit=window).fillna(0)

        new = (
            forward.groupby(groups)
            .bfill(limit=window)
            .fillna(0)
        )

        changed = old.ne(new)

        print("\n========== WINDOWING AUDIT ==========", flush=True)
        print("Dataset:", args.src)
        print("Task:", args.task)
        print("Variant:", args.variant)
        print("Rows:", len(x))
        print("Stays:", groups.nunique())
        print("Old positives:", int((old == 1).sum()))
        print("Corrected positives:", int((new == 1).sum()))
        print("Changed labels:", int(changed.sum()))
        print("Affected stays:", groups[changed].nunique())
        print("Removed positives:", int(((old == 1) & (new == 0)).sum()))
        print("Added positives:", int(((old == 0) & (new == 1)).sum()))

        raise AuditComplete

    return compare


cohort_utils.make_outcome_windower = audit_window

script = f"{args.task}.py"
sys.argv = [script, "--src", args.src]

try:
    runpy.run_path(script, run_name="__main__")
except AuditComplete:
    print("AUDIT_COMPLETE", flush=True)
else:
    raise RuntimeError("Expected outcome window was not reached.")
