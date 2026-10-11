from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id():
    return str(uuid4())


def now():
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    source_kind: Mapped[str] = mapped_column(String)
    seed: Mapped[int | None] = mapped_column(Integer)
    generator_params: Mapped[dict | None] = mapped_column(JSON)
    job_hash: Mapped[str] = mapped_column(String)
    horizon_min: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String, default=now)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class JobRecord(Base):
    __tablename__ = "jobs"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processing_time_min: Mapped[int] = mapped_column(Integer)
    release_time_min: Mapped[int] = mapped_column(Integer)
    due_time_min: Mapped[int] = mapped_column(Integer)
    priority_weight: Mapped[int] = mapped_column(Integer)


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (UniqueConstraint("dataset_id", "kind"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    parent_scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenarios.id"))
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)


class Machine(Base):
    __tablename__ = "machines"
    __table_args__ = (UniqueConstraint("scenario_id", "machine_code"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), index=True)
    machine_code: Mapped[str] = mapped_column(String)


class ScheduleRun(Base):
    __tablename__ = "schedule_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), index=True)
    method: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String)
    model_version: Mapped[str] = mapped_column(String, default="1.0")
    execution_state: Mapped[str] = mapped_column(String, default="queued")
    solver_config: Mapped[dict] = mapped_column(JSON)
    solver_status: Mapped[str] = mapped_column(String, default="not_run")
    result_source: Mapped[str | None] = mapped_column(String)
    proven_optimal: Mapped[bool] = mapped_column(Boolean, default=False)
    has_valid_schedule: Mapped[bool] = mapped_column(Boolean, default=False)
    objective: Mapped[float | None] = mapped_column(Float)
    best_bound: Mapped[float | None] = mapped_column(Float)
    relative_gap: Mapped[float | None] = mapped_column(Float)
    solver_runtime_seconds: Mapped[float] = mapped_column(Float, default=0)
    total_runtime_seconds: Mapped[float] = mapped_column(Float, default=0)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    diagnostics: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String, default=now)
    finished_at: Mapped[str | None] = mapped_column(String)


class ScheduleItem(Base):
    __tablename__ = "schedule_items"
    __table_args__ = (
        ForeignKeyConstraint(["dataset_id", "job_id"], ["jobs.dataset_id", "jobs.job_id"]),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("schedule_runs.id"), primary_key=True)
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"))
    start_min: Mapped[int] = mapped_column(Integer)
    completion_min: Mapped[int] = mapped_column(Integer)


class CopilotQuery(Base):
    __tablename__ = "copilot_queries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("schedule_runs.id"))
    question: Mapped[str] = mapped_column(String)
    response: Mapped[dict | None] = mapped_column(JSON)
    tool_trace: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)
