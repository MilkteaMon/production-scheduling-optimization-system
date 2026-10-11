from time import perf_counter
from typing import Literal

from opspilot.analytics.metrics import calculate_metrics
from opspilot.domain.models import Placement, PlanningInput, ScheduleResult
from opspilot.scheduling.validation import validate_schedule


def schedule_heuristic(data: PlanningInput, method: Literal["fcfs", "edd"]) -> ScheduleResult:
    start_clock = perf_counter()
    pending = list(data.jobs)
    availability = [0] * data.machine_count
    placements = []
    now = 0
    while pending:
        available_jobs = [j for j in pending if j.release_time_min <= now]
        available_machines = [k for k, t in enumerate(availability) if t <= now]
        if available_jobs and available_machines:
            key = (
                (lambda j: (j.release_time_min, j.job_id))
                if method == "fcfs"
                else (lambda j: (j.due_time_min, j.release_time_min, j.job_id))
            )
            job = min(available_jobs, key=key)
            machine = min(available_machines)
            finish = now + job.processing_time_min
            placements.append(
                Placement(
                    job_id=job.job_id,
                    machine_code=f"M{machine + 1}",
                    start_min=now,
                    completion_min=finish,
                )
            )
            availability[machine] = finish
            pending.remove(job)
        else:
            events = [t for t in availability if t > now] + [
                j.release_time_min for j in pending if j.release_time_min > now
            ]
            now = min(events)
    errors = validate_schedule(data, placements)
    return ScheduleResult(
        method=method,
        placements=placements,
        validation_errors=errors,
        metrics=calculate_metrics(data, placements),
        total_runtime_seconds=perf_counter() - start_clock,
    )
