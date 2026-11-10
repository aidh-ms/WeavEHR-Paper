"""RICU numeric comparison for eICU-CRD -- this experiment's fidelity check.

Checks WeavEHR's own extracted concept values against RICU's reference
implementation for the same dataset, following openicu-yaib's own documented
5-step workflow exactly (example/datasets/eicu-crd.ipynb), not a bespoke
comparison:

  1. WeavEHR -> full concept-wide table (run_weavehr_pipeline.py)
  2. RICU reference export for the same concepts (this script, step A)
  3. WeavEHR wide table restricted to the first 7 days (this script, step B)
  4. Compare (this script, step C)

Generic WeavEHR-vs-RICU technical validation across whichever concepts both
sides support -- not specific to any one clinical task.

Requires the one-time `ricu` data import to have already completed
(import_ricu_eicu.sbatch, from this experiment's own scripts -- see README)
and the `yaib-cohorts2` conda environment with ricu/arrow/data.table
installed.
"""

import json
import os
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
from openicu_yaib import (
    build_and_write_yaib_wide_for_dataset,
    compare_openicu_wide_to_ricu_for_dataset,
    concept_root_from_output,
    resolve_openicu_workspace,
)

from config import CONDA_BIN, OPENICU_YAIB_REPO_ROOT, RICU_CONDA_ENV, RICU_DATA_PATH
from paths import PROJECT_PATH, RESULTS_DIR

DATASET = "eicu-crd"
MAX_HOURS = 7 * 24

CONDA_RUN = [str(CONDA_BIN), "run", "-n", RICU_CONDA_ENV, "--no-capture-output"]
# The R library's own shipped concept dictionary -- a fixed relative path
# within the conda env's own structure, not something that needs its own
# separate config.py entry.
RICU_CONCEPT_DICT = (
    CONDA_BIN.parent.parent
    / "envs"
    / RICU_CONDA_ENV
    / "lib"
    / "R"
    / "library"
    / "ricu"
    / "extdata"
    / "config"
    / "concept-dict.json"
)

assert RICU_CONCEPT_DICT.exists(), f"ricu's shipped concept dict not found at {RICU_CONCEPT_DICT}"


def _newest_mtime(path: Path) -> float:
    """mtime of `path`, or of its most recently modified file if `path` is a directory."""
    if path.is_file():
        return path.stat().st_mtime
    return max((p.stat().st_mtime for p in path.rglob("*") if p.is_file()), default=0.0)


def is_stale(output_path: Path, *inputs: Path) -> bool:
    """True if `output_path` doesn't exist, or any of `inputs` was modified more recently.

    A cached output reused purely because the file exists, with no check against the
    inputs that produced it, is a reproducibility gap: if an input changes (e.g. WeavEHR
    re-extracts its concepts after a bugfix, or the ricu export script itself is edited)
    after the cache was written, the stale cache would silently be reused instead of being
    regenerated. This is not a guarantee of correctness (two different runs can share an
    mtime within filesystem timestamp resolution), but it catches the realistic case of
    "I changed something upstream and reran this script," which plain existence-checking
    does not.
    """
    if not output_path.exists():
        return True
    output_mtime = output_path.stat().st_mtime
    return any(_newest_mtime(p) > output_mtime for p in inputs if p.exists())


WORKSPACE = resolve_openicu_workspace(PROJECT_PATH)
CONCEPT_ROOT = concept_root_from_output(PROJECT_PATH)
DATASET_OUTPUT = WORKSPACE / "yaib" / DATASET
DATASET_OUTPUT.mkdir(parents=True, exist_ok=True)

print(f"weavehr_project_root = {PROJECT_PATH}")
print(f"workspace             = {WORKSPACE}")
print(f"concept_root          = {CONCEPT_ROOT}")
print(f"dataset_output        = {DATASET_OUTPUT}")

# --- Step A: export RICU's reference values for the same concepts ----------
# Both R exports are the slow part (ricu loading concepts across the full
# dataset, including the huge vitalPeriodic/nurseCharting sources) -- skipped
# if a prior run already produced them *and* nothing they depend on (the
# export script itself, the raw ricu data) has changed since (see
# is_stale()), so a script bug further down never costs a re-run of the
# expensive part, while a real upstream change still triggers one.
ricu_dynamic_path = DATASET_OUTPUT / "ricu_dynamic_vars_eicu.parquet"
ricu_stay_windows_path = DATASET_OUTPUT / "ricu_stay_windows_eicu.parquet"
export_script_path = OPENICU_YAIB_REPO_ROOT / "scripts" / "datasets" / "export_ricu_eicu-crd.R"

if not is_stale(ricu_dynamic_path, export_script_path, RICU_DATA_PATH) and not is_stale(
    ricu_stay_windows_path, export_script_path, RICU_DATA_PATH
):
    print(f"\n--- Step A: already done, reusing {ricu_dynamic_path} and {ricu_stay_windows_path} ---")
