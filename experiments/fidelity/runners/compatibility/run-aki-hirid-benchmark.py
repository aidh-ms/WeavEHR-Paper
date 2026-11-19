import argparse
import runpy
import sys
import tempfile
from pathlib import Path

import yaml

import weavehr
from weavehr import ConceptStep, WeavEHRProject
from weavehr.logging import configure_logging
from weavehr.utils.loader import auto_load_configs

from src import conf

parser = argparse.ArgumentParser()
parser.add_argument("--src", choices=["hirid", "aumc"], required=True)
args = parser.parse_args()

root = Path.home() / "output/yaib-cohorts"
src = args.src
version = {"hirid": "1.1.1", "aumc": "1.5.0"}[src]

conf["weavehr_project_path"] = str(
    root / "weavehr-projects-aki-combined/{src}"
)
conf["out_dir"] = str(root / "weavehr-aki-hirid-benchmark")

project_path = Path(
    conf["weavehr_project_path"].format(src=src)
)

assert (project_path / "datasets/extraction/.complete").is_file()
assert not (project_path / "datasets/concept/.complete").exists()
assert not (Path(conf["out_dir"]) / "aki" / src).exists()

print("WeavEHR:", weavehr.__file__, flush=True)
print("Project:", project_path, flush=True)
print("Output:", conf["out_dir"], flush=True)

assert str(Path.home() / "workspace/WeavEHR-aki/src") in str(
    Path(weavehr.__file__).resolve()
)

configure_logging(level="INFO")
auto_load_configs()

step = {
    "name": "Concept",
    "version": "1.0.0",
    "overwrite": False,
    "config": {
        "extraction_step": "Extraction",
        "mapping_configs": [
            {"name": src, "version": version}
        ],
    },
}

with tempfile.TemporaryDirectory() as tmp:
    config_path = Path(tmp) / "concept.yml"
    config_path.write_text(yaml.safe_dump(step))

    with WeavEHRProject(project_path) as project:
        ConceptStep.load(project, config_path).run()

assert (project_path / "datasets/concept/.complete").is_file()

for concept in ("aki", "aki_creatinine"):
    path = (
        project_path / "datasets/concept/data"
        / concept / "1.0.0" / src / f"{version}.parquet"
    )
    assert path.is_file(), f"Missing concept: {path}"


# YAIB/ricu compatibility experiment, not native WeavEHR KDIGO.
import polars as pl
import pandas as pd

from src import weavehr as adapter

assert src == "hirid"

rate_rows = adapter._concept(
    src, "urine_output_rate", required=True
)

print("Urine rate concept coverage:", flush=True)
print(rate_rows.select(
    pl.len().alias("events"),
    pl.col("subject_id").n_unique().alias("subjects"),
).collect(), flush=True)


def benchmark_aki(src, interval):
    assert src == "hirid"
    assert interval == pd.Timedelta(hours=1)

    def slide(frame, column, hours, aggregate):
        return frame.rolling(
            "time",
            period=f"{hours}i",
            group_by="stay_id",
            closed="right",
        ).agg(
            aggregate(pl.col(column)).alias(
                f"{column}_{hours}hr"
            )
        )

    # Creatinine staging on the YAIB stay-hour grid.
    crea = (
        adapter._load(src, "crea", interval)
        .drop_nulls("crea")
        .sort("stay_id", "time")
    )

    for hrs in (48, 168):
        crea = crea.join(
            slide(crea, "crea", hrs, pl.Expr.min),
            on=["stay_id", "time"],
        )

    c = pl.col("crea")
    c48 = pl.col("crea_48hr")
    c168 = pl.col("crea_168hr")

    kdigo_crea = crea.select(
        "stay_id",
        "time",
        pl.when(c >= 3 * c168).then(3)
        .when(
            (c >= 4)
            & ((c - c48 >= 0.3) | (c >= 1.5 * c168))
        ).then(3)
        .when(c >= 2 * c168).then(2)
        .when(c >= c48 + 0.3).then(1)
        .when(c >= 1.5 * c168).then(1)
        .otherwise(0)
        .alias("kdigo_crea"),
    )

    # HiRID records urine rate directly in mL/h.
    rates = (
        adapter._in_stays(
            adapter._concept(
                src, "urine_output_rate", required=True
            ),
            src,
            interval,
        )
        .filter(
            pl.col("numeric_value").is_between(0, 2000)
        )
        .group_by("stay_id", "time")
        .agg(
            pl.col("numeric_value").max().alias("urine_rate")
        )
        .collect()
        .sort("stay_id", "time")
    )

    urine = rates

    for hrs in (6, 12, 24):
        urine = urine.join(
            slide(rates, "urine_rate", hrs, pl.Expr.sum),
            on=["stay_id", "time"],
        )

    # Follow the original YAIB Python approximation:
    # normalize where weight is available; otherwise leave
    # the sum unchanged.
    weight = adapter._load(src, "weight", interval)

    urine = urine.join(
        weight, on="stay_id", how="left"
    ).with_columns([
        pl.when(pl.col("weight") > 0)
        .then(pl.col(col) / pl.col("weight"))
        .otherwise(pl.col(col))
        .alias(col)
        for col in (
            "urine_rate_6hr",
            "urine_rate_12hr",
            "urine_rate_24hr",
        )
    ])

    t = pl.col("time")
    u6 = pl.col("urine_rate_6hr")
    u12 = pl.col("urine_rate_12hr")
    u24 = pl.col("urine_rate_24hr")

    kdigo_urine = urine.select(
        "stay_id",
        "time",
        pl.when((t >= 24) & (u24 < 0.3)).then(3)
        .when((t >= 12) & (u12 == 0)).then(3)
        .when((t >= 12) & (u12 < 0.5)).then(2)
        .when((t >= 6) & (u6 < 0.5)).then(1)
        .otherwise(0)
        .alias("kdigo_urine"),
    )

    for component, col in (
        (kdigo_crea, "kdigo_crea"),
        (kdigo_urine, "kdigo_urine"),
    ):
        print(col, flush=True)
        print(component.group_by(col).agg(
            pl.len().alias("events"),
            pl.col("stay_id").n_unique().alias("stays"),
        ).sort(col), flush=True)

    kdigo = kdigo_crea.join(
        kdigo_urine,
        on=["stay_id", "time"],
        how="full",
        coalesce=True,
    )

    return (
        kdigo.filter(
            pl.max_horizontal("kdigo_crea", "kdigo_urine") >= 1
        )
        .select("stay_id", "time", pl.lit(True).alias("aki"))
        .sort("stay_id", "time")
    )


adapter.OUTCOMES["aki"] = benchmark_aki

sys.argv = ["aki.py", "--src", src]
runpy.run_path("aki.py", run_name="__main__")
