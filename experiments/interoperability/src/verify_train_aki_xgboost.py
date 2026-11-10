"""Independently verify a YAIB AKI/XGBoost training run's reported metrics.

Recomputes mean/std/95% CI for AUC and PR directly from the 25 individual
repetition_*/fold_*/test_metrics.json files YAIB writes per fold, using the
exact same formula YAIB itself uses (icu_benchmarks/run_utils.py:
aggregate_results, a t-distribution CI via scipy.stats.t.interval) -- not a
different method, since deviating from YAIB's own stated aggregation would
make disagreement meaningless. Then asserts the result matches YAIB's own
accumulated_test_metrics.json for the same run, exactly as
verify_aki_eicu.py cross-checks the cohort/label table against
independently-rebuilt logic rather than trusting either computation alone.

Also checks, per fold, that every repetition has exactly 5 folds and no run
failed silently (a missing test_metrics.json), and plots per-fold AUC/PR
grouped by repetition -- the same kind of visual that caught a Logistic
Regression anomaly in the author's prior OpenICU-based run (identical
metrics repeated within a repetition is visible immediately in a plot,
easy to miss by eye in a JSON dump).

Usage: `python verify_train_aki_xgboost.py [run_dir]`. With no argument,
uses the most recently modified XGBClassifier run directory under
aki_training_logs (matches either the untuned run or a --tune run,
whichever is being checked).
"""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl
from scipy import stats

from interoperability.paths import AKI_TRAINING_LOGS_DIR

TRAINING_LOGS_ROOTS = [AKI_TRAINING_LOGS_DIR]


def find_latest_run_dir() -> Path:
    candidates = [
        d
        for root in TRAINING_LOGS_ROOTS
        if root.exists()
        for d in root.glob("eicu-crd/AKI/XGBClassifier/*")
        if d.is_dir()
    ]
    if not candidates:
        raise SystemExit(f"No XGBClassifier run directories found under {TRAINING_LOGS_ROOTS}")
    return max(candidates, key=lambda d: d.stat().st_mtime)


def load_fold_metrics(run_dir: Path) -> pl.DataFrame:
    rows = []
    for rep_dir in sorted(run_dir.glob("repetition_*")):
        rep = int(rep_dir.name.removeprefix("repetition_"))
        fold_dirs = sorted(rep_dir.glob("fold_*"))
        assert len(fold_dirs) == 5, f"{rep_dir} has {len(fold_dirs)} folds, expected 5"
        for fold_dir in fold_dirs:
            fold = int(fold_dir.name.removeprefix("fold_"))
            metrics_path = fold_dir / "test_metrics.json"
            assert metrics_path.exists(), f"missing {metrics_path} -- a fold failed silently"
            metrics = json.loads(metrics_path.read_text())
            rows.append({"repetition": rep, "fold": fold, "AUC": metrics["AUC"], "PR": metrics["PR"]})
    df = pl.DataFrame(rows)
    assert df.height == 25, f"expected 25 fold results (5 reps x 5 folds), found {df.height}"
    return df


def t_interval_95(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    sem = stats.sem(values)
    return stats.t.interval(0.95, len(values) - 1, loc=mean, scale=sem)


def main() -> None:
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else find_latest_run_dir()
    print(f"Verifying run: {run_dir}")

    df = load_fold_metrics(run_dir)

    recomputed = {}
    for metric in ("AUC", "PR"):
        values = df[metric].to_list()
        mean = sum(values) / len(values)
        std = pl.Series(values).std()
        ci_low, ci_high = t_interval_95(values)
        recomputed[metric] = {"mean": mean, "std": std, "ci_low": ci_low, "ci_high": ci_high}

    reported = json.loads((run_dir / "accumulated_test_metrics.json").read_text())

    print("\n--- Cross-check: independently recomputed vs. YAIB's own accumulated_test_metrics.json ---")
    for metric in ("AUC", "PR"):
        r = recomputed[metric]
        reported_mean = reported["avg"][metric]
        reported_ci = reported["CI_0.95"][metric]
        print(
            f"{metric}: recomputed mean={r['mean']:.6f} (95% CI {r['ci_low']:.6f}-{r['ci_high']:.6f}) "
            f"| YAIB-reported mean={reported_mean:.6f} (95% CI {reported_ci[0]:.6f}-{reported_ci[1]:.6f})"
        )
        assert abs(r["mean"] - reported_mean) < 1e-9, f"{metric} mean disagrees with YAIB's own reported value"
        assert abs(r["ci_low"] - reported_ci[0]) < 1e-6, f"{metric} CI lower bound disagrees"
        assert abs(r["ci_high"] - reported_ci[1]) < 1e-6, f"{metric} CI upper bound disagrees"
    print(
        "\nAll checks passed: independent recomputation from the 25 raw fold files matches YAIB's own aggregate exactly."
    )

    # --- Visual: per-fold AUC/PR grouped by repetition ---
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, metric in zip(axes, ("AUC", "PR")):
        for rep in sorted(df["repetition"].unique().to_list()):
            sub = df.filter(pl.col("repetition") == rep).sort("fold")
            ax.plot(sub["fold"], sub[metric], marker="o", label=f"rep {rep}")
        ax.set_xlabel("fold")
        ax.set_ylabel(metric)
        ax.set_title(f"AKI/XGBoost {metric} per fold, by repetition")
        ax.set_xticks(range(5))
    axes[0].legend(fontsize=8)
    fig.suptitle(f"{run_dir.parent.parent.name}/{run_dir.name}")
    fig.tight_layout()
    plot_path = run_dir / "per_fold_metrics.png"
    fig.savefig(plot_path, dpi=150)
    print(f"Saved per-fold metrics plot: {plot_path}")

    summary = {
        "run_dir": str(run_dir),
        "recomputed": recomputed,
        "yaib_reported_avg": reported["avg"],
        "yaib_reported_CI_0.95": reported["CI_0.95"],
        "n_folds_checked": df.height,
        "verification": "PASSED",
    }
    summary_path = run_dir / "verification_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"Saved verification summary: {summary_path}")


if __name__ == "__main__":
    main()
