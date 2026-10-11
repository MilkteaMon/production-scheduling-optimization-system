import csv
import io
import re

import numpy as np
from pydantic import ValidationError

from opspilot.domain.models import GenerateRequest, Job, PlanningInput

COLUMNS = ["job_id", "processing_time_min", "release_time_min", "due_time_min", "priority_weight"]
GENERATOR_VERSION = "1.0"
MAX_CSV_BYTES = 1024 * 1024


def generate_data(config: GenerateRequest) -> PlanningInput:
    rng = np.random.default_rng(config.seed)
    durations = np.clip(np.rint(rng.lognormal(3.7, 0.55, config.job_count)), 10, 120).astype(int)
    releases = (
        rng.choice([0, 60, 120, 180], config.job_count)
        if config.profile == "staggered"
        else np.zeros(config.job_count, dtype=int)
    )
    load = sum(durations) / config.machine_count
    slack_range = {"relaxed": (1.1, 1.7), "tight": (0.1, 0.55), "staggered": (0.2, 0.65)}[
        config.profile
    ]
    slack = np.rint(rng.uniform(*slack_range, config.job_count) * load).astype(int)
    weights = rng.integers(1, 11, config.job_count)
    jobs = [
        Job(
            job_id=f"JOB-{i + 1:03}",
            processing_time_min=int(durations[i]),
            release_time_min=int(releases[i]),
            due_time_min=int(releases[i] + durations[i] + slack[i]),
            priority_weight=int(weights[i]),
        )
        for i in range(config.job_count)
    ]
    return PlanningInput(jobs=jobs, machine_count=config.machine_count)


def validate_csv(content: bytes, machine_count: int) -> dict:
    errors = []
    jobs = []
    if len(content) > MAX_CSV_BYTES:
        return {
            "valid": False,
            "errors": [{"row": None, "field": "file", "message": "CSV exceeds 1 MB"}],
            "jobs": [],
        }
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        if reader.fieldnames != COLUMNS and (
            reader.fieldnames is None
            or len(reader.fieldnames) != len(COLUMNS)
            or set(reader.fieldnames) != set(COLUMNS)
        ):
            return {
                "valid": False,
                "errors": [
                    {
                        "row": 1,
                        "field": "columns",
                        "message": f"Expected exactly: {', '.join(COLUMNS)}",
                    }
                ],
                "jobs": [],
            }
        seen = set()
        for number, row in enumerate(reader, start=2):
            if number > 51:
                errors.append({"row": number, "field": "file", "message": "Maximum 50 jobs"})
                break
            if None in row or any(v is None for v in row.values()):
                errors.append({"row": number, "field": "columns", "message": "Malformed CSV row"})
                continue
            values = {k: v.strip() for k, v in row.items()}
            for key in COLUMNS[1:]:
                if len(values[key]) <= 12 and re.fullmatch(r"\d+", values[key]):
                    values[key] = int(values[key])
            try:
                job = Job.model_validate(values)
                if job.job_id in seen:
                    errors.append({"row": number, "field": "job_id", "message": "Duplicate job ID"})
                seen.add(job.job_id)
                jobs.append(job)
            except ValidationError as exc:
                errors.extend(
                    {"row": number, "field": str(e["loc"][0]), "message": e["msg"]}
                    for e in exc.errors()
                )
        if not jobs and not errors:
            errors.append({"row": None, "field": "file", "message": "At least one job is required"})
        if not 1 <= machine_count <= 5:
            errors.append(
                {"row": None, "field": "machine_count", "message": "Must be between 1 and 5"}
            )
    except (UnicodeError, csv.Error) as exc:
        errors.append({"row": None, "field": "file", "message": f"Invalid UTF-8 CSV: {exc}"})
    warnings = [
        f"{j.job_id}: earliest completion exceeds due time"
        for j in jobs
        if j.release_time_min + j.processing_time_min > j.due_time_min
    ]
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "jobs": [j.model_dump() for j in jobs],
        "total_jobs": len(jobs),
    }


def jobs_csv(data: PlanningInput) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(j.model_dump() for j in data.jobs)
    return output.getvalue()
