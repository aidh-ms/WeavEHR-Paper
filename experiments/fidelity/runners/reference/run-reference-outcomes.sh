#!/usr/bin/env bash

set -uo pipefail

cd /home/q039tl/yaib/YAIB-cohorts-ricu/R || exit 1

ROOT=/home/q039tl/output/yaib-cohorts-reference
LOG="$HOME/output/yaib-reference-logs/$(date +%Y%m%d-%H%M%S)"

mkdir -p "$LOG"

export RENV_CONFIG_AUTOLOADER_ENABLED=FALSE
export R_LIBS_USER=/home/q039tl/R/x86_64-pc-linux-gnu-library/4.3

for task in mortality24 aki; do
    case "$task" in
        mortality24) script=mortality.R ;;
        aki) script=aki.R ;;
    esac

    for src in miiv hirid aumc; do
        echo "========== $task / $src =========="

        if [ -e "$ROOT/$task/$src" ]; then
            echo "SKIP: output directory already exists"
            continue
        fi

        if [ ! -f "$ROOT/base/$src/sta.parquet" ]; then
            echo "SKIP: base cohort missing"
            continue
        fi

        START=$(date +%s)

        Rscript -e \
            "Sys.unsetenv('RICU_CONFIG_PATH'); source('$script')" \
            --src "$src" \
            > "$LOG/${task}_${src}.log" 2>&1

        STATUS=$?
        END=$(date +%s)

        printf '%s,%s,%s,%s\n' \
            "$task" "$src" "$STATUS" "$((END-START))" \
            >> "$LOG/status.csv"

        echo "Exit code: $STATUS"
        echo "Runtime: $((END-START)) seconds"
    done
done

echo "========== ALL RUNS FINISHED =========="
echo "Logs: $LOG"
