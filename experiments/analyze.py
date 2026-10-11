"""Derive every reported experiment number from completed raw records."""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

import numpy as np


def summary(values):
    return {
        "median": statistics.median(values),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "maximum": max(values),
    }


def main(folder, report):
    rows = [json.loads(line) for line in (folder / "runs.jsonl").read_text().splitlines()]
    completion = json.loads((folder / "completion.json").read_text())
    if len(rows) != 285 or completion["method_results"] != 285:
        raise ValueError("The full experiment must finish before reporting its matrix")
    if len({r["experiment_key"] for r in rows}) != len(rows):
        raise ValueError("Duplicate experiment keys")
    groups = {}
    for row in rows:
        key = (
            row["jobs"],
            row["base_machines"],
            row["profile"],
            row["seed"],
            row["additional_machine"],
        )
        groups.setdefault(key, {})[row["method"]] = row
    base = [g for key, g in groups.items() if not key[-1]]
    milp = [g["milp"] for g in base]
    compared = {}
    for method in ["fcfs", "edd"]:
        comparisons = []
        for g in base:
            b, n = g[method]["metrics"], g["milp"]["metrics"]
            reduction = b["total_weighted_tardiness"] - n["total_weighted_tardiness"]
            comparisons.append(
                {
                    "absolute_reduction": reduction,
                    "percentage_reduction": 100 * reduction / b["total_weighted_tardiness"]
                    if b["total_weighted_tardiness"] > 0
                    else None,
                    "late_jobs_change": n["late_jobs"] - b["late_jobs"],
                    "makespan_change": n["makespan_min"] - b["makespan_min"],
                }
            )
        percentages = [
            c["percentage_reduction"] for c in comparisons if c["percentage_reduction"] is not None
        ]
        compared[method] = {
            "improved": sum(c["absolute_reduction"] > 0 for c in comparisons),
            "tied": sum(c["absolute_reduction"] == 0 for c in comparisons),
            "worse": sum(c["absolute_reduction"] < 0 for c in comparisons),
            "median_absolute_reduction": statistics.median(
                c["absolute_reduction"] for c in comparisons
            ),
            "valid_percentage_denominators": len(percentages),
            "median_percentage_reduction_nonzero_baselines": statistics.median(percentages),
            "late_jobs_worse": sum(c["late_jobs_change"] > 0 for c in comparisons),
            "late_jobs_better": sum(c["late_jobs_change"] < 0 for c in comparisons),
            "makespan_worse": sum(c["makespan_change"] > 0 for c in comparisons),
            "makespan_better": sum(c["makespan_change"] < 0 for c in comparisons),
        }
    scenarios = []
    for key, extra in groups.items():
        if not key[-1]:
            continue
        baseline = groups[(*key[:-1], False)]
        best_base = min(baseline.values(), key=lambda r: r["metrics"]["total_weighted_tardiness"])
        best_extra = min(extra.values(), key=lambda r: r["metrics"]["total_weighted_tardiness"])
        b, n = best_base["metrics"], best_extra["metrics"]
        scenarios.append(
            {
                "seed": key[3],
                "baseline": b["total_weighted_tardiness"],
                "additional_machine": n["total_weighted_tardiness"],
                "absolute_reduction": b["total_weighted_tardiness"] - n["total_weighted_tardiness"],
                "percentage_reduction": 100
                * (b["total_weighted_tardiness"] - n["total_weighted_tardiness"])
                / b["total_weighted_tardiness"]
                if b["total_weighted_tardiness"]
                else None,
                "baseline_method": best_base["method"],
                "extra_method": best_extra["method"],
                "baseline_proven_optimal": best_base["proven_optimal"],
                "extra_proven_optimal": best_extra["proven_optimal"],
                "same_job_hash": best_base["job_hash"] == best_extra["job_hash"],
                "same_horizon": b["horizon_min"] == n["horizon_min"],
            }
        )
    result = {
        "base_datasets": len(base),
        "method_results": len(rows),
        "all_validated": all(r["validated"] for r in rows),
        "base_milp_status_counts": dict(Counter(r["solver_status"] for r in milp)),
        "base_milp_source_counts": dict(Counter(r["result_source"] for r in milp)),
        "base_proven_optimal": sum(r["proven_optimal"] for r in milp),
        "warm_start_loaded_count": sum(
            any("MIPStart values read" in line for line in r["diagnostics"]) for r in milp
        ),
        "solver_failure_count": sum(
            r["solver_status"] in ["error", "infeasible", "unbounded"] for r in milp
        ),
        "known_bound_count": sum(r["best_bound"] is not None for r in milp),
        "solver_runtime_seconds": summary([r["solver_runtime_seconds"] for r in milp]),
        "total_runtime_seconds": summary([r["total_runtime_seconds"] for r in milp]),
        "comparisons": compared,
        "additional_machine_comparisons": scenarios,
        "by_size": {
            str(n): {
                "optimal": sum(r["proven_optimal"] for r in milp if r["jobs"] == n),
                "total": sum(r["jobs"] == n for r in milp),
            }
            for n in [20, 35, 50]
        },
    }
    (folder / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    statuses = ", ".join(
        f"{name}: {count}" for name, count in result["base_milp_status_counts"].items()
    )
    sources = ", ".join(
        f"{name}: {count}" for name, count in result["base_milp_source_counts"].items()
    )
    lines = [
        "# Executed synthetic experiments",
        "",
        "This report is generated by `experiments/analyze.py` from the saved complete raw matrix.",
        "It describes observed schedules under the MVP assumptions, not calibrated factory performance.",
        "",
        "## Configuration and reproducibility",
        "",
        "The base matrix has 90 datasets: 20/35/50 jobs × 3/5 machines × relaxed/tight/staggered profiles × five seeds (0–4). Each dataset has FCFS, EDD, and MILP results, giving 270 base method records. Five additional-machine scenarios for 35 jobs, three baseline machines, tight profile add 15 records (285 in total). Jobs and horizon are reused for each scenario. CBC receives 60 seconds, fixed seed 42, serial execution, a validated warm start, and no intentionally positive stopping gap.",
        "",
        "Raw schedules, hashes, objective, bounds/gaps, provenance, validation, and timings are in `experiments/results/full-60s/runs.jsonl`; flattened metrics are in `summary.csv`, machine/software context in `environment.json`, and derived statistics in `analysis.json`. Re-run the benchmark command to resume missing records; use a different output directory for a fresh experiment. The solver and generator versions are recorded. Runtime came from a development machine while other development work continued, so it is descriptive rather than a controlled throughput measurement.",
        "",
        "The host was Windows 11, Intel Core i5-12400F (six cores, twelve logical processors, 16 GB RAM), Python 3.13.15, PuLP 4.0.0, NumPy 2.5.4, Pandas 2.3.3, and official standalone CBC 2.10.13. The corrected matrix uses three concurrent independent experiment processes, each running serial CBC. Elapsed timing is reported under that workload, not as isolated-process performance. The interactive application retains its single execution queue.",
        "",
        "## Results",
        "",
        f"All {len(rows)} returned schedules passed the independent validator: **{result['all_validated']}**. Of 90 base MILP runs, **{result['base_proven_optimal']} ({100 * result['base_proven_optimal'] / 90:.1f}%)** established optimality. Terminations: {statuses}. Retained schedule sources: {sources}. Bounds were supported for {result['known_bound_count']} base runs; absent values remain null.",
        "",
        "| Comparator | Improved objective | Tied | Worse | Median absolute reduction (all 90) | Median % reduction (positive baselines only) | Positive denominators |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method, c in compared.items():
        lines.append(
            f"| {method.upper()} | {c['improved']} | {c['tied']} | {c['worse']} | {c['median_absolute_reduction']:g} weighted min | {c['median_percentage_reduction_nonzero_baselines']:.1f}% | {c['valid_percentage_denominators']} |"
        )
    lines += [
        "",
        f"CBC confirmed loading the warm start in {result['warm_start_loaded_count']} base runs. Solver failures (error/infeasible/unbounded): {result['solver_failure_count']}. Fallback frequency: {result['base_milp_source_counts'].get('heuristic_fallback', 0)}/90 ({100 * result['base_milp_source_counts'].get('heuristic_fallback', 0) / 90:.1f}%).",
        "",
        "The comparison uses the app's retained validated result, including heuristic fallbacks; it is not a claim about CBC-only improvement. The retention rule prevents returning a worse weighted-tardiness schedule than either baseline. Median percentages exclude zero denominators and must not be read as an average production improvement.",
        "",
        "| Jobs | Proven optima | Runs |",
        "|---|---:|---:|",
    ]
    for n, c in result["by_size"].items():
        lines.append(f"| {n} | {c['optimal']} | {c['total']} |")
    lines += [
        "",
        "| Runtime (seconds) | Median | P90 | P95 | Maximum |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, key in [
        ("PuLP / CBC solve call", "solver_runtime_seconds"),
        ("Total execution", "total_runtime_seconds"),
    ]:
        c = result[key]
        lines.append(
            f"| {label} | {c['median']:.2f} | {c['p90']:.2f} | {c['p95']:.2f} | {c['maximum']:.2f} |"
        )
    lines += [
        "",
        "Solver runtime is the elapsed PuLP solve call, including its adapter file I/O and CBC process. Total execution also includes model construction, solver probing, extraction, and validation inside the worker. The API adds queue waiting and persistence separately; these experiment timings exclude interactive queue waiting.",
        "",
        "## Tradeoffs and extra-machine scenarios",
        "",
    ]
    for method, c in compared.items():
        lines.append(
            f"Against {method.upper()}, retained results had fewer late jobs in {c['late_jobs_better']} cases and more in {c['late_jobs_worse']}; makespan was lower in {c['makespan_better']} and higher in {c['makespan_worse']}. Weighted tardiness is the sole objective, so other KPIs may deteriorate."
        )
    lines += [
        "",
        "Each row compares best-known validated objectives among the three methods. These time-limited results need not be optimal.",
        "",
        "| Seed | Three machines | Four machines | Reduction (weighted min) | Reduction % | Both proven optimal |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for c in scenarios:
        percent = (
            f"{c['percentage_reduction']:.1f}%" if c["percentage_reduction"] is not None else "N/A"
        )
        lines.append(
            f"| {c['seed']} | {c['baseline']:g} | {c['additional_machine']:g} | {c['absolute_reduction']:g} | {percent} | {c['baseline_proven_optimal'] and c['extra_proven_optimal']} |"
        )
    lines += [
        "",
        "## Adapter audit and limits",
        "",
        "The initial adapter used an absolute MIP-start filename that the standalone Windows CBC build did not open. Its valid schedules are preserved in `initial-unaccepted-warm-start-60s/`, but those results are excluded from this corrected matrix. Adapter 1.1 uses unique relative solver filenames without changing the working directory. A regression test verifies CBC actually reads and accepts the start, and each raw result retains the corresponding log messages.",
        "",
        "This fixed matrix is synthetic and relatively small. The model's LP bound can be weak, and difficult instances frequently exhaust the time budget. Fallbacks and unknown gaps are visible rather than disguised as optimal schedules. The result-retention policy is a safeguard, not proof that CBC found an improvement. An extra machine expands feasible capacity, but finite-budget searches may have different incumbent quality. No forecast accuracy, factory UAT, economic return, or production acceptance is established.",
        "",
        "Windows results do not verify Linux/Docker behavior. CI contains those checks, pending execution. A commercial deployment would require reviewed assumptions, real data, and independently verified platform behavior.",
        "",
    ]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, default=Path("experiments/results/full-60s"))
    parser.add_argument("--report", type=Path, default=Path("docs/opspilot/experiments.md"))
    args = parser.parse_args()
    main(args.folder, args.report)
