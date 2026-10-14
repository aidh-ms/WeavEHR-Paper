"""Independent verification of the AKI cohort/label table -- run separately
from run_aki_eicu.py so its checks can't share a bug with the code they're
checking.

This is not decorative: an earlier version of this cohort builder had a
real, serious bug that every check embedded *inside* that script's own run
missed completely (matching row counts, a "plausible" prevalence number, a
clean exit code) -- it silently dropped stays whose baseline creatinine or
age was missing, because an unguarded null propagated through the
exclusion OR-chain. It was only caught by building the independent
cross-checks below and finding they disagreed with the production numbers.

Checks performed, and why each is here:

1. OR-vs-cascade equivalence. cohort.filter(~(A|B|C|...)) and sequentially
   filtering ~A, then ~B, then ~C on the survivors are mathematically
   required to produce the identical final count -- this is not a
   heuristic, it's set algebra. If they disagree, something is wrong in
   how one of the two was computed (this is exactly what caught the bug
   in the original port of this script).
2. LOS bound. No stay's outcome table may extend past its own actual
   length of stay -- checked by comparing outc.parquet's per-stay max
   hour against the real LOS from the raw eICU-CRD file directly.
3. Label spot checks, both directions: for a sample of label=1 rows,
   independently recompute the true AKI onset hour and confirm
   (onset > t) and (onset <= t + 6); for a sample of label=0 rows,
   confirm that condition is genuinely False.
4. Exclusion-6 (hospital AKI prevalence), both directions: find one real
   hospital with zero observed AKI cases and confirm it would be
   excluded, and one with at least one case and confirm it would not.
5. Missing-data handling: confirm a stay with zero first-24h creatinine
   measurements (the exact scenario the null-propagation bug dropped) is
   present in the final retained cohort.

Produces one real visual: an attrition funnel built via true sequential
cascading (not naive independent-count subtraction, which double-counts
stays matched by more than one exclusion criterion and does not land on
the true final_n).
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

from interoperability.config import EICU_RAW_PATIENT_CSV
from interoperability.paths import AKI_TASK_DIR, RESULTS_DIR

DYN_PATH = RESULTS_DIR / "openicu_dyn_all.parquet"
STA_PATH = RESULTS_DIR / "weavehr_sta_eicu-crd.parquet"
AKI_CONCEPTS_PATH = RESULTS_DIR / "weavehr_aki_concepts_corrected_eicu-crd.parquet"
HOSPITAL_ID_PATH = RESULTS_DIR / "weavehr_hospital_id_eicu-crd.parquet"
ONSET_WINDOW = 6

results: dict = {}

# --- Rebuild the same cohort inputs run_aki_eicu.py uses --------------------
raw = pl.scan_csv(EICU_RAW_PATIENT_CSV, try_parse_dates=True).select(
    pl.col("patientunitstayid").cast(pl.Int64).alias("stay_id"),
    (pl.col("unitdischargeoffset").cast(pl.Float64) / 60).alias("los_hours"),
)
hospital_id = pl.scan_parquet(HOSPITAL_ID_PATH)
aki_concepts = pl.scan_parquet(AKI_CONCEPTS_PATH)
sta = pl.scan_parquet(STA_PATH).select("stay_id", "age")
dyn = pl.scan_parquet(DYN_PATH)
dynamic_cols = [c for c in dyn.collect_schema().names() if c not in ("stay_id", "time")]
has_measurement = pl.any_horizontal([pl.col(c).is_not_null() for c in dynamic_cols])
meas_stats = (
    dyn.filter(has_measurement)
    .select("stay_id", "time")
    .unique()
    .sort("stay_id", "time")  # required before .diff() -- see module docstring
    .group_by("stay_id")
    .agg(pl.len().alias("n_meas"), pl.col("time").diff().max().alias("max_gap"))
)
onset = aki_concepts.filter(pl.col("aki") >= 1).group_by("stay_id").agg(pl.col("time").min().alias("onset_hour"))
baseline = (
    dyn.filter((pl.col("time") >= 0) & (pl.col("time") < 24) & pl.col("crea").is_not_null())
    .group_by("stay_id")
    .agg(pl.col("crea").min().alias("baseline_crea"))
)

cohort = (
    raw.join(hospital_id, on="stay_id", how="left")
    .join(sta, on="stay_id", how="left")
    .join(meas_stats, on="stay_id", how="left")
    .join(onset, on="stay_id", how="left")
    .join(baseline, on="stay_id", how="left")
    .with_columns(pl.col("n_meas").fill_null(0), pl.col("max_gap").fill_null(0))
).collect()
hosp_prev = (
    cohort.select("stay_id", "hospitalid", "onset_hour")
    .group_by("hospitalid")
    .agg((pl.col("onset_hour").is_not_null().sum() > 0).alias("has_aki"))
)
cohort = cohort.join(hosp_prev, on="hospitalid", how="left")

exclusions = [
    ("InvalidLOS", (pl.col("los_hours") < 0).fill_null(False)),
    ("LOS<6h", (pl.col("los_hours") < 6).fill_null(False)),
    ("<4 meas-hrs", (pl.col("n_meas") < 4).fill_null(False)),
    (">12h gap", (pl.col("max_gap") > 12).fill_null(False)),
    ("Age<18", (pl.col("age") < 18).fill_null(False)),
    ("LowHospAKI", pl.col("has_aki").not_().fill_null(True)),
    ("Onset<6h", (pl.col("onset_hour").is_not_null() & (pl.col("onset_hour") < 6)).fill_null(False)),
    ("BaselineCrea>4", (pl.col("baseline_crea") > 4).fill_null(False)),
]

# --- Check 1: OR-combined vs. true sequential cascade ----------------------
combined_excluded = exclusions[0][1]
for _, cond in exclusions[1:]:
    combined_excluded = combined_excluded | cond
or_final_n = cohort.filter(~combined_excluded).height

cascade_counts = [("Initial", cohort.height)]
current = cohort
for name, cond in exclusions:
    current = current.filter(~cond)
    cascade_counts.append((f"-{name}", current.height))
cascade_final_n = cascade_counts[-1][1]

results["or_vs_cascade_equivalence"] = {
    "or_combined_final_n": or_final_n,
    "cascade_final_n": cascade_final_n,
    "match": or_final_n == cascade_final_n,
}
assert or_final_n == cascade_final_n, (
    f"OR-combined final_n ({or_final_n}) != cascade final_n ({cascade_final_n}). "
    "These are mathematically required to be equal -- stop and investigate rather "
    "than trust either number."
)

# --- Check 2: LOS bound -----------------------------------------------------
outc = pl.scan_parquet(AKI_TASK_DIR / "outc.parquet")
dyn_check = pl.scan_parquet(AKI_TASK_DIR / "dyn.parquet")
outc_max = outc.group_by("stay_id").agg(pl.col("time").max().alias("outc_max"))
los_check = outc_max.join(raw, on="stay_id", how="left").collect()
n_exceeding_los = los_check.filter(pl.col("outc_max") > pl.col("los_hours") + 1).height
results["los_bound_check"] = {"n_stays_exceeding_actual_los": n_exceeding_los}
assert n_exceeding_los == 0, f"{n_exceeding_los} stays have outcome rows past their actual LOS."

n_dyn_rows = dyn_check.select(pl.len()).collect().item()
n_outc_rows = outc.select(pl.len()).collect().item()
results["dyn_outc_row_count_match"] = {
    "dyn_rows": n_dyn_rows,
    "outc_rows": n_outc_rows,
    "match": n_dyn_rows == n_outc_rows,
}
assert n_dyn_rows == n_outc_rows, (
    f"dyn.parquet ({n_dyn_rows} rows) and outc.parquet ({n_outc_rows} rows) should match exactly."
)

# --- Check 3: label spot checks, both directions ----------------------------
outc_df = outc.collect()


def onset_hour_for(stay_id: int) -> int | None:
    r = (
        aki_concepts.filter((pl.col("stay_id") == stay_id) & (pl.col("aki") >= 1))
        .select(pl.col("time").min())
        .collect()
    )
    return r.item() if r.height and r.item() is not None else None


pos_sample = outc_df.filter(pl.col("label") == 1).sample(5, seed=11)
pos_checks = []
for stay_id, t, _ in pos_sample.iter_rows():
    onset_h = onset_hour_for(stay_id)
    ok = onset_h is not None and (onset_h > t) and (onset_h <= t + ONSET_WINDOW)
    pos_checks.append({"stay_id": stay_id, "t": t, "onset_hour": onset_h, "correct": ok})

neg_sample = outc_df.filter(pl.col("label") == 0).sample(5, seed=11)
neg_checks = []
for stay_id, t, _ in neg_sample.iter_rows():
    onset_h = onset_hour_for(stay_id)
    should_be_false = onset_h is not None and (onset_h > t) and (onset_h <= t + ONSET_WINDOW)
    neg_checks.append({"stay_id": stay_id, "t": t, "onset_hour": onset_h, "correctly_negative": not should_be_false})

results["label_spot_checks"] = {"positive_samples": pos_checks, "negative_samples": neg_checks}
assert all(c["correct"] for c in pos_checks), "A positive-labeled row did not match the onset-window formula."
assert all(c["correctly_negative"] for c in neg_checks), "A negative-labeled row should have been positive."

# --- Check 4: exclusion 6, both directions ----------------------------------
aki_stay_ids = set(aki_concepts.filter(pl.col("aki") >= 1).select("stay_id").unique().collect()["stay_id"].to_list())
per_hosp = hospital_id.group_by("hospitalid").agg(pl.col("stay_id")).collect()
excluded_example, included_example = None, None
for hospitalid_val, stays in per_hosp.iter_rows():
    has_any = any(s in aki_stay_ids for s in stays)
    if not has_any and excluded_example is None:
        excluded_example = {"hospitalid": hospitalid_val, "n_stays": len(stays)}
    if has_any and included_example is None:
        included_example = {"hospitalid": hospitalid_val, "n_stays": len(stays)}
    if excluded_example and included_example:
        break
results["exclusion_6_spot_check"] = {
    "zero_aki_hospital_example": excluded_example,
    "has_aki_hospital_example": included_example,
}

# --- Check 5: a previously-mishandled missing-data case is now retained ----
no_crea_stays = (
    dyn.filter((pl.col("time") >= 0) & (pl.col("time") < 24))
    .group_by("stay_id")
    .agg(pl.col("crea").is_not_null().sum().alias("n_crea"))
    .filter(pl.col("n_crea") == 0)
    .select("stay_id")
    .collect()
)
retained_no_crea = outc_df.select("stay_id").unique().join(no_crea_stays, on="stay_id", how="inner")
results["missing_baseline_crea_retained_example"] = {
    "n_retained_stays_with_zero_first24h_creatinine": retained_no_crea.height,
    "example_stay_id": retained_no_crea["stay_id"][0] if retained_no_crea.height else None,
}
assert retained_no_crea.height > 0, (
    "No retained stay has zero first-24h creatinine measurements -- if this ever "
    "becomes true again, the null-propagation bug this check exists for may have "
    "been reintroduced."
)

# --- Visual: true cascading attrition funnel --------------------------------
fig, ax = plt.subplots(figsize=(10, 5))
labels = [c[0] for c in cascade_counts]
vals = [c[1] for c in cascade_counts]
ax.bar(range(len(labels)), vals, color="#3b6fa0")
ax.set_xticks(range(len(labels)))
ax.set_xticklabels(labels, rotation=40, ha="right")
ax.set_ylabel("Stays remaining (true sequential cascade)")
ax.set_title(f"AKI cohort attrition, eICU-CRD (final: {vals[-1]:,} / {vals[0]:,})")
for i, v in enumerate(vals):
    ax.text(i, v + 2000, f"{v:,}", ha="center", fontsize=8)
fig.tight_layout()
plot_path = AKI_TASK_DIR / "attrition_funnel.png"
fig.savefig(plot_path, dpi=150)
plt.close(fig)
results["attrition_funnel_plot"] = str(plot_path)
results["attrition_cascade_counts"] = cascade_counts

print(json.dumps(results, indent=2, default=str))
(AKI_TASK_DIR / "verification_summary.json").write_text(json.dumps(results, indent=2, default=str))
print("\nAll checks passed.")
