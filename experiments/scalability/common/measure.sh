#!/usr/bin/env bash
# Container entrypoint: runs the given command and writes its wall time and
# container-level (cgroup v2) memory usage to /output/metrics.env.
set -uo pipefail

OUT=/output
CG=/sys/fs/cgroup
INTERVAL="${SAMPLE_INTERVAL:-1}"
mkdir -p "$OUT/data" "$OUT/work" "$OUT/tmp"

# Background sampler. memory.peak (read at the end) includes the page cache,
# so we additionally track the peak working set (usage minus inactive file
# cache, as reported by `docker stats`) and the peak anonymous memory.
sample() {
  local ws_max=0 anon_max=0 cur anon inactive ws
  while :; do
    cur=$(<"$CG/memory.current")
    read -r anon inactive < <(awk '$1=="anon"{a=$2} $1=="inactive_file"{i=$2} END{print a, i}' "$CG/memory.stat")
    ws=$((cur - inactive))
    ((ws > ws_max)) && ws_max=$ws
    ((anon > anon_max)) && anon_max=$anon
    echo "$ws_max $anon_max" > "$OUT/.peak.tmp" && mv "$OUT/.peak.tmp" "$OUT/.peak"
    sleep "$INTERVAL"
  done
}
sample &
sampler=$!

start=$(date +%s.%N)
"$@"
rc=$?
end=$(date +%s.%N)

kill "$sampler" 2>/dev/null
wait "$sampler" 2>/dev/null

read -r peak_ws peak_anon < "$OUT/.peak" || { peak_ws=NA; peak_anon=NA; }
peak_cgroup=$(cat "$CG/memory.peak" 2>/dev/null || echo NA)
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
peak_cgroup_bytes=$peak_cgroup
peak_workingset_bytes=$peak_ws
peak_anon_bytes=$peak_anon
EOF
echo "[measure] $(tr '\n' ' ' < "$OUT/metrics.env")"
exit "$rc"
