#!/usr/bin/env bash

set -e

RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


cd "$HOME/workspace/YAIB-cohorts-migration-review/Python"

export PYTHONPATH="$HOME/workspace/WeavEHR-ricu-fix/src:$PWD"

PY="$HOME/workspace/YAIB-cohorts-weavehr/.venv/bin/python"

for SRC in eicu-crd-ricu mimic-iv-ricu
do
    for TASK in aki sepsis
    do
        echo "========== NATIVE: $SRC $TASK =========="

        "$PY" "$RUNNER_DIR/native/run-native-outcomes-v2.py" \
            --src "$SRC" \
            --task "$TASK"

        echo "SUCCESS: native $SRC $TASK"
    done

    echo "========== COMPATIBLE AKI: $SRC =========="

    "$PY" "$RUNNER_DIR/compatibility/run-aki-reference-compatible-v2.py" \
        --src "$SRC"

    echo "SUCCESS: compatible $SRC aki"
done

echo "========== LEGACY SEPSIS: eICU =========="

"$PY" "$RUNNER_DIR/compatibility/run-sepsis-reference-compatible-v2.py" \
    --src eicu-crd-ricu \
    --variant legacy-abx

echo "SUCCESS: legacy eicu sepsis"
echo "ALL_SEVEN_EXPERIMENTS_COMPLETE"
