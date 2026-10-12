"""Calculated observations, not an invented account of the solver's reasoning."""

from fastapi import HTTPException

from opspilot.analytics.metrics import reduction


def explain_schedule(service, run_id, baseline_run_id=None):
    run = service.get_run(run_id)
    data, scenario = service.scenario_input(run["scenario_id"])
    summary = []
    changes = {}
    job_changes = []
    if not run["has_valid_schedule"]:
        if run["solver_status"] == "infeasible":
            summary.append(
                "No schedule can meet all selected hard deadlines under these conditions."
            )
        elif run["solver_status"] == "time_limit":
            summary.append(
                "The time limit ended without a validated schedule. This does not prove infeasibility."
            )
        else:
            summary.append(
                "This run has no validated schedule; performance comparisons are unavailable."
            )
        summary.extend(run["diagnostics"])
        summary.extend(run["validation_errors"])
    else:
        summary.append(
            "Weighted tardiness is the sum of each job's lateness multiplied by its priority weight."
        )
        summary.append(
            "CBC established optimality."
            if run["proven_optimal"]
            else "This run has no established proof of optimality."
        )
        if data.must_finish_job_ids:
            summary.append("The validated schedule satisfies every selected hard deadline.")
    baseline = None
    if baseline_run_id:
        baseline, baseline_data, _, _ = service.require_result(baseline_run_id)
        if baseline_data.job_hash != data.job_hash or baseline_data.horizon_min != data.horizon_min:
            raise HTTPException(409, "Explanations require identical jobs and horizon")
        if not run["has_valid_schedule"]:
            raise HTTPException(409, "Cannot compare a run without a validated schedule")
        changes = {
            key: reduction(baseline["metrics"][key], run["metrics"][key])
            for key in ["total_weighted_tardiness", "late_jobs", "makespan_min"]
        }
        old = {p["job_id"]: p for p in baseline["placements"]}
        current = {p["job_id"]: p for p in run["placements"]}
        for job in data.jobs:
            b, n = old[job.job_id], current[job.job_id]
            bt, nt = (
                max(0, b["completion_min"] - job.due_time_min),
                max(0, n["completion_min"] - job.due_time_min),
            )
            job_changes.append(
                {
                    "job_id": job.job_id,
                    "priority_weight": job.priority_weight,
                    "due_time_min": job.due_time_min,
                    "baseline_completion_min": b["completion_min"],
                    "completion_min": n["completion_min"],
                    "baseline_tardiness_min": bt,
                    "tardiness_min": nt,
                    "weighted_tardiness_reduction": job.priority_weight * (bt - nt),
                    "must_finish_on_time": job.job_id in data.must_finish_job_ids,
                }
            )
        job_changes.sort(key=lambda row: (-abs(row["weighted_tardiness_reduction"]), row["job_id"]))
        change = changes["total_weighted_tardiness"]
        percentage = change["percentage_reduction"]
        summary.append(
            f"Weighted tardiness reduction: {change['absolute_reduction']:g} weighted min; "
            + (
                f"{percentage:g}%"
                if percentage is not None
                else "percentage N/A because the baseline is zero"
            )
            + "."
        )
        summary.append(
            f"Late-job reduction: {changes['late_jobs']['absolute_reduction']:g} jobs; makespan reduction: {changes['makespan_min']['absolute_reduction']:g} min. Negative reductions mean deterioration."
        )
        if change["absolute_reduction"] > 0 and changes["late_jobs"]["absolute_reduction"] < 0:
            summary.append(
                "Weighted lateness improved while more jobs became late. The order-level contributions show this tradeoff; the objective does not minimize late-job count."
            )
        if (
            baseline_data.must_finish_job_ids != data.must_finish_job_ids
            or baseline_data.machine_count != data.machine_count
        ):
            summary.append(
                "These scenarios have different capacity or hard deadlines. This is a scenario comparison, not a same-conditions algorithm benchmark."
            )
    summary.append(
        "These are calculated observations. They do not establish why a particular order is mathematically necessary; use a confirmed What-if scenario to test an alternative requirement."
    )
    return {
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "dataset_id": scenario["dataset_id"],
        "scenario_id": scenario["id"],
        "method": run["method"],
        "solver_status": run["solver_status"],
        "result_source": run["result_source"],
        "proven_optimal": run["proven_optimal"],
        "has_valid_schedule": run["has_valid_schedule"],
        "machine_count": data.machine_count,
        "must_finish_job_ids": data.must_finish_job_ids,
        "metrics": run["metrics"],
        "baseline_metrics": baseline["metrics"] if baseline else None,
        "summary": summary,
        "changes": changes,
        "job_changes": job_changes,
    }
