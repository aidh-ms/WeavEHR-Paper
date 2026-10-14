#!/usr/bin/env bash
#SBATCH --job-name=interop-yaib-dyn-rename
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=32
#SBATCH --mem=256G
#SBATCH --time=24:00:00
#SBATCH --output=logs/yaib_dyn_rename_%j.log
#SBATCH --error=logs/yaib_dyn_rename_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# run_weavehr_pipeline.sbatch has completed.

set -euo pipefail
mkdir -p logs
export POLARS_MAX_THREADS="${SLURM_CPUS_PER_TASK}"
export PYTHONPATH="$(pwd)/src"
REPO_ROOT="$(cd ../.. && pwd)"

echo "Job started: $(date)"
echo "Node: $(hostname)"
uv run --project "$REPO_ROOT" python src/run_yaib_dyn_rename.py
echo "Job finished: $(date)"
