"""Tests of experiments/fidelity/compare_fidelity.py on synthetic data only (made-up stays, hours and values)."""

import hashlib
import json
import random
from collections.abc import Mapping
from pathlib import Path

import polars as pl
import pytest

import compare_fidelity as cf
from compare_fidelity import DYNAMIC_VARS, FidelityInputError, check_consistency, concept_metrics

Values = Mapping[str, Mapping[tuple[int, int], float | None]]


def dyn(grid: dict[int, int], values: Values | None = None) -> pl.DataFrame:
    """A YAIB dyn table: buckets 0..end of each stay (grid: stay -> end), all 48 variables, null unless given."""
    keys = [(stay, hour) for stay, end in grid.items() for hour in range(end + 1)]
    values = values or {}
    data: dict[str, list] = {"stay_id": [s for s, _ in keys], "time": [t for _, t in keys]}
    data |= {c: [values.get(c, {}).get(k) for k in keys] for c in DYNAMIC_VARS}
    return pl.DataFrame(data, schema={"stay_id": pl.Int64, "time": pl.Int64} | {c: pl.Float64 for c in DYNAMIC_VARS})


def as_ricu(df: pl.DataFrame) -> pl.DataFrame:
    """As YAIB's R route writes dyn.parquet: stay_id double, time a duration (arrow duration[s], read as ms)."""
    hours = pl.duration(hours="time").cast(pl.Duration("ms")).alias("time")
    return df.with_columns(pl.col("stay_id").cast(pl.Float64), hours)


def write(root: Path, src: str, df: pl.DataFrame) -> Path:
    path = root / "los" / src / "dyn.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def compare(tmp_path: Path, ricu: pl.DataFrame, weavehr: pl.DataFrame, ricu_style: bool = True):
    write(tmp_path / "ricu", "eicu", as_ricu(ricu) if ricu_style else ricu)
    write(tmp_path / "weavehr", "eicu-crd", weavehr)
    return cf.run(tmp_path / "ricu", tmp_path / "weavehr", tmp_path / "out", ["eicu-crd"])


def row(metrics: pl.DataFrame, concept: str) -> dict:
    return metrics.filter(pl.col("concept") == concept).row(0, named=True)


def counts(r: dict) -> tuple:
    return tuple(r[c] for c in cf.METRIC_COLUMNS[2:9])


def series(*values: float | None) -> pl.Series:
    return pl.Series(values, dtype=pl.Float64)


def test_dynamic_vars_are_48_distinct_variables():
    assert len(DYNAMIC_VARS) == len(set(DYNAMIC_VARS)) == 48


def test_bucket_categories_and_metrics(tmp_path):
    hr_r = {(1, 0): 80, (1, 1): 90, (1, 2): 70}  # identical, different, ricu only
    hr_w = {(1, 0): 80, (1, 1): 91, (1, 3): 60}  # identical, different, WeavEHR only
    metrics, coverage = compare(
        tmp_path, dyn({1: 3}, {"hr": hr_r, "glu": {(1, 0): 5}}), dyn({1: 3}, {"hr": hr_w, "glu": {(1, 0): 5}})
    )
    hr = row(metrics, "hr")
    # total, something, both, identical, different, weavehr only, ricu only
    assert counts(hr) == (4, 4, 2, 1, 1, 1, 1)
    assert hr["presence_disagreement_pct"] == 50.0
    assert hr["mrd_pct"] == pytest.approx(100 * (0 + 1 / 90) / 2)
    glu = row(metrics, "glu")  # three buckets without a value in either backend count in the total only
    assert counts(glu) == (4, 1, 1, 1, 0, 0, 0)
    assert (glu["presence_disagreement_pct"], glu["mrd_pct"]) == (0.0, 0.0)
    alb = row(metrics, "alb")  # no value at all
    assert counts(alb) == (4, 0, 0, 0, 0, 0, 0)
    assert alb["presence_disagreement_pct"] is None and alb["mrd_pct"] is None
    assert coverage.row(0, named=True)["buckets_common"] == 4


def test_csv_outputs_are_aggregates_with_exact_columns(tmp_path):
    compare(tmp_path, dyn({7: 2}, {"hr": {(7, 0): 1.0}}), dyn({7: 2}))
    metrics = pl.read_csv(tmp_path / "out" / "fidelity_metrics.csv")
    coverage = pl.read_csv(tmp_path / "out" / "coverage.csv")
    assert tuple(metrics.columns) == cf.METRIC_COLUMNS
    assert tuple(coverage.columns) == cf.COVERAGE_COLUMNS
    assert metrics["concept"].to_list() == list(DYNAMIC_VARS)
    assert set(metrics["dataset"]) == {"eicu-crd"}