else:
    env = os.environ.copy()
    env["RICU_DATA_PATH"] = str(RICU_DATA_PATH)
    env["RICU_OUT_DIR"] = str(DATASET_OUTPUT)
    env["RICU_SRC_LOAD"] = "eicu"
    env["R_ENVIRON_USER"] = "/dev/null"

    print("\n--- Step A: exporting RICU reference values (export_ricu_eicu-crd.R) ---")
    subprocess.run(
        [*CONDA_RUN, "Rscript", "--no-environ", "scripts/datasets/export_ricu_eicu-crd.R"],
        cwd=OPENICU_YAIB_REPO_ROOT,
        env=env,
        check=True,
    )
    assert ricu_dynamic_path.exists(), f"export script ran but did not produce {ricu_dynamic_path}"
    assert ricu_stay_windows_path.exists(), f"export script ran but did not produce {ricu_stay_windows_path}"

# --- Step B: WeavEHR wide table restricted to the first 7 days -------------
weavehr_7d_path = DATASET_OUTPUT / "weavehr_dyn_168h.parquet"
if not is_stale(weavehr_7d_path, CONCEPT_ROOT, RICU_CONCEPT_DICT):
    print(f"\n--- Step B: already done, reusing {weavehr_7d_path} ---")

    class _CachedResult:
        output_path = weavehr_7d_path

    weavehr_7d = _CachedResult()
else:
    print("\n--- Step B: building the 7-day WeavEHR wide table (aggregation_mode='ricu') ---")
    weavehr_7d = build_and_write_yaib_wide_for_dataset(
        dataset=DATASET,
        max_hours=MAX_HOURS,
        output_root=DATASET_OUTPUT,
        concept_root=CONCEPT_ROOT,
        icustays_csv=None,
        ricu_concept_dict=RICU_CONCEPT_DICT,
        version="1.0.0",
        aggregation_mode="ricu",
    )
print(f"WeavEHR 7-day wide table: {weavehr_7d.output_path} ({weavehr_7d.output_path.stat().st_size} bytes)")

# --- Step C: compare -------------------------------------------------------
print("\n--- Step C: comparing WeavEHR vs. RICU ---")
comparison = compare_openicu_wide_to_ricu_for_dataset(
    dataset=DATASET,
    max_hours=MAX_HOURS,
    output_root=DATASET_OUTPUT,
    concept_root=CONCEPT_ROOT,
    icustays_csv=None,
    ricu_concept_dict=RICU_CONCEPT_DICT,
    openicu_wide_path=weavehr_7d.output_path,
)
comparison_dict = comparison.as_dict()

# --- Sanity checks: don't trust a silent/empty comparison as a "pass" ------
# value_diff is the real per-concept table (one row per shared concept, with
# mean_rel_diff -- the same metric the project's own established
# <1%-per-concept threshold refers to), not something invented for this
# script.
value_diff = comparison_dict["value_diff"]
assert value_diff.height > 0, "0 concepts were actually compared -- this is not a real validation"
print(f"\n{value_diff.height} concepts compared.")
print(value_diff.sort("mean_rel_diff", descending=True))

reproduction_accuracy = comparison_dict["reproduction_accuracy"]
assert reproduction_accuracy.height == 1, "expected a single whole-dataset accuracy summary row"
print("\nWhole-dataset stay/row-level agreement:")
print(reproduction_accuracy)

n_within_threshold = value_diff.filter(value_diff["mean_rel_diff"] < 0.01).height
print(
    f"\n{n_within_threshold}/{value_diff.height} concepts within the project's established "
    f"<1% mean relative difference threshold for 'technically done'."
)

# --- Save every report table as JSON (records) for anyone to inspect -------
out_dir = RESULTS_DIR / "ricu_comparison_eicu-crd"
out_dir.mkdir(parents=True, exist_ok=True)
for name, df in comparison_dict.items():
    df.write_csv(out_dir / f"{name}.csv")
    (out_dir / f"{name}.json").write_text(json.dumps(df.to_dicts(), indent=2, default=str))
print(f"Saved all {len(comparison_dict)} report tables (csv + json) to: {out_dir}")

# --- Visual: mean relative difference per concept, against the 1% line -----
vd = value_diff.sort("mean_rel_diff")
fig, ax = plt.subplots(figsize=(9, max(4, 0.3 * vd.height)))
colors = ["tab:red" if v >= 0.01 else "tab:blue" for v in vd["mean_rel_diff"].fill_null(0)]
ax.barh(vd["concept"], vd["mean_rel_diff"].fill_null(0), color=colors)
ax.axvline(0.01, color="black", linestyle="--", linewidth=1, label="1% threshold")
ax.set_xlabel("mean relative difference (WeavEHR vs. ricu)")
ax.set_title(f"WeavEHR vs. ricu per-concept agreement, {DATASET}")
ax.legend()
fig.tight_layout()
plot_path = RESULTS_DIR / "ricu_comparison_eicu-crd_per_concept.png"
fig.savefig(plot_path, dpi=150)
print(f"Saved per-concept comparison plot: {plot_path}")
