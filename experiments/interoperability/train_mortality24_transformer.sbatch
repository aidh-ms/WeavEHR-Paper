#!/usr/bin/env bash
#SBATCH --job-name=interop-train-mortality24-tf
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --qos=a100
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/train_mortality24_transformer_%j.log
#SBATCH --error=logs/train_mortality24_transformer_%j.err

# Run with `sbatch` from this directory, after `source .env` and after
# run_mortality24_eicu.sbatch has completed.
#
# The one genuine neural-network training job in this experiment -- real
# GPU resources, unlike every other training job here (tree/linear models,
# which don't benefit from GPU at this scale).

set -euo pipefail
mkdir -p logs
cd "$YAIB_REPO_ROOT"

RESULTS_DIR="$OLDPWD/results"
LOGS_DIR="$OLDPWD/mortality24_training_logs"

echo "Job started: $(date)"
echo "Node: $(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv 2>&1 || echo "nvidia-smi not available"

"$YAIB_REPO_ROOT/.venv/bin/icu-benchmarks" train \
  -d "$RESULTS_DIR/mortality24/eicu-crd" \
  -n eicu-crd \
  -t BinaryClassification \
  -tn Mortality24 \
  -m Transformer \
  -l "$LOGS_DIR" \
  -s 2222 \
  --reproducible

echo "Job finished: $(date)"
