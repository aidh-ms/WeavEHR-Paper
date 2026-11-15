"""Concept fidelity of WeavEHR against ricu on the 48 dynamic YAIB variables.

Read-only comparison of existing YAIB-cohorts outputs: reads the `los/<src>/dyn.parquet` file of the ricu and of
the WeavEHR backend for each dataset, aligns them by ICU stay and hourly bucket, and writes aggregated metrics per
dataset and concept. Nothing is filtered, repaired or recomputed; see README.md for the method.

    python compare_fidelity.py --ricu-dir RICU_OUT_DIR --weavehr-dir WEAVEHR_OUT_DIR --output-dir results

Outputs contain aggregate counts and run metadata (versions, input file hashes) only, never stay IDs, times or
values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

# The `dynamic_vars` of every YAIB-cohorts task script (e.g. Python/los.py and R/los.R).
DYNAMIC_VARS: tuple[str, ...] = (
    "alb", "alp", "alt", "ast", "be", "bicar", "bili", "bili_dir",
    "bnd", "bun", "ca", "cai", "ck", "ckmb", "cl", "crea", "crp",
    "dbp", "fgn", "fio2", "glu", "hgb", "hr", "inr_pt", "k", "lact",
    "lymph", "map", "mch", "mchc", "mcv", "methb", "mg", "na", "neut",
    "o2sat", "pco2", "ph", "phos", "plt", "po2", "ptt", "resp", "sbp",
    "temp", "tnt", "urine", "wbc",
)  # fmt: skip

# dataset -> (`--src` of the ricu route, `--src` of the WeavEHR route of YAIB-cohorts)
DATASETS: dict[str, tuple[str, str]] = {
    "eicu-crd": ("eicu", "eicu-crd"),
    "mimic-iv": ("miiv", "mimic-iv"),
    "hirid": ("hirid", "hirid"),
    "aumc": ("aumc", "aumc"),
    "eicu-demo": ("eicu_demo", "eicu-demo"),  # public demo, for a smoke test only
}
PAPER_DATASETS = ("eicu-crd", "mimic-iv", "hirid", "aumc")

# The YAIB task whose dyn.parquet holds hours 0..min(floor(LOS), 168) of every stay of its cohort.
TASK = "los"
MAX_HOUR = 168
# Bucket-level equality of weavehr-yaib's cohort_comparison: |R - W| <= ATOL + RTOL * |W|
RTOL, ATOL = 1e-3, 1e-6

KEYS = ("stay_id", "time")
HOUR_US = 3_600_000_000
PANDAS_INDEX = re.compile(r"__index_level_\d+__")  # row index that pandas may write; not data

METRIC_COLUMNS = (
    "dataset",
    "concept",
    "buckets_total",
    "buckets_something",
    "buckets_both_value",
    "buckets_identical",
    "buckets_different",
    "buckets_weavehr_only",
    "buckets_ricu_only",
    "presence_disagreement_pct",
    "mrd_pct",
)
COVERAGE_COLUMNS = (
    "dataset",
    "stays_ricu",
    "stays_weavehr",
    "stays_common",
    "buckets_ricu",
    "buckets_weavehr",
    "buckets_common",
    "buckets_ricu_only_shared_stays",
    "buckets_weavehr_only_shared_stays",
    "values_ricu_outside_common",
    "values_weavehr_outside_common",
)
PCT_COLUMNS = ("presence_disagreement_pct", "mrd_pct")


def _schema(columns: Sequence[str]) -> dict[str, type[pl.DataType]]:
    return {
        c: pl.String if c in ("dataset", "concept") else pl.Float64 if c in PCT_COLUMNS else pl.Int64 for c in columns
    }


class FidelityInputError(ValueError):
    """An input that cannot be compared as it is."""


def _check_columns(path: Path) -> None:
    if not path.is_file():
        raise FidelityInputError(f"{path}: file not found")
    columns = pl.scan_parquet(path).collect_schema().names()
    missing = [c for c in (*KEYS, *DYNAMIC_VARS) if c not in columns]
    if missing:
        raise FidelityInputError(f"{path}: missing required columns {missing}")
    extra = [c for c in columns if c not in KEYS and c not in DYNAMIC_VARS and not PANDAS_INDEX.fullmatch(c)]
    if extra:
        raise FidelityInputError(f"{path}: unexpected columns {extra}; expected stay_id, time and the 48 variables")


def _integral(s: pl.Series, path: Path, what: str) -> pl.Series:
    if s.null_count():
        raise FidelityInputError(f"{path}: {s.null_count()} missing {what}")
    if s.dtype.is_integer():
        return s.cast(pl.Int64)
    if s.dtype.is_float() and (s.is_finite() & (s == s.floor())).all():
        return s.cast(pl.Int64)
    raise FidelityInputError(f"{path}: {what} must be whole numbers, got {s.dtype} with non-integral values")


def _hours(time: pl.Series, path: Path) -> pl.Series:
    """Hourly bucket index; ricu's R route writes `time` as a duration, the Python routes as numbers of hours."""
    if isinstance(time.dtype, pl.Duration):
        if time.null_count():
            raise FidelityInputError(f"{path}: {time.null_count()} missing times")
        us = time.dt.total_microseconds()
        if (us % HOUR_US != 0).any():
            raise FidelityInputError(f"{path}: times are not whole hours; expected hourly YAIB buckets")
        return us // HOUR_US
    if time.dtype.is_numeric():
        return _integral(time, path, "times (hourly buckets)")
    raise FidelityInputError(f"{path}: time has type {time.dtype}; expected hours or a duration")


