"""Compare binary YAIB outcomes and export aggregate metrics only."""

import argparse
from pathlib import Path

import polars as pl

DATASETS = {
    "eicu-crd": "eicu",
    "mimic-iv": "miiv",
    "hirid": "hirid",
    "aumc": "aumc",
}

TASKS = ("mortality24", "aki", "sepsis")


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def pct(numerator, denominator):
    return 100 * numerator / denominator if denominator else None


def load_outcome(path, task, backend):
    df = pl.read_parquet(path)

    keys = ["stay_id"] if task == "mortality24" else ["stay_id", "time"]
    required = keys + ["label"]

    if not set(required).issubset(df.columns):
        raise ValueError(f"{path}: missing required columns")

    df = df.select(required)

    if any(df.null_count().row(0)):
        raise ValueError(f"{path}: unexpected null values")

    label_dtype = df["label"].dtype

    if label_dtype == pl.Boolean:
        pass
    elif label_dtype.is_numeric():
        if not ((df["label"] == 0) | (df["label"] == 1)).all():
            raise ValueError(f"{path}: non-binary labels")
    else:
        raise ValueError(f"{path}: unsupported label dtype")

    if not df["stay_id"].dtype.is_integer():
        if not df["stay_id"].dtype.is_float():
            raise ValueError(f"{path}: unsupported stay_id dtype")
        if not (df["stay_id"].is_finite() & (df["stay_id"] == df["stay_id"].floor())).all():
            raise ValueError(f"{path}: non-integral stay IDs")

    df = df.with_columns(
        pl.col("stay_id").cast(pl.Int64),
        pl.col("label").cast(pl.Int8),
    )

    if "time" in keys:
        dtype = df.schema["time"]

        if isinstance(dtype, pl.Duration):
            micros = pl.col("time").dt.total_microseconds()
            hour = 3_600_000_000

            if df.filter(micros % hour != 0).height:
                raise ValueError(f"{path}: non-hourly times")

            df = df.with_columns((micros // hour).alias("time"))
        elif dtype.is_integer():
            df = df.with_columns(pl.col("time").cast(pl.Int64))
        elif dtype.is_float():
            if df.filter(~pl.col("time").is_finite() | (pl.col("time") != pl.col("time").floor())).height:
                raise ValueError(f"{path}: non-integral hourly times")
            df = df.with_columns(pl.col("time").cast(pl.Int64))
        else:
            raise ValueError(f"{path}: unsupported time dtype")

    if df.select(keys).unique().height != df.height:
        raise ValueError(f"{path}: duplicate keys")

    return df.rename({"label": backend}), keys


def compare(dataset, task, ricu_path, weavehr_path):
    r, keys = load_outcome(ricu_path, task, "ricu")
    w, _ = load_outcome(weavehr_path, task, "weavehr")

    r_stays = r.select("stay_id").unique()
    w_stays = w.select("stay_id").unique()

    common_stays = r_stays.join(w_stays, on="stay_id", how="inner").height

    common = r.join(w, on=keys, how="inner")

    n = common.height

    tp, tn, fp, fn = common.select(
        ((pl.col("ricu") == 1) & (pl.col("weavehr") == 1)).sum(),
        ((pl.col("ricu") == 0) & (pl.col("weavehr") == 0)).sum().alias("tn"),
        ((pl.col("ricu") == 0) & (pl.col("weavehr") == 1)).sum().alias("fp"),
        ((pl.col("ricu") == 1) & (pl.col("weavehr") == 0)).sum().alias("fn"),
    ).row(0)

    assert tp + tn + fp + fn == n

    observed = ratio(tp + tn, n)

    expected = ((tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)) / n**2 if n else None

    kappa = ratio(observed - expected, 1 - expected) if n else None

    return {
        "dataset": dataset,
        "outcome": task,
        "stays_ricu": r_stays.height,
        "stays_weavehr": w_stays.height,
        "stays_common": common_stays,
        "stays_ricu_only": r_stays.height - common_stays,
        "stays_weavehr_only": w_stays.height - common_stays,
        "stay_jaccard_pct": pct(
            common_stays,
            r_stays.height + w_stays.height - common_stays,
        ),
        "keys_ricu": r.height,
        "keys_weavehr": w.height,
        "keys_common": n,
        "keys_ricu_only": r.height - n,
        "keys_weavehr_only": w.height - n,
        "key_jaccard_pct": pct(n, r.height + w.height - n),
        "positive_ricu": r["ricu"].sum(),
        "positive_weavehr": w["weavehr"].sum(),
        "positive_ricu_common": tp + fn,
        "positive_weavehr_common": tp + fp,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "labels_agree": tp + tn,
        "labels_disagree": fp + fn,
        "agreement_pct": pct(tp + tn, n),
        "disagreement_pct": pct(fp + fn, n),
        "precision_pct": pct(tp, tp + fp),
        "recall_pct": pct(tp, tp + fn),
        "specificity_pct": pct(tn, tn + fp),
        "f1_pct": pct(2 * tp, 2 * tp + fp + fn),
        "cohens_kappa": kappa,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ricu-root", type=Path, required=True)
    parser.add_argument("--weavehr-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--ricu-variants",
        action="store_true",
        help="Use ricu-specific WeavEHR dataset variants",
    )
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(args.output)

    rows = []

    for dataset, reference in DATASETS.items():
        for task in TASKS:
            r = args.ricu_root / task / reference / "outc.parquet"
            weavehr_src = f"{dataset}-ricu" if args.ricu_variants and dataset in ("eicu-crd", "mimic-iv") else dataset
            w = args.weavehr_root / task / weavehr_src / "outc.parquet"

            if not r.exists() or not w.exists():
                print(f"SKIP: {dataset} / {task}: missing input")
                continue

            print(f"Comparing: {dataset} / {task}")
            rows.append(compare(dataset, task, r, w))

    if not rows:
        raise ValueError("No comparable outcome files found")

    results = pl.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results.write_csv(args.output)

    print(
        results.select(
            "dataset",
            "outcome",
            "stays_common",
            "keys_common",
            "agreement_pct",
            "f1_pct",
            "cohens_kappa",
        )
    )

    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
