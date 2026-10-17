#!/usr/bin/env bash
# Run every tool in the full native catalogue setting with the settings from config.env.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

for start in "$HERE"/full_catalogue/*/start.sh; do
  "$start"
done