def test_outputs_hold_aggregates_and_provenance_only(tmp_path):
    stay, value = 987654321, 4242.4242  # must not appear in any output
    compare(tmp_path, dyn({stay: 2}, {"hr": {(stay, 1): value}}), dyn({stay: 2}, {"hr": {(stay, 1): value}}))
    out = tmp_path / "out"
    assert sorted(p.name for p in out.iterdir()) == ["coverage.csv", "fidelity_metrics.csv", "provenance.json"]
    assert not any(s in p.read_text() for p in out.iterdir() for s in (str(stay), str(value)))
    record = json.loads((out / "provenance.json").read_text())
    assert record["parameters"] == {"task": "los", "max_hour": 168, "rtol": 1e-3, "atol": 1e-6}
    inputs = record["inputs"]["eicu-crd"]
    ricu_file, weavehr_file = cf.input_paths(tmp_path / "ricu", tmp_path / "weavehr", "eicu-crd")
    assert inputs["ricu"]["sha256"] == hashlib.sha256(ricu_file.read_bytes()).hexdigest()
    assert inputs["weavehr"]["bytes"] == weavehr_file.stat().st_size
    assert (inputs["ricu"]["time_type"], inputs["weavehr"]["time_type"]) == ("Duration(time_unit='ms')", "Int64")
    assert record["script"]["sha256"] == hashlib.sha256(Path(cf.__file__).read_bytes()).hexdigest()


def test_different_stay_populations_and_grids(tmp_path):
    # stay 1: same grid; stay 2: ricu has one hour more; stay 3 only in ricu, stay 4 only in WeavEHR
    ricu = dyn({1: 3, 2: 5, 3: 2}, {"hr": {(1, 0): 1, (2, 5): 2, (3, 0): 3}})
    weavehr = dyn({1: 3, 2: 4, 4: 6}, {"hr": {(1, 0): 1, (4, 0): 4}})
    metrics, coverage = compare(tmp_path, ricu, weavehr)
    assert coverage.row(0, named=True) == {
        "dataset": "eicu-crd",
        "stays_ricu": 3,
        "stays_weavehr": 3,
        "stays_common": 2,
        "buckets_ricu": 13,
        "buckets_weavehr": 16,
        "buckets_common": 9,
        "buckets_ricu_only_shared_stays": 1,
        "buckets_weavehr_only_shared_stays": 0,
        "values_ricu_outside_common": 2,
        "values_weavehr_outside_common": 1,
    }
    assert set(metrics["buckets_total"]) == {9}
    assert counts(row(metrics, "hr")) == (9, 1, 1, 1, 0, 0, 0)  # values outside the common buckets are not compared


def test_hour_168_is_the_last_bucket(tmp_path):
    metrics, _ = compare(tmp_path, dyn({1: 168}, {"k": {(1, 168): 4.0}}), dyn({1: 168}, {"k": {(1, 168): 4.0}}))
    assert counts(row(metrics, "k")) == (169, 1, 1, 1, 0, 0, 0)


def test_numeric_hours_from_the_python_ricu_route(tmp_path):
    ricu = dyn({1: 2}, {"hr": {(1, 2): 5.0}}).with_columns(pl.col("stay_id", "time").cast(pl.Float64))
    metrics, _ = compare(tmp_path, ricu, dyn({1: 2}, {"hr": {(1, 2): 5.0}}), ricu_style=False)
    assert counts(row(metrics, "hr")) == (3, 1, 1, 1, 0, 0, 0)


def test_nan_is_missing_like_null(tmp_path):
    weavehr = dyn({1: 1}, {"hr": {(1, 0): float("nan"), (1, 1): 7.0}})
    metrics, _ = compare(tmp_path, dyn({1: 1}, {"hr": {(1, 0): 80.0, (1, 1): None}}), weavehr)
    assert counts(row(metrics, "hr")) == (2, 2, 0, 0, 0, 1, 1)


@pytest.mark.parametrize("dtype", [pl.Null, pl.Boolean, pl.String])
def test_empty_concept_outputs(tmp_path, dtype):
    weavehr = dyn({1: 2}).with_columns(pl.lit(None, dtype=dtype).alias("tnt"))
    metrics, _ = compare(tmp_path, dyn({1: 2}, {"tnt": {(1, 0): 0.1}}), weavehr)
    assert counts(row(metrics, "tnt")) == (3, 1, 0, 0, 0, 0, 1)
    assert row(metrics, "tnt")["mrd_pct"] is None


def test_zero_ricu_reference_is_excluded_from_mrd():
    res = concept_metrics(weavehr=series(0, 5, 110), ricu=series(0, 0, 100))
    assert (res["buckets_identical"], res["buckets_different"]) == (1, 2)  # zeros still count for equality
    assert res["mrd_pct"] == pytest.approx(10.0)  # only the bucket with a nonzero reference


@pytest.mark.parametrize(
    ("weavehr", "ricu"),
    [(series(1, None), series(None, 2)), (series(3), series(0)), (series(), series())],
)
def test_mrd_is_missing_without_eligible_pairs(weavehr, ricu):
    assert concept_metrics(weavehr, ricu)["mrd_pct"] is None


def test_presence_disagreement_without_observations_is_missing():
    res = concept_metrics(series(None, None), series(None, None))
    assert (res["buckets_total"], res["buckets_neither"], res["presence_disagreement_pct"]) == (2, 2, None)


