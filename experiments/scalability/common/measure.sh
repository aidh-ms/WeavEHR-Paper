#!/usr/bin/env bash
# Container entrypoint: runs the given command and writes its wall time and the
# container's peak memory (cgroup v2 memory.peak) to /output/metrics.env.
set -uo pipefail

OUT=/output
CG=/sys/fs/cgroup
mkdir -p "$OUT/data" "$OUT/work" "$OUT/tmp"

start=$(date +%s.%N)
"$@"
rc=$?
end=$(date +%s.%N)

oom_kills=$(awk '$1=="oom_kill"{print $2}' "$CG/memory.events")
if ((rc == 0)); then
  status=ok
elif ((oom_kills > 0)); then
  status=oom
else
  status=failed
fi

cat > "$OUT/metrics.env" <<EOF
status=$status
exit_code=$rc
wall_seconds=$(awk "BEGIN{printf \"%.3f\", $end - $start}")
peak_memory_bytes=$(<"$CG/memory.peak")
EOF
echo "[measure] $(tr '\n' ' ' < "$OUT/metrics.env")"
exit "$rc"
