from typing import Any

from pydantic import BaseModel

from opspilot.domain.models import (
    KPI,
    ExecutionState,
    Job,
    Method,
    Placement,
    PlanningInput,
    ScheduleSource,
    SolverTermination,
)
from opspilot.domain.workload_drafts import WorkloadDraft


class HealthRead(BaseModel):
    status: str
    database_available: bool
    solver_available: bool
    ai_available: bool
    ai_enabled: bool
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_reasoning_effort: str | None = None
    version: str


class WorkloadPreviewRead(BaseModel):
    draft: WorkloadDraft
    ready: bool
    questions: list[str]
    errors: list[str]
    assumptions: list[str]
    unsupported_requirements: list[str]
    warnings: list[str]
    planning_input: PlanningInput | None


class MachineRead(BaseModel):
    id: str
    machine_code: str


class ScenarioRead(BaseModel):
    id: str
    dataset_id: str
    name: str
    kind: str
    parent_scenario_id: str | None
    machine_count: int
    machines: list[MachineRead]
    must_finish_job_ids: list[str] = []


class DatasetRead(BaseModel):
    id: str
    name: str
    source_kind: str
    seed: int | None
    generator_params: dict | None
    job_hash: str
    horizon_min: int
    created_at: str
    jobs: list[Job]
    scenarios: list[ScenarioRead]
    is_archived: bool
    is_test: bool


class DatasetVisibilityRequest(BaseModel):
    model_config = {"extra": "forbid"}
    is_archived: bool


class RunRead(BaseModel):
    id: str
    scenario_id: str
    method: Method
    input_hash: str
    model_version: str
    execution_state: ExecutionState
    solver_config: dict
    solver_status: SolverTermination
    result_source: ScheduleSource | None
    proven_optimal: bool
    has_valid_schedule: bool
    objective: float | None
    best_bound: float | None
    relative_gap: float | None
    solver_runtime_seconds: float
    total_runtime_seconds: float
    validation_errors: list[str]
    diagnostics: list[str]
    metrics: KPI | None
    created_at: str
    finished_at: str | None
    placements: list[Placement]
    must_finish_job_ids: list[str] = []


class QueuedRead(BaseModel):
    run_ids: list[str]


class ValidationErrorRead(BaseModel):
    row: int | None
    field: str
    message: str


class PreviewRead(BaseModel):
    valid: bool
    errors: list[ValidationErrorRead]
    jobs: list[Job]
    total_jobs: int = 0
    warnings: list[str] = []


class AnalyticsRead(BaseModel):
    run_id: str
    dataset_id: str
    scenario_id: str
    method: Method
    solver_status: SolverTermination
    result_source: ScheduleSource
    proven_optimal: bool
    rows: list[dict[str, Any]]


class ReductionRead(BaseModel):
    absolute_reduction: float
    percentage_reduction: float | None


class ComparedRun(RunRead):
    machine_count: int
    scenario_name: str
    constraints_differ: bool = False
    changes: dict[str, ReductionRead]
    window_utilization_change_pp: float
    span_utilization_change_pp: float


class ComparisonRead(BaseModel):
    baseline_run_id: str
    job_hash: str
    horizon_min: int
    runs: list[ComparedRun]


class FactRead(BaseModel):
    label: str
    value: str
    unit: str
    evidence_id: str


class EvidenceRead(BaseModel):
    evidence_id: str
    tool: str
    data: dict[str, Any]
    facts: list[dict[str, str]]


class CopilotRead(BaseModel):
    query_id: str
    facts: list[FactRead]
    interpretation: str | None
    tool_trace: list[EvidenceRead]
    pending_run_ids: list[str]
    fallback: bool
    proposal: "RulesPreviewRead | None" = None


class DeadlineRead(BaseModel):
    job_id: str
    due_time_min: int
    earliest_completion_min: int


class RulesPreviewRead(BaseModel):
    scenario_id: str
    dataset_id: str
    job_hash: str
    horizon_min: int
    input_hash: str
    base_machine_count: int
    machine_count: int
    job_ids: list[str]
    add_machine: bool
    deadlines: list[DeadlineRead]
    warnings: list[str]


class RulesAppliedRead(BaseModel):
    scenario: ScenarioRead
    run_ids: list[str]
    preview: RulesPreviewRead


class JobChangeRead(BaseModel):
    job_id: str
    priority_weight: int
    due_time_min: int
    baseline_completion_min: float
    completion_min: float
    baseline_tardiness_min: float
    tardiness_min: float
    weighted_tardiness_reduction: float
    must_finish_on_time: bool


class ExplanationRead(BaseModel):
    run_id: str
    baseline_run_id: str | None
    dataset_id: str
    scenario_id: str
    method: Method
    solver_status: SolverTermination
    result_source: ScheduleSource | None
    proven_optimal: bool
    has_valid_schedule: bool
    machine_count: int
    must_finish_job_ids: list[str]
    metrics: KPI | None
    baseline_metrics: KPI | None
    summary: list[str]
    changes: dict[str, ReductionRead]
    job_changes: list[JobChangeRead]
