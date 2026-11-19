"""YAIB-compatible AKI sensitivity experiment using WeavEHR concepts."""

import argparse
import ast
import runpy
import sys
from pathlib import Path

import pandas as pd
import polars as pl

from src import conf
from src import weavehr as adapter

parser = argparse.ArgumentParser()
parser.add_argument(
    "--src",
    required=True,
    choices=["eicu-crd-ricu", "mimic-iv-ricu", "aumc"],
)
args = parser.parse_args()
src = args.src

root = Path.home() / "output/yaib-cohorts"

project = (
    "weavehr-projects-aki-combined"
    if src == "aumc"
    else "weavehr-projects-ricu-fix"
)

conf["weavehr_project_path"] = str(
    root / project / "{src}"
)

conf["out_dir"] = str(
    root / "weavehr-aki-reference-compatible-v2"
)

output = Path(conf["out_dir"]) / "aki" / src

if output.exists():
    raise FileExistsError(output)

# Reuse the successful HiRID benchmark implementation.
source = (Path(__file__).resolve().parents[1] / "compatibility/run-aki-hirid-benchmark.py")
text = source.read_text()
tree = ast.parse(text)

node = next(
    n for n in tree.body
    if isinstance(n, ast.FunctionDef)
    and n.name == "benchmark_aki"
)

function = ast.get_source_segment(text, node)

assert '    assert src == "hirid"\n' in function

function = function.replace(
    '    assert src == "hirid"\n', ""
)

start = function.index("    # HiRID records urine rate")
end = function.index("    urine = rates", start)

# Reproduce the original YAIB approximation for datasets
# recording urine amounts rather than direct urine rates.
rate_block = '''
    urine_rows = adapter._concept(
        src, "urine_output", required=True
    )

    urine_rows = (
        adapter._in_stays(urine_rows, src, interval)
        .filter(pl.col("numeric_value").is_finite())
        .sort("stay_id", "time", maintain_order=True)
    )

    gap = (
        pl.col("time")
        - pl.col("time").shift(1).over("stay_id")
        + 1
    )

    rates = (
        urine_rows.with_columns(
            (
                pl.col("numeric_value")
                / pl.when(gap.is_null() | (gap > 24))
                .then(1)
                .otherwise(gap)
            ).alias("urine_rate")
        )
        .filter(pl.col("urine_rate").is_between(0, 2000))
        .group_by("stay_id", "time")
        .agg(pl.col("urine_rate").max())
        .collect()
        .sort("stay_id", "time")
    )

'''

function = function[:start] + rate_block + function[end:]

namespace = {
    "pd": pd,
    "pl": pl,
    "adapter": adapter,
}

exec(compile(function, str(source), "exec"), namespace)

adapter.OUTCOMES["aki"] = namespace["benchmark_aki"]

print("Dataset:", src, flush=True)
print("Project:", project, flush=True)
print("Output:", output, flush=True)

sys.argv = ["aki.py", "--src", src]

runpy.run_path("aki.py", run_name="__main__")
