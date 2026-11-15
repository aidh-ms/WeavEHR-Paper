#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 RICU_DIR WEAVEHR_DIR OUTPUT_DIR DATASET" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

RICU_DIR="$1"
WEAVEHR_DIR="$2"
OUTPUT_DIR="$3"
DATASET="$4"

PYTHON="${PYTHON:-python3}"
THRESHOLD="${THRESHOLD:-1}"

"$PYTHON" "$SCRIPT_DIR/compare_fidelity.py" \
  --ricu-dir "$RICU_DIR" \
  --weavehr-dir "$WEAVEHR_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --datasets "$DATASET"

"$PYTHON" "$SCRIPT_DIR/report_fidelity.py" \
  --metrics "$OUTPUT_DIR/fidelity_metrics.csv" \
  --output "$OUTPUT_DIR/concept_report.csv" \
  --threshold "$THRESHOLD"
