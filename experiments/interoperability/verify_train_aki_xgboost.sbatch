#!/usr/bin/env bash
#SBATCH --job-name=interop-verify-train-aki-xgb
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/verify_train_aki_xgb_%j.log
#SBATCH --error=logs/verify_train_aki_xgb_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# train_aki_xgboost.sbatch has completed. Optionally pass a specific run
# directory: `sbatch verify_train_aki_xgboost.sbatch <run_dir>`.

set -euo pipefail
mkdir -p logs
export PYTHONPATH="$(pwd)/src"
REPO_ROOT="$(cd ../.. && pwd)"

echo "Job started: $(date)"
uv run --project "$REPO_ROOT" python src/verify_train_aki_xgboost.py "$@"
echo "Job finished: $(date)"
