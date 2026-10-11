from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

Method = Literal["fcfs", "edd", "milp"]
ExecutionState = Literal["queued", "running", "completed", "failed", "interrupted"]
SolverTermination = Literal[
    "optimal", "time_limit", "gap_limit", "infeasible", "unbounded", "error", "not_run"
]
ScheduleSource = Literal["heuristic", "cbc_incumbent", "heuristic_fallback"]
Profile = Literal["relaxed", "tight", "staggered"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Job(StrictModel):
    job_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    processing_time_min: StrictInt = Field(gt=0, le=10080)
    release_time_min: StrictInt = Field(ge=0, le=525600)
    due_time_min: StrictInt = Field(ge=0, le=1051200)
    priority_weight: StrictInt = Field(ge=1, le=10)


class PlanningInput(StrictModel):
    jobs: list[Job] = Field(min_length=1, max_length=50)
    machine_count: StrictInt = Field(ge=1, le=6)
    horizon_min: StrictInt | None = None

    @model_validator(mode="after")
    def consistent(self):
        if len({j.job_id for j in self.jobs}) != len(self.jobs):
            raise ValueError("Job IDs must be unique")
        safe = max(j.release_time_min for j in self.jobs) + sum(
            j.processing_time_min for j in self.jobs
        )
        if self.horizon_min is None:
            self.horizon_min = safe
        elif self.horizon_min != safe:
            raise ValueError("Horizon must equal max release plus total processing time")
        return self

    @property
    def job_hash(self) -> str:
        import json

        rows = [j.model_dump() for j in sorted(self.jobs, key=lambda j: j.job_id)]
        return sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

    @property
    def input_hash(self) -> str:
        return sha256(
            f"{self.job_hash}:{self.machine_count}:{self.horizon_min}".encode()
        ).hexdigest()


class Placement(StrictModel):
    job_id: str
    machine_code: str
    start_min: float
    completion_min: float


class KPI(StrictModel):
    total_jobs: int
    late_jobs: int
    total_weighted_tardiness: float
    makespan_min: float
    window_utilization: float
    span_utilization: float
    horizon_min: int
    machine_count: int


class ScheduleResult(StrictModel):
    method: Method
    placements: list[Placement]
    solver_status: SolverTermination = "not_run"
    result_source: ScheduleSource = "heuristic"
    proven_optimal: bool = False
    best_bound: float | None = None
    relative_gap: float | None = None
    solver_runtime_seconds: float = 0
    total_runtime_seconds: float = 0
    diagnostics: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    metrics: KPI | None = None


class GenerateRequest(StrictModel):
    name: str = Field(default="Synthetic production demo", min_length=1, max_length=100)
    job_count: StrictInt = Field(default=30, ge=1, le=50)
    machine_count: StrictInt = Field(default=4, ge=1, le=5)
    seed: StrictInt = Field(default=42, ge=0, le=2147483647)
    profile: Profile = "tight"
    confirmed: bool = False


class RunRequest(StrictModel):
    methods: list[Method] = Field(default_factory=lambda: ["milp"], min_length=1, max_length=3)
    time_limit_seconds: int = Field(default=60, ge=1, le=120)

    @model_validator(mode="after")
    def unique_methods(self):
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("Duplicate methods are not allowed")
        return self


class CompareRequest(StrictModel):
    run_ids: list[str] = Field(min_length=2, max_length=6)


class ExportBundleRequest(StrictModel):
    run_ids: list[str] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def distinct_runs(self):
        if len(set(self.run_ids)) != len(self.run_ids):
            raise ValueError("Choose distinct run IDs")
        return self


class CopilotRequest(StrictModel):
    scenario_id: str
    run_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)
