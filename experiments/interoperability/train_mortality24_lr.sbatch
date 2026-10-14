#!/usr/bin/env bash
#SBATCH --job-name=interop-train-mortality24-lr
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=logs/train_mortality24_lr_%j.log
#SBATCH --error=logs/train_mortality24_lr_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# run_mortality24_eicu.sbatch has completed.

set -euo pipefail
mkdir -p logs
cd "$YAIB_REPO_ROOT"

RESULTS_DIR="$OLDPWD/results"
LOGS_DIR="$OLDPWD/mortality24_training_logs"

echo "Job started: $(date)"

"$YAIB_REPO_ROOT/.venv/bin/icu-benchmarks" train \
  -d "$RESULTS_DIR/mortality24/eicu-crd" \
  -n eicu-crd \
  -t BinaryClassification \
  -tn Mortality24 \
  -m LogisticRegression \
  -l "$LOGS_DIR" \
  -s 2222 \
  --cpu \
  --reproducible

echo "Job finished: $(date)"
