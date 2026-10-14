# Fidelity

Does WeavEHR's harmonised output agree, numerically, with RICU's reference
implementation for the same raw data? This experiment answers that for
eICU-CRD: every concept the two tools share is compared value-for-value over
the first 7 days of each stay, and the result is reported as a per-concept
mean relative difference against the project's own established **<1%**
threshold for "technically done".

Ported from the author's own prior validation work
([georginapetr/openicu-yaib-integration](https://github.com/georginapetr/openicu-yaib-integration)),
originally built against OpenICU, re-run here against the current WeavEHR
codebase and its own fresh eICU-CRD extraction.

## Pipeline

```mermaid
flowchart LR
    A["Raw eICU-CRD<br>(PhysioNet)"] --> B["WeavEHR<br>extraction + concept steps"]
    A --> D["RICU<br>R reference implementation"]
    B --> C["openicu-yaib<br>WeavEHR -> YAIB-wide format"]
    C --> E{{"RICU comparison<br>mean relative difference per concept"}}
    D --> E
```

1. **`run_weavehr_pipeline.py`** — runs WeavEHR's `ExtractionStep` then
   `ConceptStep` for eICU-CRD into this experiment's own `output/` directory.
2. **`scripts/import_ricu_eicu.R`** (one-time, via `scripts/import_ricu_eicu.sbatch`)
   — imports the raw eICU-CRD download into `ricu`'s own cached format.
3. **`run_ricu_comparison.py`** — follows `openicu-yaib`'s own documented
   5-step workflow (`example/datasets/eicu-crd.ipynb` in that package) exactly:
   export RICU's reference values for the shared concepts, build WeavEHR's
   matching 7-day wide table (`aggregation_mode="ricu"`), compare. Each
   expensive step is skipped on re-run if its output already exists.

## Setup

```sh
cd experiments/fidelity
cp .env.example .env    # fill in your own machine-specific paths
source .env
```

Needs, in addition to the repo's own `uv sync`: a local checkout of
[georginapetr/openicu-yaib](https://github.com/georginapetr/openicu-yaib)
(for the R export resource script) and a conda environment with
`ricu`/`arrow`/`data.table` installed (see that repo's own setup notes).

## Running

```sh
sbatch scripts/import_ricu_eicu.sbatch     # one-time per machine
sbatch run_weavehr_pipeline.sbatch
sbatch run_ricu_comparison.sbatch          # after the above two complete
```

Results (per-concept comparison tables as CSV+JSON, and a summary plot) are
written to `results/`.

## Results (eICU-CRD)

**48/48 shared concepts land under the <1% mean relative difference
threshold** (largest: `mg`, 0.49%). Of 200,859 WeavEHR stays, 196,340 have a
matching RICU stay (RICU's own internal filtering excludes the remaining
4,519 — not a disagreement, just nothing to compare against for those). Full
per-concept table and plot: `results/ricu_comparison_eicu-crd/value_diff.csv`
and `results/ricu_comparison_eicu-crd_per_concept.png`. All 10 underlying
report tables are saved as CSV+JSON in `results/ricu_comparison_eicu-crd/`
for independent inspection.

## Sources

The `<1%` mean-relative-difference threshold is this validation task's
agreed criterion; the comparison methodology applying it is documented, with
full results, in
[georginapetr/openicu-yaib-integration](https://github.com/georginapetr/openicu-yaib-integration#ricu-comparison-eicu-crd).
