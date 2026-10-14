#!/usr/bin/env bash
#SBATCH --job-name=interop-yaib-static
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=logs/yaib_static_%j.log
#SBATCH --error=logs/yaib_static_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# run_yaib_wide.sbatch has completed (reads its output, openicu_all_concepts_wide.parquet).

set -euo pipefail
mkdir -p logs
export POLARS_MAX_THREADS="${SLURM_CPUS_PER_TASK}"
export PYTHONPATH="$(pwd)/src"
REPO_ROOT="$(cd ../.. && pwd)"

echo "Job started: $(date)"
uv run --project "$REPO_ROOT" python src/run_yaib_static.py
echo "Job finished: $(date)"
