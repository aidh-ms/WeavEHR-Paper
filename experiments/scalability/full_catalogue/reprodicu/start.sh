#!/usr/bin/env bash
# Build this tool's image and run the benchmark (see ../../config.env).
set -euo pipefail
source "$(dirname "$0")/../../config.env"
# reprodICU's extractors need the OMOP vocabulary; skip rather than fail so
# run_full_catalogue.sh still runs the other tools.
if [[ ! -f "${OMOP_DIR:-}/CONCEPT.csv" ]]; then
  echo "== full_catalogue / reprodicu SKIPPED: no OMOP vocabulary at OMOP_DIR=${OMOP_DIR:-} (see config.env)" >&2
  exit 0
fi
exec "$(dirname "$0")/../../common/bench.sh" "$(dirname "$0")"
