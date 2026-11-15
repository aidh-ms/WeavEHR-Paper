# Fidelity

How closely does WeavEHR reproduce `ricu` for the 48 dynamic YAIB variables? This experiment compares, per dataset
and concept, the hourly values that the two backends of
[YAIB-cohorts](https://github.com/rvandewater/YAIB-cohorts) produce for the first 7 days of each ICU stay of the
length-of-stay (`los`) cohort. The comparison only reads their existing outputs: nothing is filtered, repaired or
recomputed, and it writes aggregate counts only.

```
compare_fidelity.py                       # the comparison
README.md                                 # this procedure
../../tests/test_fidelity_comparison.py   # synthetic tests
results/                                  # outputs (git-ignored)
```

Procedure: [1](#1-upstream-revisions-and-dependencies) revisions → [2](#2-two-yaib-cohorts-checkouts) checkouts and
configuration → [3](#3-ricu-backend) ricu backend → [4](#4-weavehr-backend) WeavEHR backend →
[5](#5-record-the-upstream-versions) record versions → [6](#6-compare) compare. Steps 3 and 4 are independent.

## 1. Upstream reference revisions and dependencies

| Component | Repository | Revision |
|---|---|---|
| YAIB-cohorts, WeavEHR backend (`Python/`, `weavehr-extensions/`) | [TobiasVeronaLaser/YAIB-cohorts](https://github.com/TobiasVeronaLaser/YAIB-cohorts/tree/feat/weavehr-backend), branch `feat/weavehr-backend` | `eb2956ec1d12cd79b8565bdfb37a92056cd1f28c` |
| YAIB-cohorts, ricu backend (`R/`, `ricu-extensions/`) | same commit; these folders are identical to upstream [rvandewater/YAIB-cohorts](https://github.com/rvandewater/YAIB-cohorts) `main` | `74ac699f5d4117613f9c48bdc4e0852099c42e19` (upstream) |
| WeavEHR | [aidh-ms/WeavEHR](https://github.com/aidh-ms/WeavEHR) | `2fcccb6bf5ca66e559fef5491dc795dd07cdcdfd`, pinned in YAIB-cohorts' `Python/environment.yml` |
| ricu | R package | YAIB's `R/renv.lock` pins R 4.2.2, ricu 0.6.0 ([prockenschaub/ricu-package@monkeypatch0.6.0](https://github.com/prockenschaub/ricu-package/tree/monkeypatch0.6.0), `0969a52`), data.table 1.14.8, arrow 22.0.0; record the versions actually used (step 5) |
| This comparison | this repository | recorded in `provenance.json` |

- WeavEHR backend: the conda environment of YAIB-cohorts'
  [`Python/environment.yml`](https://github.com/TobiasVeronaLaser/YAIB-cohorts/blob/feat/weavehr-backend/Python/environment.yml)
  (Python 3.13, WeavEHR, pandas, polars, pyarrow, pyyaml, numpy, scikit-learn).
- ricu backend: R with `ricu`, `data.table`, `arrow`, `argparser`, `assertthat`, `rlang`, `vctrs`, `yaml` and `glue`,
  either from YAIB's renv lock (`Rscript setup_env.R` in `R/`) or from an R user library (see
  [issues](#issues-of-the-eicu-ricu-run)). The dataset must have been imported into ricu once (`?ricu::import_src`).
- Comparison: Python ≥ 3.14 with `polars` (`uv sync` in this repository).

## 2. Two YAIB-cohorts checkouts

The following checkout recipe targets the newer upstream revision `eb2956e`. It has NOT been verified to reproduce the results below. The evaluated local checkouts were `02f7d90` (WeavEHR backend) and `8ed523c` (ricu backend), with local modifications:

```sh
export YAIB_RICU=$PWD/yaib-ricu YAIB_WEAVEHR=$PWD/yaib-weavehr   # used by the following steps
for dir in "$YAIB_RICU" "$YAIB_WEAVEHR"; do
  git clone https://github.com/TobiasVeronaLaser/YAIB-cohorts.git "$dir"
  git -C "$dir" checkout eb2956ec1d12cd79b8565bdfb37a92056cd1f28c
done
```

Two checkouts because both backends read the same `config.yaml` (`out_dir`), and ricu and WeavEHR use the same
`--src` names for HiRID and AUMC, so their outputs would overwrite each other. Only the ricu checkout gets the
one-line R fix of step 3.

Set in each checkout's `config.yaml` (paths are resolved from `R/` or `Python/`, so use absolute paths):

| Checkout | Key | Value |
|---|---|---|
| `yaib-ricu` | `ricu_data_path` | ricu's data directory with the imported dataset (`RICU_DATA_PATH`, set by `R/.load_ricu.R`) |
| `yaib-ricu` | `out_dir` | e.g. `/data/fidelity/ricu`; `base_cohort.R` writes `<out_dir>/base/<src>/`, which `los.R` reads |
| `yaib-weavehr` | `weavehr_project_path` | WeavEHR project per dataset, e.g. `/data/weavehr-projects/{src}` (patient-level data: keep it outside any repository) |
| `yaib-weavehr` | `out_dir` | e.g. `/data/fidelity/weavehr` |

Concept extensions need no setup: `R/.load_ricu.R` loads `ricu-extensions/` (ricu's own dictionary plus YAIB's
additions), and `Python/weavehr_build.py` registers `weavehr-extensions/` ahead of WeavEHR's configs. The WeavEHR
backend reads a dataset only if `weavehr-extensions/config.yml` defines its ICU stays under `sources` (`eicu-crd`,
`mimic-iv`, `aumc` and HiRID do in the evaluated local configuration).

## 3. ricu backend

```sh
cd "$YAIB_RICU/R"
# YAIB bug with data.table >= 1.18.0 (see issues); harmless with older versions:
sed -i 's/pmin(end, \.\.\.time)/pmin(end, i....time)/' src/obs_time.R
grep -c 'pmin(end, i\.\.\.\.time)' src/obs_time.R          # must print 1
export RENV_CONFIG_AUTOLOADER_ENABLED=FALSE                # only when using the R user library instead of renv

Rscript -e 'Sys.unsetenv("RICU_CONFIG_PATH"); source("base_cohort.R")' --src eicu
Rscript -e 'Sys.unsetenv("RICU_CONFIG_PATH"); source("los.R")' --src eicu
```

`los.R` keeps the stays of the base cohort, so `base_cohort.R` must run first, with the same `config.yaml`. Plain
`Rscript base_cohort.R --src eicu` is equivalent if `RICU_CONFIG_PATH` is not set in your R environment. ricu `--src`
names: `eicu`, `miiv`, `aumc`, `hirid` (`eicu_demo` for a dry run on the public demo).

## 4. WeavEHR backend

```sh
cd "$YAIB_WEAVEHR/Python"
conda env create -f environment.yml && conda activate yaib-cohorts
python weavehr_build.py --src eicu-crd --version 2.0 --data-path /path/to/physionet.org/files/eicu-crd/2.0
python los.py --src eicu-crd
```

WeavEHR `--src` names and versions: `eicu-crd` 2.0, `mimic-iv` 3.1 (inherits the 2.2 mappings), `aumc` 1.5.0 (the
AMSTEL OMOP export), `eicu-demo` 2.0.

## 5. Record the upstream versions

The comparison cannot see which pipelines produced its inputs, so record them next to its outputs. Run from the
root of this repository, in the shell of steps 3 and 4 (renv setting exported, conda environment active):

```sh
OUT=experiments/fidelity/results/eicu-crd
mkdir -p "$OUT"
{
  echo "## ricu backend"; git -C "$YAIB_RICU" rev-parse HEAD; git -C "$YAIB_RICU" diff -- R ricu-extensions
  (cd "$YAIB_RICU/R" && Rscript -e 'cat(R.version.string, "\n"); for (p in c("ricu", "data.table", "arrow")) cat(p, format(packageVersion(p)), "\n")')
  echo "## WeavEHR backend"; git -C "$YAIB_WEAVEHR" rev-parse HEAD; git -C "$YAIB_WEAVEHR" diff -- Python weavehr-extensions
  python -c 'import importlib.metadata as m; d = m.distribution("weavehr"); print("weavehr", d.version, d.read_text("direct_url.json"))'
  echo "## data: eICU-CRD 2.0 (ricu: imported eicu; WeavEHR: --version 2.0)"
} > "$OUT/upstream_versions.txt"
```

The ricu diff must show only the `obs_time.R` line and the WeavEHR diff must be empty.

## 6. Compare

From this repository (`provenance.json` records the commit and whether there were
uncommitted changes):

```sh
uv run python experiments/fidelity/compare_fidelity.py \
    --ricu-dir /data/fidelity/ricu \
    --weavehr-dir /data/fidelity/weavehr \
    --output-dir experiments/fidelity/results/eicu-crd \
    --datasets eicu-crd
```

`--ricu-dir`/`--weavehr-dir` are the `out_dir`s of step 2; the script reads `<dir>/los/<src>/dyn.parquet`.
`--datasets` takes `eicu-crd`, `mimic-iv`, `hirid`, `aumc` (the default: all four) and `eicu-demo`; every
requested dataset needs both files. All inputs are validated before anything is written; an invalid input stops
the run with an error naming the file and the problem (counts, paths and column names only). The script prints the
coverage table. It reads one variable at a time.

### Inputs

| | ricu (`R/los.R`) | WeavEHR (`Python/los.py`) |
|---|---|---|
| File | `<ricu out_dir>/los/<eicu\|miiv\|hirid\|aumc>/dyn.parquet` | `<WeavEHR out_dir>/los/<eicu-crd\|mimic-iv\|hirid\|aumc>/dyn.parquet` |
| `stay_id` | double (whole numbers) | integer |
| `time` | duration, whole hours | integer hours |
| 48 variables | numbers | numbers |

Required: exactly `stay_id`, `time` and the 48 variables (pandas index columns `__index_level_N__` are ignored); one
row per `(stay_id, time)`; per stay the hours `0, 1, …, end` without gaps, `end ≤ 168`; numeric values (null or NaN
is missing; a column with only missing values may have any type). Stay IDs must be the same identifiers in both
files (eICU `patientunitstayid`, MIMIC-IV `stay_id`, AUMC `admissionid` = OMOP `visit_occurrence_id`).

### Outputs (in `--output-dir`)

| File | Content |
|---|---|
| `fidelity_metrics.csv` | one row per dataset and concept (48 per dataset): `dataset, concept, buckets_total, buckets_something, buckets_both_value, buckets_identical, buckets_different, buckets_weavehr_only, buckets_ricu_only, presence_disagreement_pct, mrd_pct`; an empty cell is undefined |
| `coverage.csv` | one row per dataset: `stays_ricu`, `stays_weavehr`, `stays_common`; `buckets_ricu`, `buckets_weavehr`, `buckets_common` (= `buckets_total`); `buckets_ricu_only_shared_stays`, `buckets_weavehr_only_shared_stays` (grid hours of shared stays in one file only); `values_ricu_outside_common`, `values_weavehr_outside_common` (values, summed over the 48 variables, in buckets not compared) |
| `provenance.json` | time of the run; SHA-256 and git commit of this script, and whether it had uncommitted changes; Python and polars versions; parameters; per input file its path, size, SHA-256 and the types of `stay_id` and `time` |
| `upstream_versions.txt` | written in step 5 |

`results/` is git-ignored: commit results only deliberately, after review.

## Method

**Variables.** The `dynamic_vars` of the YAIB-cohorts task scripts (identical in every R and Python task script and
in `weavehr-extensions/config.yml`).

**Window.** Both backends write YAIB's hourly grid: per stay, `time = 0, 1, …, min(floor(LOS in hours), 168)` hours
since ICU admission, so up to 169 buckets per stay, the last being [168 h, 169 h). Hours without an observation are
rows of nulls. Values are those of the backends: the median per hour, the sum for `urine`.

**Cohort.** The `los` task keeps the YAIB base cohort, so the comparison covers that cohort, not all ICU stays. Each
backend excludes, in this order and on its own data (ricu: `R/base_cohort.R`; WeavEHR: `Python/los.py`):

1. invalid length of stay (stay end < 0);
2. ICU stay shorter than 6 h;
3. fewer than 4 hours with any of the 48 variables (ricu also counts hours before ICU admission, WeavEHR only hours
   within the stay);
4. more than 12 consecutive hours without any of the 48 variables within hours 0–168;
5. age below 18.

Because criteria 3 and 4 depend on the data, a stay can be in one cohort only.

**Comparison population.** The `(stay_id, time)` buckets present in both files, so for stays present in both files
only the hours both grids contain. Buckets in one file only are not compared and not treated as missing values;
`coverage.csv` counts them and the values they hold. Equal stay counts do not imply the same stays:
`stays_common` does. The run stops if the files share no bucket.

**Missing values.** Null or NaN. A bucket where neither backend has a value counts in `buckets_total` only. ricu's
value ranges are not applied to WeavEHR; the outputs are compared as produced.

**Metrics** per dataset and concept (W = WeavEHR, R = ricu):

| Column | Definition |
|---|---|
| `buckets_something` | W or R has a value |
| `buckets_both_value` | both have a value |
| `buckets_identical` | both, and `\|R − W\| ≤ 1e-6 + 1e-3 · \|W\|` (weavehr-yaib's `cohort_comparison.py`; the tolerance scales with `\|W\|`) |
| `buckets_different` | both, but not identical |
| `buckets_weavehr_only` / `buckets_ricu_only` | only W / only R has a value |
| `presence_disagreement_pct` | `100 · (weavehr_only + ricu_only) / something`; empty if `something = 0` |
| `mrd_pct` | `100 · mean(\|W − R\| / \|R\|)` over buckets with both values and `R ≠ 0` (weavehr-yaib's `compare.py`); empty if there are none |

Buckets with `R = 0` are left out of the MRD even if `W ≠ 0` (e.g. hours with 0 ml urine), but count for
identical/different. The paper's 1 % MRD threshold is a concept-level criterion and is not applied here. Every row
is checked: `something = both_value + weavehr_only + ricu_only`, `both_value = identical + different`,
`neither = total − something ≥ 0`.

## Issues of the eICU ricu run

| Issue | Kind | Handling |
|---|---|---|
| `R/src/obs_time.R` (`stop_obs_at`, used by every R task) fails with *Variable '.time' is not found in calling scope*: since data.table 1.18.0 ([#5460](https://github.com/Rdatatable/data.table/issues/5460)) a symbol starting with `..` in `j` is looked up in the calling scope unless it is exactly `...` or `..N`, so the join column `...time` is read as variable `.time`. data.table 1.14.8 (YAIB's renv lock) exempted every `...`-prefixed symbol. | **Upstream bug** (YAIB-cohorts), latent under the renv lock | `i....time` names the column of the joined table explicitly and gives the same result with old and new data.table; applied with `sed` in the ricu checkout only (step 3). To be reported upstream. |
| `RICU_CONFIG_PATH` is set in `~/.Renviron`, which R reads at startup, so unsetting it in the shell has no effect. ricu merges every `concept-dict.json` it finds there into YAIB's dictionary (or fails if the folder is incomplete). | **Machine-specific** | Unset inside R before ricu is loaded: `Rscript -e 'Sys.unsetenv("RICU_CONFIG_PATH"); source("…")' --src …` (step 3). ricu then uses its own configs plus `ricu-extensions/`, as YAIB intends. |
| YAIB's renv environment was incomplete (the lock targets R 4.2.2 and a ricu fork); the packages came from existing R user libraries. | **Machine-specific** | `RENV_CONFIG_AUTOLOADER_ENABLED=FALSE` uses the user library; the package versions are part of the reference and are recorded in step 5. |
| `los.R` reads the base cohort from `<out_dir>/base/<src>/sta.parquet`; with a different `out_dir` (another checkout or config) it finds none or another run's. | **Experiment configuration** | One ricu checkout, absolute `out_dir`, `base_cohort.R` before `los.R` (steps 2 and 3). |

## Known limitations

- **Population.** Results describe the YAIB `los` cohort present in both outputs (adults, stays ≥ 6 h, ≥ 4 hours with
  a measurement, no gap > 12 h in the first 7 days), not all ICU stays, and its 169 hourly buckets per stay.
- **`o2sat` (WeavEHR backend).** `weavehr-extensions/config.yml` pools the WeavEHR concepts `oxygen_saturation` and
  `arterial_oxygen_saturation`, which both map eICU's lab "O2 Sat (%)" rows, and since `eb2956e` the loader no
  longer counts such a row once (`d23837e` did). These rows are counted twice in the hourly median, so the eICU
  `o2sat` result reflects this adapter defect, not WeavEHR's mappings. The same happens for AUMC with WeavEHR
  versions after 0.1.2 and for HiRID. Not fixed here (it belongs in YAIB-cohorts).
- **HiRID.** Both evaluated YAIB backends successfully produced LoS outputs. All 32,338 stays and 1,506,256 hourly keys match; 48/48 concepts PASS. The evaluated local checkouts are not equivalent to a verified run of YAIB commit `eb2956e`.
- **AUMC.** The pinned WeavEHR (`2fcccb6`) predates WeavEHR 0.1.2's AUMC fixes (PCO2/PO2 recorded in kPa converted
  to mmHg; direct bilirubin from another item), which change AUMC values; choose and record the WeavEHR version.
  ricu reads native AmsterdamUMCdb 1.0.2, WeavEHR the 1.5.0 OMOP export; stay IDs correspond by the
  [AMSTEL ETL](https://github.com/AmsterdamUMC/AMSTEL/blob/9e91acc04cba52a713713be933435cdca683730d/inst/sql/insert_visit_occurrence.sql)'s
  construction (`visit_occurrence_id = admissionid`), which is not verified for a given export.
- **MIMIC-IV.** ricu reads the imported release with its 2.2 config; WeavEHR 3.1 inherits the 2.2 mappings.
- **What is compared.** The WeavEHR backend includes `weavehr-extensions/` mappings that reproduce ricu where WeavEHR
  deliberately differs (eICU magnesium ÷ 1.215, eICU FiO2 text parsing, eICU °F temperature rows, MIMIC-IV items
  226253 "SpO2 Desat Limit" and 227510 "TF Residual"). The results measure YAIB-cohorts' WeavEHR backend including
  these, without ricu's value ranges.

## Tests

`uv run pytest tests/test_fidelity_comparison.py` runs synthetic tests (made-up stays, hours and values): each bucket
category, tolerance and MRD edge cases, different populations and grids, the 0/168 boundaries, both time types,
invalid inputs, aggregate-only outputs and the provenance record.

## Final fidelity results (2026-11-15)

Evaluation uses the YAIB length-of-stay cohort and the intersection
of `(stay_id, time)` keys, with hourly positions 0 through 168.

| Dataset | Common stays | Common hourly keys | PASS |
|---|---:|---:|---:|
| eICU-CRD | 182,788 | 10,670,965 | 48/48 |
| MIMIC-IV | 92,972 | 6,241,533 | 48/48 |
| HiRID | 32,338 | 1,506,256 | 48/48 |
| AUMC | 20,432 | 1,185,417 | 0/48 |

PASS requires all three defined concept-level metrics to be below 1%:
value disagreement, presence disagreement and mean relative difference.

For AUMC, 26/48 concepts satisfy the value disagreement criterion,
40/48 satisfy the MRD criterion, and 23/48 satisfy both numerical
criteria. None satisfies the presence criterion. Therefore, 0/48
PASS does not imply that the numerical values generally disagree.

AUMC uses native AmsterdamUMCdb 1.0.2 through ricu and the
AMSTEL-derived OMOP 1.5.0 representation through WeavEHR.
Differences in encounter-relative timestamps, measurement coverage,
and some concept definitions have been documented separately.

### Reproduce the comparison

After generating both YAIB LoS outputs:

    PYTHON=python3 bash experiments/fidelity/run_fidelity.sh \
      /path/to/ricu-output \
      /path/to/weavehr-output \
      /path/to/aggregate-results/hirid \
      hirid

Repeat for `eicu-crd`, `mimic-iv`, `hirid`, and `aumc`.

The runner produces `fidelity_metrics.csv`, `coverage.csv`,
`provenance.json`, and `concept_report.csv`.

All 41 synthetic tests passed. The HiRID comparison was repeated,
and the three aggregate CSV files matched byte-for-byte.

### Provenance limitation

The evaluated local YAIB checkouts were `02f7d90` (WeavEHR backend)
and `8ed523c` (ricu backend), with local modifications.
The exact WeavEHR revision used to generate every historical
Parquet output has not been independently verified.

The recorded comparison environment used Python 3.13.18 and
Polars 1.42.1. Reproducing the comparison with fixed inputs
does not independently establish reproducibility of every upstream
data-processing step.
