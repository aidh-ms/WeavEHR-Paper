#!/usr/bin/env bash
# Build this tool's image and run the benchmark (see ../../config.env).
set -euo pipefail
exec "$(dirname "$0")/../../common/bench.sh" "$(dirname "$0")"