@pytest.mark.parametrize(
    ("w", "r", "identical"),
    [
        (1000.0, 1001.0, True),  # |R - W| = 1 <= 1e-6 + 1e-3 * 1000
        (1000.0, 1001.01, False),
        (-1000.0, -1001.0, True),
        (0.0, 5e-7, True),  # absolute tolerance near zero
        (0.0, 2e-6, False),
        (1000.0, 1001.0005, False),  # the tolerance scales with |W|, not |R| ...
        (1001.0005, 1000.0, True),  # ... so swapping the values changes the outcome
    ],
)
def test_numerical_tolerance(w, r, identical):
    res = concept_metrics(series(w), series(r))
    assert (res["buckets_identical"], res["buckets_different"]) == ((1, 0) if identical else (0, 1))


def test_consistency_equations_on_random_data():
    rng = random.Random(0)
    for _ in range(50):
        n = rng.randrange(0, 40)
        values = [None, 0.0, 1.0, 1.0005, 2.0, -3.0]
        res = concept_metrics(series(*rng.choices(values, k=n)), series(*rng.choices(values, k=n)))
        check_consistency(res)
        c = {k: v for k, v in res.items() if k.startswith("buckets_") and isinstance(v, int)}
        assert len(c) == 8
        assert c["buckets_something"] == c["buckets_both_value"] + c["buckets_weavehr_only"] + c["buckets_ricu_only"]
        assert c["buckets_both_value"] == c["buckets_identical"] + c["buckets_different"]
        assert c["buckets_neither"] == c["buckets_total"] - c["buckets_something"] >= 0


def test_consistency_check_detects_contradictions():
    res = concept_metrics(series(1, None), series(1, 2))
    with pytest.raises(RuntimeError, match="both_value = identical"):
        check_consistency(res | {"buckets_identical": 2})


def bad_input(tmp_path, weavehr: pl.DataFrame, match: str, ricu: pl.DataFrame | None = None):
    with pytest.raises(FidelityInputError, match=match):
        compare(tmp_path, dyn({1: 2}) if ricu is None else ricu, weavehr)
    assert not (tmp_path / "out").exists()  # nothing is written when an input is invalid


def test_rejects_duplicate_buckets(tmp_path):
    bad_input(tmp_path, pl.concat([dyn({1: 2}), dyn({1: 0})]), "duplicate")


def test_rejects_missing_variable(tmp_path):
    bad_input(tmp_path, dyn({1: 2}).drop("urine"), r"missing required columns \['urine'\]")


def test_rejects_unexpected_column_but_ignores_pandas_index(tmp_path):
    bad_input(tmp_path, dyn({1: 2}).with_columns(pl.lit(1).alias("label")), "unexpected columns")
    compare(tmp_path, dyn({1: 2}), dyn({1: 2}).with_columns(pl.lit(1).alias("__index_level_0__")))


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (pl.col("hr").cast(pl.String).fill_null("high"), "expected numbers"),
        (pl.col("hr").fill_null(float("inf")), "infinite"),
        (pl.col("stay_id") + 0.5, "whole numbers"),
        (pl.col("time") + 0.5, "whole numbers"),
        (pl.col("time").cast(pl.String), "expected hours or a duration"),
        (pl.duration(minutes=pl.col("time") * 30).alias("time"), "not whole hours"),
    ],
)
def test_rejects_incompatible_schemas(tmp_path, change, match):
    bad_input(tmp_path, dyn({1: 2}).with_columns(change), match)


@pytest.mark.parametrize(
    ("weavehr", "match"),
    [
        (dyn({1: 169}), "outside hours 0..168"),
        (dyn({1: 2}).with_columns(pl.col("time") - 1), "outside hours 0..168"),
        (dyn({1: 3}).filter(pl.col("time") != 1), "not 0, 1, ..., end"),
        (dyn({1: 3}).filter(pl.col("time") != 0), "not 0, 1, ..., end"),
        (dyn({1: 0}).clear(), "no rows"),
    ],
)
def test_rejects_buckets_outside_the_yaib_grid(tmp_path, weavehr, match):
    bad_input(tmp_path, weavehr, match)


def test_rejects_outputs_without_common_buckets(tmp_path):
    bad_input(tmp_path, dyn({2: 2}), "share no")


def test_missing_input_file_and_cli(tmp_path, capsys):
    write(tmp_path / "ricu", "eicu", as_ricu(dyn({1: 2})))
    args = ["--ricu-dir", str(tmp_path / "ricu"), "--weavehr-dir", str(tmp_path / "weavehr")]
    with pytest.raises(SystemExit, match="missing input files"):
        cf.main([*args, "--output-dir", str(tmp_path / "out"), "--datasets", "eicu-crd"])
    assert not (tmp_path / "out").exists()
    write(tmp_path / "weavehr", "eicu-crd", dyn({1: 2}))
    cf.main([*args, "--output-dir", str(tmp_path / "out"), "--datasets", "eicu-crd"])
    assert (tmp_path / "out" / "fidelity_metrics.csv").is_file() and "stays_common" in capsys.readouterr().out
