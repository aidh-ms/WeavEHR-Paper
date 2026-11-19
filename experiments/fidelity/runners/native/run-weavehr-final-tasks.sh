#!/usr/bin/env bash

set -euo pipefail

SRC="${1:?Usage: $0 DATASET}"

case "$SRC" in
    mimic-iv-ricu|eicu-crd-ricu|hirid|aumc) ;;
    *) echo "Unsupported dataset: $SRC"; exit 1 ;;
esac

YAIB=/home/q039tl/workspace/YAIB-cohorts-migration-review
WEAVEHR=/home/q039tl/workspace/weavehr-ai-workspace/WeavEHR
PY=/home/q039tl/workspace/YAIB-cohorts-weavehr/.venv/bin/python

ROOT="$HOME/output/yaib-cohorts/weavehr-final"
PROJECT="$HOME/output/yaib-cohorts/weavehr-projects-final/$SRC"
LOG="$HOME/output/yaib-weavehr-final-logs/$SRC/$(date +%Y%m%d-%H%M%S)"

mkdir -p "$LOG"

cd "$YAIB/Python"

export PYTHONPATH="$WEAVEHR/src:$PWD"

for step in extraction concept; do
    if [ ! -f "$PROJECT/datasets/$step/.complete" ]; then
        echo "ERROR: $step has not completed for $SRC"
        exit 1
    fi
done

git -C "$WEAVEHR" rev-parse HEAD > "$LOG/weavehr-commit.txt"
git -C "$YAIB" rev-parse HEAD > "$LOG/yaib-commit.txt"
cp "$YAIB/config.yaml" "$LOG/config.yaml"

for task in mortality24 aki los; do
    case "$task" in
        mortality24) script=mortality.py ;;
        aki) script=aki.py ;;
        los) script=los.py ;;
    esac

    echo "========== $SRC / $task =========="

    if [ -e "$ROOT/$task/$SRC" ]; then
        echo "SKIP: output directory already exists"
        continue
    fi

    START=$(date +%s)

    STATUS=0

    "$PY" "$script" --src "$SRC" \
        > "$LOG/$task.log" 2>&1 || STATUS=$?

    END=$(date +%s)

    printf '%s,%s,%s,%s\n' \
        "$SRC" "$task" "$STATUS" "$((END-START))" \
        >> "$LOG/status.csv"

    echo "Exit code: $STATUS"
    echo "Runtime: $((END-START)) seconds"
done

echo "========== COMPLETE =========="
echo "Logs: $LOG"
