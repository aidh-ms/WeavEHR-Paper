"""Sepsis reference-compatibility sensitivity experiments."""

import argparse
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
    choices=["eicu-crd-ricu", "mimic-iv-ricu"],
)
parser.add_argument(
    "--variant",
    required=True,
    choices=["first-infection", "legacy-abx"],
)
args = parser.parse_args()

if args.variant == "legacy-abx":
    assert args.src == "eicu-crd-ricu"

root = Path.home() / "output/yaib-cohorts"

conf["weavehr_project_path"] = str(
    root / "weavehr-projects-ricu-fix" / "{src}"
)

conf["out_dir"] = str(
    root / f"weavehr-sepsis-{args.variant}-v2"
)

output = Path(conf["out_dir"]) / "sepsis" / args.src

if output.exists():
    raise FileExistsError(output)


def describe(name, frame):
    print(
        name,
        frame.select(
            pl.len().alias("events"),
            pl.col("stay_id").n_unique().alias("stays"),
        ),
        flush=True,
    )


def legacy_abx(src, interval):
    files = adapter._files(
        src,
        f"concept/data/antibiotics/*/{src}/*.parquet",
    )

    if not files:
        raise FileNotFoundError("Missing antibiotics")

    rows = pl.scan_parquet(files)

    duration = (
        pl.col("coverage_end").str.to_datetime(
            time_unit="us", strict=False
        ) - pl.col("time")
    ).dt.total_seconds() / 3600

    rows = rows.with_columns(
        duration.alias("dur")
    )

    print(
        rows.select(
            pl.len().alias("events"),
            (pl.col("dur") < 0).sum().alias("negative"),
            (pl.col("dur") > 168).sum().alias("over_7d"),
            pl.col("dur").null_count().alias("null"),
        ).collect(),
        flush=True,
    )

    abx = (
        adapter._in_stays(rows, src, interval)
        .drop_nulls("dur")
        .group_by("stay_id", "time")
        .agg(pl.col("dur").max())
        .collect()
    )

    death = (
        adapter._death_icu(src, interval)
        .filter("death_icu")
        .group_by("stay_id")
        .agg(pl.col("time").min().alias("death"))
    )

    abx = (
        abx.join(death, on="stay_id", how="left")
        .filter(
            pl.col("death").is_null()
            | (pl.col("time") <= pl.col("death"))
        )
        .sort("stay_id", "time")
    )

    end = pl.min_horizontal(
        pl.col("death").first(),
        pl.col("time").first() + 72,
    )

    # Deliberately reproduce the documented legacy
    # YAIB Python approximation of ricu's unit error.
    # NOT a clinically valid duration calculation.
    covered = (
        pl.col("time") + pl.col("dur")
    ) * 3600

    gap = (
        pl.col("time").shift(-1).fill_null(end)
        - covered.cum_max()
    )

    result = (
        abx.rolling(
            "time",
            period="72i",
            offset="0i",
            closed="both",
            group_by="stay_id",
        )
        .agg(gap.max().alias("max_gap"))
        .filter(pl.col("max_gap") <= 24)
        .select("stay_id", "time")
        .unique()
        .sort("stay_id", "time")
    )

    describe("Legacy suspected infection:", result)
    return result


def benchmark_sepsis(src, interval):
    assert interval == pd.Timedelta(hours=1)

    if args.variant == "legacy-abx":
        infection = legacy_abx(src, interval)
    else:
        infection = adapter._events(
            src,
            "infection",
            adapter._concept(
                src,
                "suspected_infection",
                required=True,
            ),
            interval,
        ).select("stay_id", "time")

    first = infection.group_by("stay_id").agg(
        pl.col("time").min().alias("si")
    )

    describe("First suspected infection:", first)

    # Hourly SOFA using maximum observed score.
    sofa = (
        adapter._in_stays(
            adapter._concept(
                src, "sofa", required=True
            ),
            src,
            interval,
        )
        .join(
            first.lazy().select("stay_id"),
            on="stay_id",
            how="inner",
        )
        .filter(pl.col("numeric_value").is_finite())
        .group_by("stay_id", "time")
        .agg(pl.col("numeric_value").max().alias("sofa"))
        .collect()
        .sort("stay_id", "time")
    )

    describe("Hourly SOFA:", sofa)

    bounds = sofa.group_by("stay_id").agg(
        pl.col("time").min().alias("first_sofa"),
        pl.col("time").max().alias("last_sofa"),
    )

    # Only materialize hours inside the infection window.
    grid = (
        first.join(bounds, on="stay_id")
        .with_columns(
            pl.max_horizontal(
                pl.col("si") - 48,
                "first_sofa",
            ).alias("start"),
            pl.min_horizontal(
                pl.col("si") + 24,
                "last_sofa",
            ).alias("end"),
        )
        .filter(pl.col("start") <= pl.col("end"))
        .with_columns(
            pl.int_ranges(
                "start", pl.col("end") + 1
            ).alias("time")
        )
        .explode("time")
        .select("stay_id", "time")
        .sort("stay_id", "time")
    )

    # Carry forward only within the same ICU stay.
    scores = (
        grid.join_asof(
            sofa,
            on="time",
            by="stay_id",
            strategy="backward",
            check_sortedness=False,
        )
        .sort("stay_id", "time")
        .with_columns(
            (
                pl.col("sofa")
                - pl.col("sofa").cum_min().over("stay_id")
            ).alias("delta_sofa")
        )
    )

    result = (
        scores.filter(pl.col("delta_sofa") >= 2)
        .group_by("stay_id")
        .agg(pl.col("time").min())
        .with_columns(pl.lit(True).alias("sep3"))
        .sort("stay_id", "time")
    )

    describe("Sepsis onset:", result)
    return result


adapter.OUTCOMES["sep3"] = benchmark_sepsis

print("Dataset:", args.src, flush=True)
print("Variant:", args.variant, flush=True)
print("Output:", output, flush=True)

sys.argv = ["sepsis.py", "--src", args.src]

runpy.run_path("sepsis.py", run_name="__main__")
