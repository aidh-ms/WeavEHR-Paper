#!/usr/bin/env bash
# Run every tool in the common concept set setting with the settings from config.env.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

for start in "$HERE"/common_concepts/*/start.sh; do
  "$start"
done
