#!/usr/bin/env bash
#SBATCH --job-name=interop-tune-aki-xgb
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=36:00:00
#SBATCH --output=logs/tune_aki_xgb_%j.log
#SBATCH --error=logs/tune_aki_xgb_%j.err

# Run with `sbatch` from this directory, after `source .env`.
#
# Trains AKI/XGBoost with hyperparameter tuning enabled (--tune), using
# YAIB's own unmodified defaults for the search: configs/prediction_models/
# XGBClassifier.gin defines the search space (learning_rate, n_estimators,
# max_depth, scale_pos_weight, min_child_weight, max_delta_step,
# colsample_bytree), and configs/prediction_models/common/MLTuning.gin sets
# the search itself (Optuna GPSampler, 30 calls, 5 initial points, tuned on
# 5 folds) -- none of this is written or overridden here, it is what YAIB
# ships and runs for every classical ML model when --tune is passed.
#
# Reads from results/aki/eicu-crd-tuning/, a frozen byte-identical copy of
# results/aki/eicu-crd/{dyn,sta,outc}.parquet, made so this long-running job
# can never race against the cohort-building script being re-run on the
# original files while this is still training.
#
# Expected duration: the untuned run (job 597685) took 2h04m for this same
# data. Tuning adds an Optuna search of 30 trials x 5 folds each *before*
# that same 25-fold run executes with the winning hyperparameters bound --
# roughly 6x the untuned run's fold count, so plan for this to run
# considerably longer (potentially into the double-digit hours). 36h is a
# safety ceiling, not an estimate; the job exits as soon as it's actually done.

set -euo pipefail
mkdir -p logs
cd "$YAIB_REPO_ROOT"

RESULTS_DIR="$OLDPWD/results"
LOGS_DIR="$OLDPWD/aki_training_logs_tuned"

echo "Job started: $(date)"
echo "Node: $(hostname)"

"$YAIB_REPO_ROOT/.venv/bin/icu-benchmarks" train \
  -d "$RESULTS_DIR/aki/eicu-crd-tuning" \
  -n eicu-crd \
  -t BinaryClassification \
  -tn AKI \
  -m XGBClassifier \
  -l "$LOGS_DIR" \
  -s 2222 \
  --tune \
  --cpu \
  --reproducible

echo "Job finished: $(date)"
