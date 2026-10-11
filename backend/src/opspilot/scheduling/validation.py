import math

from opspilot.domain.models import Placement, PlanningInput

TOLERANCE = 1e-5


def validate_schedule(data: PlanningInput, placements: list[Placement]) -> list[str]:
    """Independent checks; never infer validity from solver termination."""
    errors: list[str] = []
    jobs = {j.job_id: j for j in data.jobs}
    ids = [p.job_id for p in placements]
    if len(ids) != len(set(ids)):
        errors.append("A job is scheduled more than once")
    if set(ids) != set(jobs):
        errors.append("Scheduled jobs do not match the input jobs")
    machines = {f"M{k}" for k in range(1, data.machine_count + 1)}
    for p in placements:
        if p.machine_code not in machines:
            errors.append(f"{p.job_id}: unknown machine")
        if p.job_id not in jobs:
            continue
        if not (math.isfinite(p.start_min) and math.isfinite(p.completion_min)):
            errors.append(f"{p.job_id}: nonfinite time")
            continue
        j = jobs[p.job_id]
        if p.start_min < j.release_time_min - TOLERANCE:
            errors.append(f"{p.job_id}: release time violated")
        if abs(p.completion_min - p.start_min - j.processing_time_min) > TOLERANCE:
            errors.append(f"{p.job_id}: incorrect processing duration")
        if p.completion_min > data.horizon_min + TOLERANCE:
            errors.append(f"{p.job_id}: planning horizon violated")
    for machine in machines:
        items = sorted(
            (p for p in placements if p.machine_code == machine), key=lambda p: p.start_min
        )
        for left, right in zip(items, items[1:]):
            if left.completion_min > right.start_min + TOLERANCE:
                errors.append(f"{machine}: overlapping jobs {left.job_id}, {right.job_id}")
    return errors


def normalize_schedule(data: PlanningInput, placements: list[Placement]) -> list[Placement]:
    """Left-shift a validated order; deliberately wait for unreleased next jobs."""
    jobs = {j.job_id: j for j in data.jobs}
    result = []
    for k in range(1, data.machine_count + 1):
        machine = f"M{k}"
        available = 0
        for p in sorted(
            (p for p in placements if p.machine_code == machine),
            key=lambda p: (p.start_min, p.job_id),
        ):
            job = jobs[p.job_id]
            start = max(available, job.release_time_min)
            available = start + job.processing_time_min
            result.append(
                Placement(
                    job_id=job.job_id,
                    machine_code=machine,
                    start_min=start,
                    completion_min=available,
                )
            )
    return result
