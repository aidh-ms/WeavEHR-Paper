#!/usr/bin/env bash
#SBATCH --job-name=interop-mortality24-eicu
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH --output=logs/mortality24_eicu_%j.log
#SBATCH --error=logs/mortality24_eicu_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# run_yaib_dyn_rename.sbatch and run_yaib_static.sbatch have completed.

set -euo pipefail
mkdir -p logs
export POLARS_MAX_THREADS="${SLURM_CPUS_PER_TASK}"
export PYTHONPATH="$(pwd)/src"
REPO_ROOT="$(cd ../.. && pwd)"

echo "Job started: $(date)"
echo "Node: $(hostname)"
uv run --project "$REPO_ROOT" python src/run_mortality24_eicu.py
echo "Job finished: $(date)"
