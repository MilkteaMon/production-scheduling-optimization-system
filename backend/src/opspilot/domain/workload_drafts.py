from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt

from opspilot.domain.models import StrictModel


class DraftJob(StrictModel):
    label: str | None = Field(max_length=100)
    job_id: str | None = Field(max_length=64)
    processing_time_min: StrictInt | None
    release_time_min: StrictInt | None
    due_time_min: StrictInt | None
    priority_weight: StrictInt | None
    must_finish_on_time: StrictBool


class WorkloadDraft(StrictModel):
    machine_count: StrictInt | None
    time_basis: Literal["minutes_from_start", "needs_clarification"]
    jobs: list[DraftJob] = Field(max_length=50)
    clarifications: list[str] = Field(max_length=10)
    unsupported_requirements: list[str] = Field(max_length=10)


class WorkloadDescriptionRequest(StrictModel):
    description: str = Field(min_length=1, max_length=8000)


class WorkloadReviewRequest(WorkloadDescriptionRequest):
    draft: WorkloadDraft


class WorkloadConfirmRequest(WorkloadReviewRequest):
    name: str = Field(min_length=1, max_length=100)
    confirmation_id: UUID
    confirmed: StrictBool = False
    time_limit_seconds: StrictInt = Field(default=60, ge=1, le=120)
