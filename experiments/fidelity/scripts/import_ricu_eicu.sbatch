#!/usr/bin/env bash
#SBATCH --job-name=fidelity-ricu-import-eicu
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --time=24:00:00
#SBATCH --output=../logs/ricu_import_eicu_%j.log
#SBATCH --error=../logs/ricu_import_eicu_%j.err

# One-time ricu import of the raw eICU-CRD data, needed before any RICU
# numeric comparison against WeavEHR's output. Run with `sbatch` from this
# directory, after `source ../.env`. A no-op if this machine already has a
# completed ricu import (checked by import_ricu_eicu.R itself via
# src_data_avail()).

set -euo pipefail
mkdir -p ../logs

echo "Job started: $(date)"
"$CONDA_BIN" run -n "${RICU_CONDA_ENV:-yaib-cohorts2}" --no-capture-output \
  Rscript "$(pwd)/import_ricu_eicu.R"
echo "Job finished: $(date)"
