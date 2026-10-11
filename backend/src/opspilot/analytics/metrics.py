from opspilot.domain.models import KPI, Placement, PlanningInput


def late_jobs(data: PlanningInput, placements: list[Placement]) -> list[dict]:
    jobs = {j.job_id: j for j in data.jobs}
    rows = []
    for p in placements:
        j = jobs[p.job_id]
        tardiness = max(0, p.completion_min - j.due_time_min)
        if tardiness > 0:
            rows.append(
                {
                    **p.model_dump(),
                    "due_time_min": j.due_time_min,
                    "tardiness_min": tardiness,
                    "priority_weight": j.priority_weight,
                    "weighted_tardiness": tardiness * j.priority_weight,
                }
            )
    return sorted(rows, key=lambda r: (-r["weighted_tardiness"], r["job_id"]))


def machine_utilization(data: PlanningInput, placements: list[Placement]) -> list[dict]:
    span = max((p.completion_min for p in placements), default=0)
    rows = []
    for k in range(1, data.machine_count + 1):
        code = f"M{k}"
        items = [p for p in placements if p.machine_code == code]
        busy = sum(p.completion_min - p.start_min for p in items)
        rows.append(
            {
                "machine_code": code,
                "job_count": len(items),
                "busy_time_min": busy,
                "window_utilization": busy / data.horizon_min,
                "span_utilization": busy / span if span else 0,
                "horizon_min": data.horizon_min,
                "schedule_span_min": span,
            }
        )
    return rows


def calculate_metrics(data: PlanningInput, placements: list[Placement]) -> KPI:
    late = late_jobs(data, placements)
    span = max(p.completion_min for p in placements)
    busy = sum(j.processing_time_min for j in data.jobs)
    return KPI(
        total_jobs=len(data.jobs),
        late_jobs=len(late),
        total_weighted_tardiness=sum(r["weighted_tardiness"] for r in late),
        makespan_min=span,
        window_utilization=busy / (data.machine_count * data.horizon_min),
        span_utilization=busy / (data.machine_count * span),
        horizon_min=data.horizon_min,
        machine_count=data.machine_count,
    )


def reduction(baseline: float, new: float) -> dict:
    return {
        "absolute_reduction": baseline - new,
        "percentage_reduction": 100 * (baseline - new) / baseline if baseline > 0 else None,
    }
