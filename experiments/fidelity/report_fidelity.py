#!/usr/bin/env python3
"""Report concept fidelity from aggregated metrics only. Never reads clinical data."""
import argparse
import csv
import math
from pathlib import Path

REQUIRED = (
    "dataset", "concept", "buckets_both_value", "buckets_different",
    "presence_disagreement_pct", "mrd_pct",
)

def percent(value: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return math.nan
    return v if math.isfinite(v) else math.nan

def main() -> None:
    parser = argparse.ArgumentParser(description="Fidelity threshold report from aggregated CSV only")
    parser.add_argument("--metrics", type=Path, required=True, help="Existing fidelity_metrics.csv")
    parser.add_argument("--output", type=Path, required=True, help="Output aggregate report CSV")
    parser.add_argument("--threshold", type=float, default=1.0, help="Review threshold in percent (default: 1.0)")
    args = parser.parse_args()
    if not math.isfinite(args.threshold) or args.threshold <= 0:
        parser.error("--threshold must be positive and finite")
    with args.metrics.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        missing = set(REQUIRED) - set(reader.fieldnames or ())
        if missing:
            parser.error("Missing required aggregate columns: " + ", ".join(sorted(missing)))
        rows = list(reader)
    if not rows:
        parser.error("Input CSV contains no concept rows")
    output_rows = []
    seen = set()
    for row in rows:
        key = (row["dataset"], row["concept"])
        if key in seen:
            parser.error("Duplicate dataset/concept entry: " + repr(key))
        seen.add(key)
        try:
            both = int(row["buckets_both_value"])
            different = int(row["buckets_different"])
        except ValueError:
            parser.error("Invalid integer counts for " + repr(key))
        if both < 0 or different < 0 or different > both:
            parser.error("Invalid aggregate count relationship for " + repr(key))
        disagreement = 100 * different / both if both else math.nan
        presence = percent(row["presence_disagreement_pct"])
        mrd = percent(row["mrd_pct"])
        values = (disagreement, presence, mrd)
        status = "UNDEFINED" if not all(math.isfinite(v) for v in values) else (
            "REVIEW" if any(v >= args.threshold for v in values) else "PASS"
        )
        output_rows.append({
            "dataset": row["dataset"],
            "concept": row["concept"],
            "value_disagreement_pct": disagreement,
            "presence_disagreement_pct": presence,
            "mrd_pct": mrd,
            "status": status,
        })
    output_rows.sort(key=lambda r: (r["dataset"], r["concept"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    datasets = sorted({row["dataset"] for row in output_rows})
    for dataset in datasets:
        selected = [row for row in output_rows if row["dataset"] == dataset]
        passed = sum(row["status"] == "PASS" for row in selected)
        flagged = [row for row in selected if row["status"] != "PASS"]
        print(f"{dataset}: {passed}/{len(selected)} PASS; {len(flagged)} flagged (threshold: {args.threshold:g}%)")
        for row in flagged:
            print(f"  {row['concept']}: {row['status']} | value={row['value_disagreement_pct']:.6g}% | presence={row['presence_disagreement_pct']:.6g}% | MRD={row['mrd_pct']:.6g}%")
    print(f"Aggregated concept report: {args.output}")

if __name__ == "__main__":
    main()
