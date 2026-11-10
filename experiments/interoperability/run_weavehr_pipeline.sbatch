#!/usr/bin/env bash
#SBATCH --job-name=interop-weavehr-pipeline
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=06:00:00
#SBATCH --output=logs/weavehr_pipeline_%j.log
#SBATCH --error=logs/weavehr_pipeline_%j.err

# Run with `sbatch` from this directory, after `source .env`.
# Uses `uv run` against the repo root's own pyproject.toml/uv.lock (this
# experiment has no separate venv of its own).

set -euo pipefail
mkdir -p logs
export POLARS_MAX_THREADS="${SLURM_CPUS_PER_TASK}"
export PYTHONPATH="$(pwd)/src"
REPO_ROOT="$(cd ../.. && pwd)"

echo "Job started: $(date)"
uv run --project "$REPO_ROOT" python src/run_weavehr_pipeline.py
echo "Job finished: $(date)"
