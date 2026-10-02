# Scalability

We evaluated runtime and memory consumption in two settings. First, we compared
WeavEHR and `ricu` on a controlled extraction of the common concept set
from MIMIC-IV and eICU-CRD, so that runtime differences reflect implementation
efficiency rather than catalogue size. Second, we profiled all three tools ---
WeavEHR, `ricu`, and `reprodICU` --- each extracting its full
native concept catalogue from the same databases. These full-catalogue figures
are not directly comparable across tools but reflect the workload a user
encounters in practice. Because the tools differ in execution model, we report
timings for intermediate steps as well as end-to-end. Each tool was configured
according to its own documentation for optimal performance, using the latest
stable release at the time of evaluation. Each run was executed inside a Docker
container with available memory limited to 16, 32 and 48\,GB. We report median time
and median peak memory at the container level, together with the observed range,
across five repeated runs. Input data were stored on local NVMe storage and the
page cache was cleared before each run. Runs that failed to complete within the
memory limit were recorded as such.

## Running the benchmark

```
config.env                   # host paths, datasets, memory limits, repeats, demo switch
run_all.sh                   # runs all five tool/setting combinations
common/bench.sh              # shared driver (build, drop caches, docker run, collect)
common/measure.sh            # container entrypoint (wall time + cgroup memory)
common/common_concepts.csv   # common concept set (ricu <-> WeavEHR names)
common_concepts/{weavehr,ricu}/              # setting 1: common concept set
full_catalogue/{weavehr,ricu,reprodicu}/     # setting 2: full native catalogue
```

Each tool folder has a `Dockerfile`, the tool's run script and a `start.sh`.
Set the paths in `config.env`, then run a single tool or everything:

```sh
./common_concepts/weavehr/start.sh
./run_all.sh
DEMO=1 REPEATS=1 MEM_LIMITS=16 ./run_all.sh   # quick test on the PhysioNet demos
```

Each dataset (MIMIC-IV, eICU-CRD; `DATASETS` in `config.env`) is benchmarked in
its own container runs, so a tool never processes both at once. Per run, `bench.sh`

- drops the host page cache with a privileged throwaway container
  (`echo 3 > /proc/sys/vm/drop_caches`; set `DROP_CACHES=0` to skip),
- starts the tool with `--memory=<N>g --memory-swap=<N>g` (no swap) and
  `--network none`, with the one dataset mounted read-only at `/input` and a fresh
  run directory mounted at `/output`,
- records status (`ok`/`oom`/`failed`), wall time and peak memory in
  `$OUT_DIR/results.csv`, and the timings of the intermediate steps in
  `$OUT_DIR/steps.csv`. Logs stay in
  `$OUT_DIR/<mode>/<setting>/<tool>/<dataset>/<mem>g/run<i>/`.
  Tool outputs are deleted after each run.

Peak memory is measured inside the container via cgroup v2:
`peak_cgroup_bytes` (`memory.peak`, includes page cache),
`peak_workingset_bytes` (usage minus inactive file cache, as `docker stats`)
and `peak_anon_bytes` (anonymous memory), the latter two sampled every second.

ricu and reprodICU write files next to their source data (ricu's `.fst`
import, reprodICU's Parquet copies), so they work on a symlinked copy of the
input under `/output/work`; that conversion is part of the measured time.

reprodICU runs the steps of its `build_all()`. Its magic concepts
(`build_magic_concepts`) are not run: they set up the paths of all seven
reprodICU datasets and fail unless every one of them is present.

All tools write Parquet. ricu loads each concept at 1-minute resolution
(`interval = mins(1L)`, closest to WeavEHR's raw events) and writes one long
table per concept and source: stay ID, time since ICU admission in hours, value.

### Common concept set

`common/common_concepts.csv` lists the 76 concepts that both ricu (0.6.3) and
WeavEHR map for MIMIC-IV and eICU-CRD. All of them are directly mapped (non-recursive)
concepts. Excluded:

- ricu recursive concepts (e.g. `sofa*`, `sep3`, `pafi`, `vent_ind`) and
  WeavEHR derived concepts (e.g. `sofa*`, `aki*`).
- Concepts mapped for only one of the two databases in one tool: vasopressor
  durations, `tracheostomy`, `body_fluid_sampling` (WeavEHR: MIMIC-IV only);
  `esr`, `hba1c`, `etco2`, `mech_vent` (ricu: MIMIC-IV only); `hbco`,
  `vent_start`, `vent_end`, `tgcs` (ricu: eICU only).
- `los_icu`, `los_hosp` (no WeavEHR mapping) and ricu's `o2sat` (union of
  SpO2 and SaO2; `spo2` and `sao2` are included individually).