def read_keys(path: Path) -> pl.DataFrame:
    """Validated `(stay_id, time)` buckets of a dyn.parquet file, in file order."""
    _check_columns(path)
    raw = pl.read_parquet(path, columns=list(KEYS))
    keys = pl.DataFrame(
        [_integral(raw["stay_id"], path, "stay IDs").alias("stay_id"), _hours(raw["time"], path).alias("time")]
    )
    if keys.height == 0:
        raise FidelityInputError(f"{path}: no rows")
    outside = keys.filter((pl.col("time") < 0) | (pl.col("time") > MAX_HOUR)).height
    if outside:
        raise FidelityInputError(f"{path}: {outside} rows outside hours 0..{MAX_HOUR}; expected a YAIB {TASK} output")
    duplicates = keys.height - keys.n_unique()
    if duplicates:
        raise FidelityInputError(f"{path}: {duplicates} duplicate (stay_id, time) buckets")
    grids = keys.group_by("stay_id").agg(
        pl.col("time").min().alias("first"), pl.col("time").max().alias("last"), pl.len().alias("n")
    )
    gaps = grids.filter((pl.col("first") != 0) | (pl.col("n") != pl.col("last") + 1)).height
    if gaps:
        raise FidelityInputError(f"{path}: {gaps} stays whose buckets are not 0, 1, ..., end; expected YAIB's grid")
    return keys


def read_values(path: Path, concept: str) -> pl.Series:
    """One variable as Float64 in file order; null (and NaN, pandas' missing value) is missing."""
    s = pl.read_parquet(path, columns=[concept])[concept]
    if s.dtype.is_numeric():
        s = s.cast(pl.Float64).fill_nan(None)
        if s.is_infinite().any():
            raise FidelityInputError(f"{path}: {concept} has infinite values")
        return s
    if s.null_count() == s.len():  # an empty concept, e.g. an all-NA logical column written by R
        return s.cast(pl.Float64)
    raise FidelityInputError(f"{path}: {concept} has type {s.dtype} with non-missing values; expected numbers")


