#!/usr/bin/env bash
# Run every tool in both settings with the settings from config.env.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

for start in "$HERE"/common_concepts/*/start.sh "$HERE"/full_catalogue/*/start.sh; do
  "$start"
done
