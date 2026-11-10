#!/usr/bin/env bash
#SBATCH --job-name=interop-hospital-id
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=logs/hospital_id_%j.log
#SBATCH --error=logs/hospital_id_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# run_weavehr_pipeline.sbatch has completed.

set -euo pipefail
mkdir -p logs
export POLARS_MAX_THREADS="${SLURM_CPUS_PER_TASK}"
export PYTHONPATH="$(pwd)/src"
REPO_ROOT="$(cd ../.. && pwd)"

echo "Job started: $(date)"
uv run --project "$REPO_ROOT" python src/run_yaib_hospital_id.py
echo "Job finished: $(date)"
