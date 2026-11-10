#!/usr/bin/env bash
#SBATCH --job-name=interop-train-aki-xgb
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH --output=logs/train_aki_xgb_%j.log
#SBATCH --error=logs/train_aki_xgb_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# run_aki_eicu.sbatch has completed.
#
# icu-benchmarks is a separate tool (rvandewater/YAIB) with its own venv at
# $YAIB_REPO_ROOT/.venv, not managed by this repo's own uv environment, and
# resolves its gin configs via a relative "configs" path -- must run from
# that repo's own root.

set -euo pipefail
mkdir -p logs
cd "$YAIB_REPO_ROOT"

RESULTS_DIR="$OLDPWD/results"
LOGS_DIR="$OLDPWD/aki_training_logs"

echo "Job started: $(date)"
echo "Node: $(hostname)"

"$YAIB_REPO_ROOT/.venv/bin/icu-benchmarks" train \
  -d "$RESULTS_DIR/aki/eicu-crd" \
  -n eicu-crd \
  -t BinaryClassification \
  -tn AKI \
  -m XGBClassifier \
  -l "$LOGS_DIR" \
  -s 2222 \
  --cpu \
  --reproducible

echo "Job finished: $(date)"