def concept_metrics(weavehr: pl.Series, ricu: pl.Series) -> dict[str, int | float | None]:
    """Metrics of one concept on aligned buckets (same length and order; null = no value)."""
    if weavehr.len() != ricu.len():
        raise ValueError("weavehr and ricu must hold the same buckets")
    w_val, r_val = pl.col("w").is_not_null(), pl.col("r").is_not_null()
    both = w_val & r_val
    equal = ((pl.col("r") - pl.col("w")).abs() <= ATOL + RTOL * pl.col("w").abs()).fill_null(False)
    rel_diff = (pl.col("w") - pl.col("r")).abs() / pl.col("r").abs()
    res = (
        pl.DataFrame({"w": weavehr.cast(pl.Float64), "r": ricu.cast(pl.Float64)})
        .select(
            pl.len().alias("buckets_total"),
            (w_val | r_val).sum().alias("buckets_something"),
            both.sum().alias("buckets_both_value"),
            (both & equal).sum().alias("buckets_identical"),
            (both & ~equal).sum().alias("buckets_different"),
            (w_val & ~r_val).sum().alias("buckets_weavehr_only"),
            (~w_val & r_val).sum().alias("buckets_ricu_only"),
            (~w_val & ~r_val).sum().alias("buckets_neither"),
            rel_diff.filter(both & (pl.col("r") != 0)).mean().alias("mrd"),
        )
        .row(0, named=True)
    )
    something, mrd = res["buckets_something"], res.pop("mrd")
    res["presence_disagreement_pct"] = (
        100 * (res["buckets_weavehr_only"] + res["buckets_ricu_only"]) / something if something else None
    )
    res["mrd_pct"] = None if mrd is None else 100 * mrd
    return res


def check_consistency(row: dict) -> None:
    """Raise if the bucket counts of one concept contradict each other."""
    failed = [
        name
        for name, ok in {
            "something = both_value + weavehr_only + ricu_only": row["buckets_something"]
            == row["buckets_both_value"] + row["buckets_weavehr_only"] + row["buckets_ricu_only"],
            "total >= something": row["buckets_total"] >= row["buckets_something"],
            "both_value = identical + different": row["buckets_both_value"]
            == row["buckets_identical"] + row["buckets_different"],
            "neither = total - something": row["buckets_neither"] == row["buckets_total"] - row["buckets_something"],
        }.items()
        if not ok
    ]
    if failed:
        raise RuntimeError(f"inconsistent counts for {row.get('dataset')}/{row.get('concept')}: {failed}")


def compare_dataset(dataset: str, ricu_path: Path, weavehr_path: Path) -> tuple[list[dict], dict]:
    """Metric rows (one per concept) and stay/bucket coverage of one dataset."""
    ricu = read_keys(ricu_path).with_row_index("ricu_row")
    weavehr = read_keys(weavehr_path).with_row_index("weavehr_row")
    # Comparison universe: the buckets defined in both grids, i.e. of the stays in both cohorts.
    common = ricu.join(weavehr, on=KEYS, how="inner")
    if common.height == 0:
        raise FidelityInputError(f"{dataset}: the two outputs share no (stay_id, time) bucket; stay IDs not comparable")
    shared = ricu.select("stay_id").unique().join(weavehr.select("stay_id").unique(), on="stay_id")

    def grid_only(keys: pl.DataFrame, other: pl.DataFrame) -> int:
        return keys.join(shared, on="stay_id", how="semi").join(other, on=KEYS, how="anti").height

    coverage = {
        "dataset": dataset,
        "stays_ricu": ricu["stay_id"].n_unique(),
        "stays_weavehr": weavehr["stay_id"].n_unique(),
        "stays_common": shared.height,
        "buckets_ricu": ricu.height,
        "buckets_weavehr": weavehr.height,
        "buckets_common": common.height,
        "buckets_ricu_only_shared_stays": grid_only(ricu, weavehr),
        "buckets_weavehr_only_shared_stays": grid_only(weavehr, ricu),
    }

    def n_values(s: pl.Series) -> int:
        return s.len() - s.null_count()

    rows, ricu_outside, weavehr_outside = [], 0, 0
    for concept in DYNAMIC_VARS:
        r_all, w_all = read_values(ricu_path, concept), read_values(weavehr_path, concept)
        r, w = r_all.gather(common["ricu_row"]), w_all.gather(common["weavehr_row"])
        ricu_outside += n_values(r_all) - n_values(r)  # values in buckets outside the comparison universe
        weavehr_outside += n_values(w_all) - n_values(w)
        row = {"dataset": dataset, "concept": concept, **concept_metrics(w, r)}
        check_consistency(row)
        rows.append(row)
    if [row["concept"] for row in rows] != list(DYNAMIC_VARS):
        raise RuntimeError(f"{dataset}: not all 48 dynamic variables were compared")
    coverage |= {"values_ricu_outside_common": ricu_outside, "values_weavehr_outside_common": weavehr_outside}
    return rows, coverage


