#!/usr/bin/env bash
#SBATCH --job-name=fidelity-ricu-compare
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=06:00:00
#SBATCH --output=logs/ricu_compare_%j.log
#SBATCH --error=logs/ricu_compare_%j.err

# Run with `sbatch` from this directory, after `source .env`.
# Requires run_weavehr_pipeline.sbatch and scripts/import_ricu_eicu.sbatch to
# have completed successfully first.

set -euo pipefail
mkdir -p logs
export POLARS_MAX_THREADS="${SLURM_CPUS_PER_TASK}"
export PYTHONPATH="$(pwd)/src"
REPO_ROOT="$(cd ../.. && pwd)"

echo "Job started: $(date)"
uv run --project "$REPO_ROOT" python src/run_ricu_comparison.py
echo "Job finished: $(date)"
