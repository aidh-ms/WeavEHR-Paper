"""Synthetic tests for aggregate outcome fidelity."""

from datetime import timedelta

import polars as pl
import pytest

from compare_outcomes import compare, load_outcome


def test_mortality_comparison(tmp_path):
    r = tmp_path / "ricu.parquet"
    w = tmp_path / "weavehr.parquet"

    pl.DataFrame(
        {
            "stay_id": [1, 2, 3, 4, 5],
            "label": [1, 0, 1, 0, 1],
        }
    ).write_parquet(r)

    pl.DataFrame(
        {
            "stay_id": [1, 2, 3, 4, 6],
            "label": [1, 0, 0, 1, 1],
        }
    ).write_parquet(w)

    res = compare("synthetic", "mortality24", r, w)

    assert res["stays_common"] == 4
    assert res["stays_ricu_only"] == 1
    assert res["stays_weavehr_only"] == 1
    assert res["tp"] == 1
    assert res["tn"] == 1
    assert res["fp"] == 1
    assert res["fn"] == 1
    assert res["agreement_pct"] == 50
    assert res["f1_pct"] == 50
    assert res["cohens_kappa"] == pytest.approx(0)


def test_dynamic_boolean_duration(tmp_path):
    r = tmp_path / "ricu.parquet"
    w = tmp_path / "weavehr.parquet"

    pl.DataFrame(
        {
            "stay_id": [1, 1, 1],
            "time": [timedelta(hours=h) for h in range(3)],
            "label": [False, True, True],
        }
    ).write_parquet(r)

    pl.DataFrame(
        {
            "stay_id": [1, 1, 1],
            "time": [0, 1, 2],
            "label": [0, 1, 1],
        }
    ).write_parquet(w)

    res = compare("synthetic", "aki", r, w)

    assert res["keys_common"] == 3
    assert res["agreement_pct"] == 100
    assert res["f1_pct"] == 100
    assert res["cohens_kappa"] == pytest.approx(1)


@pytest.mark.parametrize(
    "labels",
    [
        [0, 2],
        [0, -1],
        [0.0, 0.5],
    ],
)
def test_reject_nonbinary_labels(tmp_path, labels):
    path = tmp_path / "invalid.parquet"

    pl.DataFrame(
        {
            "stay_id": [1, 2],
            "label": labels,
        }
    ).write_parquet(path)

    with pytest.raises(ValueError, match="non-binary"):
        load_outcome(path, "mortality24", "ricu")


def test_reject_duplicate_keys(tmp_path):
    path = tmp_path / "invalid.parquet"

    pl.DataFrame(
        {
            "stay_id": [1, 1],
            "label": [0, 1],
        }
    ).write_parquet(path)

    with pytest.raises(ValueError, match="duplicate"):
        load_outcome(path, "mortality24", "ricu")


def test_reject_null_labels(tmp_path):
    path = tmp_path / "invalid.parquet"

    pl.DataFrame(
        {
            "stay_id": [1, 2],
            "label": [0, None],
        }
    ).write_parquet(path)

    with pytest.raises(ValueError, match="null"):
        load_outcome(path, "mortality24", "ricu")
