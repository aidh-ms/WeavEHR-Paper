"""Generate publication figures from aggregate fidelity metrics."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

DATASETS = {
    "eicu-crd": "eICU-CRD",
    "mimic-iv": "MIMIC-IV",
    "hirid": "HiRID",
    "aumc": "AUMC",
}

METRICS = {
    "value_disagreement_pct": "Value disagreement (%)",
    "presence_disagreement_pct": "Presence disagreement (%)",
    "mrd_pct": "Mean relative difference (%)",
}

THRESHOLD = 1.0


def load_metrics(root):
    frames = []

    for dataset in DATASETS:
        path = root / dataset / "fidelity_metrics.csv"
        df = pl.read_csv(path)

        if df.height != 48:
            raise ValueError(f"{dataset}: expected 48 concepts")

        if df["concept"].n_unique() != 48:
            raise ValueError(f"{dataset}: duplicate concepts")

        if set(df["dataset"].to_list()) != {dataset}:
            raise ValueError(f"{dataset}: unexpected dataset name")

        frames.append(df)

    reference = set(frames[0]["concept"].to_list())

    for df in frames[1:]:
        if set(df["concept"].to_list()) != reference:
            raise ValueError("Concept sets differ across datasets")

    df = pl.concat(frames, how="vertical_relaxed")

    df = df.with_columns(
        pl.when(pl.col("buckets_both_value") > 0)
        .then(100.0 * pl.col("buckets_different") / pl.col("buckets_both_value"))
        .otherwise(None)
        .alias("value_disagreement_pct")
    )

    df = df.with_columns([pl.when(pl.col(m).is_finite()).then(pl.col(m)).otherwise(None).alias(m) for m in METRICS])

    return df.with_columns(
        pl.when(pl.any_horizontal([pl.col(m) >= THRESHOLD for m in METRICS]).fill_null(False))
        .then(pl.lit("REVIEW"))
        .when(pl.any_horizontal([pl.col(m).is_null() for m in METRICS]))
        .then(pl.lit("UNDEFINED"))
        .otherwise(pl.lit("PASS"))
        .alias("status")
    ).sort("dataset", "concept")


def plot_heatmap(df, metric, output):
    concepts = sorted(df["concept"].unique().to_list())

    values = np.array(
        [
            [
                df.filter((pl.col("dataset") == dataset) & (pl.col("concept") == concept))[metric].item()
                for dataset in DATASETS
            ]
            for concept in concepts
        ],
        dtype=float,
    )

    colors = [
        "#e8f4ea",
        "#93c9a4",
        "#fee5a2",
        "#f5ae68",
        "#dd6954",
        "#922c40",
    ]

    boundaries = [0, 1e-12, 1, 5, 20, 50, np.inf]

    cmap = ListedColormap(colors)
    cmap.set_bad("#cccccc")
    norm = BoundaryNorm(boundaries, cmap.N)

    fig, ax = plt.subplots(figsize=(6.5, 14))

    ax.imshow(
        np.ma.masked_invalid(values),
        cmap=cmap,
        norm=norm,
        aspect="auto",
        interpolation="nearest",
    )

    ax.set_xticks(
        range(len(DATASETS)),
        list(DATASETS.values()),
    )
    ax.set_yticks(range(len(concepts)), concepts)

    ax.tick_params(
        top=True,
        bottom=False,
        labeltop=True,
        labelbottom=False,
        length=0,
    )

    for i in range(len(concepts)):
        for j in range(len(DATASETS)):
            value = values[i, j]

            if not np.isfinite(value):
                label = "NA"
            elif value == 0:
                label = "0"
            elif value < 0.01:
                label = "<0.01"
            else:
                label = f"{value:.2f}"

            ax.text(
                j,
                i,
                label,
                ha="center",
                va="center",
                fontsize=7,
                color=("white" if np.isfinite(value) and value >= 50 else "#222222"),
            )

    ax.set_title(METRICS[metric], pad=20)

    labels = [
        "Near zero",
        "<1%",
        "1–<5%",
        "5–<20%",
        "20–<50%",
        "≥50%",
        "Undefined",
    ]

    handles = [Patch(facecolor=color, label=label) for color, label in zip(colors + ["#cccccc"], labels)]

    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncol=3,
        frameon=False,
        fontsize=8,
    )

    fig.tight_layout()

    for suffix in ("pdf", "png"):
        fig.savefig(
            output / f"{metric}.{suffix}",
            dpi=300,
            bbox_inches="tight",
        )

    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    df = load_metrics(args.root)
    args.output.mkdir(parents=True, exist_ok=False)

    df.write_csv(args.output / "concept_comparison.csv")

    wide = (
        df.select("concept", "dataset", *METRICS, "status")
        .pivot(
            on="dataset",
            index="concept",
            values=[*METRICS, "status"],
        )
        .sort("concept")
    )

    wide.write_csv(args.output / "concept_comparison_wide.csv")

    summary = (
        df.group_by("dataset")
        .agg(
            pl.len().alias("concepts"),
            *[(pl.col("status") == status).sum().alias(status.lower()) for status in ("PASS", "REVIEW", "UNDEFINED")],
            *[
                (pl.col(metric) < THRESHOLD).fill_null(False).sum().alias(metric + "_below_threshold")
                for metric in METRICS
            ],
        )
        .sort("dataset")
    )

    summary.write_csv(args.output / "dataset_summary.csv")

    for metric in METRICS:
        plot_heatmap(df, metric, args.output)

    print(summary)
    print(f"Generated {df.height} comparisons")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
