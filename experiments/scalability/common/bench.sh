#!/usr/bin/env bash
# Shared benchmark driver, called by every <setting>/<tool>/start.sh.
# Builds the tool image and runs it REPEATS times per dataset and memory limit
# (one dataset per container), dropping the page cache before each run.
# Results are appended to
#   $OUT_DIR/results.csv  (one row per run: status, wall time, peak memory)
#   $OUT_DIR/steps.csv    (one row per intermediate step of each run)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL_DIR="$(cd "$1" && pwd)"
TOOL="$(basename "$TOOL_DIR")"
SETTING="$(basename "$(dirname "$TOOL_DIR")")"
source "$ROOT/config.env"

MODE=$([[ "$DEMO" == 1 ]] && echo demo || echo full)
IMAGE="scalability-$SETTING-$TOOL"

input_dir() {
  case "$1:$DEMO" in
    mimic-iv:1) echo "$DATA_DIR/mimic-iv-demo/2.2" ;;
    mimic-iv:*) echo "$DATA_DIR/mimiciv/3.1" ;;
    eicu:1) echo "$DATA_DIR/eicu-crd-demo/2.0.1" ;;
    eicu:*) echo "$DATA_DIR/eicu-crd/2.0" ;;
    *) echo "unknown dataset: $1" >&2; exit 1 ;;
  esac
}

drop_caches() {
  # vm.drop_caches is host-wide, so a privileged throwaway container can do
  # it without sudo. Alternative: sync; echo 3 | sudo tee /proc/sys/vm/drop_caches
  docker run --rm --privileged alpine:3.22 sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'
}

echo "== $SETTING / $TOOL ($MODE)"
docker build -t "$IMAGE" -f "$TOOL_DIR/Dockerfile" "$ROOT"

mkdir -p "$OUT_DIR"
RESULTS="$OUT_DIR/results.csv"
STEPS="$OUT_DIR/steps.csv"
[[ -f "$RESULTS" ]] || echo "setting,tool,mode,dataset,mem_limit_gb,run,status,exit_code,wall_seconds,peak_memory_bytes,started_at" > "$RESULTS"
[[ -f "$STEPS" ]] || echo "setting,tool,mode,dataset,mem_limit_gb,run,step,seconds,status" > "$STEPS"

for dataset in $DATASETS; do
  INPUT_DIR="$(input_dir "$dataset")"
  for mem in $MEM_LIMITS; do
    for run in $(seq 1 "$REPEATS"); do
      RUN_DIR="$OUT_DIR/$MODE/$SETTING/$TOOL/$dataset/${mem}g/run$run"
      NAME="$IMAGE-$dataset-${mem}g-run$run"
      rm -rf "$RUN_DIR" && mkdir -p "$RUN_DIR"
      docker rm -f "$NAME" > /dev/null 2>&1 || true
      drop_caches

      started_at=$(date -Iseconds)
      echo "-- $dataset ${mem}g run $run/$REPEATS ($started_at), input: $INPUT_DIR, log: $RUN_DIR/log.txt"
      rc=0
      docker run --name "$NAME" \
        --memory "${mem}g" --memory-swap "${mem}g" \
        --cgroupns private --network none \
        --user "$(id -u):$(id -g)" \
        -e HOME=/tmp -e DEMO="$DEMO" -e DATASET="$dataset" \
        -v "$INPUT_DIR:/input:ro" \
        -v "$RUN_DIR:/output" \
        "$IMAGE" > "$RUN_DIR/log.txt" 2>&1 || rc=$?
      oom_killed=$(docker inspect -f '{{.State.OOMKilled}}' "$NAME")
      docker rm "$NAME" > /dev/null

      # Defaults in case the container died before writing its metrics.
      status=failed exit_code=$rc wall_seconds=NA
      peak_memory_bytes=NA
      [[ -f "$RUN_DIR/metrics.env" ]] && source "$RUN_DIR/metrics.env"
      [[ "$oom_killed" == true ]] && status=oom

      prefix="$SETTING,$TOOL,$MODE,$dataset,$mem,$run"
      echo "$prefix,$status,$exit_code,$wall_seconds,$peak_memory_bytes,$started_at" >> "$RESULTS"
      [[ -f "$RUN_DIR/steps.csv" ]] && tail -n +2 "$RUN_DIR/steps.csv" | sed "s|^|$prefix,|" >> "$STEPS"
      echo "   status=$status wall=${wall_seconds}s peak_memory=$peak_memory_bytes"

      # Keep logs and metrics only; tool outputs need tens of GB per run.
      rm -rf "$RUN_DIR/data" "$RUN_DIR/work" "$RUN_DIR/tmp"
    done
  done
done
