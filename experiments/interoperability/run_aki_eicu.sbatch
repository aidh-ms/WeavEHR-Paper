#!/usr/bin/env bash
#SBATCH --job-name=interop-aki-eicu
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=04:00:00
#SBATCH --output=logs/aki_eicu_%j.log
#SBATCH --error=logs/aki_eicu_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# run_yaib_dyn_rename.sbatch, run_yaib_static.sbatch, run_yaib_hospital_id.sbatch
# and run_aki_concepts_corrected.sbatch have all completed.

set -euo pipefail
mkdir -p logs
export POLARS_MAX_THREADS="${SLURM_CPUS_PER_TASK}"
export PYTHONPATH="$(pwd)/src"
REPO_ROOT="$(cd ../.. && pwd)"

echo "Job started: $(date)"
echo "Node: $(hostname)"
uv run --project "$REPO_ROOT" python src/run_aki_eicu.py
echo "Job finished: $(date)"