def input_paths(ricu_dir: Path, weavehr_dir: Path, dataset: str) -> tuple[Path, Path]:
    ricu_src, weavehr_src = DATASETS[dataset]
    return ricu_dir / TASK / ricu_src / "dyn.parquet", weavehr_dir / TASK / weavehr_src / "dyn.parquet"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str | None:
    """Output of a git command in this script's repository, or None outside a git checkout."""
    try:
        res = subprocess.run(["git", *args], cwd=Path(__file__).parent, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return res.stdout.strip()


def _input_record(path: Path) -> dict[str, object]:
    schema = pl.scan_parquet(path).collect_schema()
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "stay_id_type": str(schema["stay_id"]),
        "time_type": str(schema["time"]),
    }


def provenance(paths: dict[str, tuple[Path, Path]]) -> dict[str, object]:
    """What a run was computed from and with: the input files (by hash) and this script's versions; no data.

    The versions of the upstream pipelines that produced the inputs are recorded separately (see README.md).
    """
    status = _git("status", "--porcelain", "--", ".")
    return {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "script": {
            "sha256": _sha256(Path(__file__)),
            "git_commit": _git("rev-parse", "HEAD"),
            "git_uncommitted_changes": None if status is None else bool(status),
        },
        "python": platform.python_version(),
        "polars": pl.__version__,
        "parameters": {"task": TASK, "max_hour": MAX_HOUR, "rtol": RTOL, "atol": ATOL},
        "inputs": {d: {"ricu": _input_record(r), "weavehr": _input_record(w)} for d, (r, w) in paths.items()},
    }


def run(
    ricu_dir: Path, weavehr_dir: Path, output_dir: Path, datasets: Sequence[str] = PAPER_DATASETS
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Compare all `datasets` and write fidelity_metrics.csv, coverage.csv and provenance.json to `output_dir`.

    All inputs are checked before anything is written; any invalid input aborts the run without output.
    """
    datasets = list(dict.fromkeys(datasets))
    unknown = [d for d in datasets if d not in DATASETS]
    if unknown:
        raise FidelityInputError(f"unknown datasets {unknown}; known: {list(DATASETS)}")
    paths = {d: input_paths(ricu_dir, weavehr_dir, d) for d in datasets}
    missing = [str(p) for pair in paths.values() for p in pair if not p.is_file()]
    if missing:
        raise FidelityInputError(f"missing input files {missing}; run the YAIB los task first or restrict --datasets")
    metrics, coverage = [], []
    for dataset, (ricu_path, weavehr_path) in paths.items():
        rows, cov = compare_dataset(dataset, ricu_path, weavehr_path)
        metrics += rows
        coverage.append(cov)
    metrics_df = pl.DataFrame([{c: r[c] for c in METRIC_COLUMNS} for r in metrics], schema=_schema(METRIC_COLUMNS))
    coverage_df = pl.DataFrame(coverage, schema=_schema(COVERAGE_COLUMNS))
    record = provenance(paths)
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_df.write_csv(output_dir / "fidelity_metrics.csv")
    coverage_df.write_csv(output_dir / "coverage.csv")
    (output_dir / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    return metrics_df, coverage_df


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Concept fidelity of WeavEHR against ricu (YAIB-cohorts los outputs).")
    parser.add_argument("--ricu-dir", type=Path, required=True, help="YAIB-cohorts out_dir of the ricu run")
    parser.add_argument("--weavehr-dir", type=Path, required=True, help="YAIB-cohorts out_dir of the WeavEHR run")
    parser.add_argument("--output-dir", type=Path, required=True, help="directory for the aggregated CSV files")
    parser.add_argument("--datasets", nargs="+", default=list(PAPER_DATASETS), choices=list(DATASETS))
    args = parser.parse_args(argv)
    try:
        _, coverage = run(args.ricu_dir, args.weavehr_dir, args.output_dir, args.datasets)
    except FidelityInputError as e:
        sys.exit(f"error: {e}")
    with pl.Config(tbl_rows=-1, tbl_cols=-1, tbl_width_chars=200):
        print(coverage)
    print(f"Wrote fidelity_metrics.csv, coverage.csv and provenance.json to {args.output_dir}")


if __name__ == "__main__":
    main()
