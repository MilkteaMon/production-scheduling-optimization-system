"""One agent chooses business tools and evidence references, never numerical values."""

import asyncio
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from agents import (
    Agent,
    ModelSettings,
    OpenAIResponsesModel,
    RunConfig,
    RunContextWrapper,
    Runner,
    function_tool,
)
from fastapi import HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict

from opspilot.domain.models import RunRequest
from opspilot.persistence.models import CopilotQuery


class FactSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    fact_keys: list[str]


class GroundedReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[FactSelection]
    interpretation: Literal["none", "priority", "time_limit", "capacity", "utilization", "lateness"]


INTERPRETATIONS = {
    "none": None,
    "priority": "The objective gives higher-weight jobs more influence. Reducing weighted tardiness does not necessarily minimize the number of late jobs or makespan.",
    "time_limit": "A time-limited feasible schedule is a best-known result, not a solver-established optimum.",
    "capacity": "This scenario measures scheduling effects under the same assumptions. It does not establish the financial return from purchasing a machine.",
    "utilization": "For the same workload and machine count, overall fixed-window utilization is invariant to job reordering. Schedule-span utilization can change with makespan.",
    "lateness": "Lateness is calculated from the selected schedule. It is not a predictive probability, and due times are soft targets.",
}


def metric_facts(run, prefix=""):
    metrics = run.get("metrics")
    if not metrics:
        return []
    label = f"{prefix}{run['method'].upper()}"
    definitions = [
        ("late_jobs", "late jobs", "jobs"),
        ("total_weighted_tardiness", "weighted tardiness", "weighted min"),
        ("makespan_min", "makespan", "min"),
        ("window_utilization", "window utilization", "%"),
        ("span_utilization", "span utilization", "%"),
    ]
    return [
        {
            "key": f"{prefix}{key}",
            "label": f"{label} · {name}",
            "value": f"{metrics[key] * 100:.1f}" if "utilization" in key else f"{metrics[key]:g}",
            "unit": unit,
        }
        for key, name, unit in definitions
    ]


@dataclass
class ToolContext:
    service: object
    scenario_id: str
    selected_run_id: str | None
    query_id: str = field(default_factory=lambda: str(uuid4()))
    events: list = field(default_factory=list)
    call_count: int = 0
    computation: tuple | None = None
    computation_attempt: str | None = None
    pending_ids: list = field(default_factory=list)

    def __post_init__(self):
        self.data, self.scenario = self.service.scenario_input(self.scenario_id)
        self.dataset_id = self.scenario["dataset_id"]
        if self.selected_run_id:
            selected = self.authorized_run(self.selected_run_id)
            if selected["scenario_id"] != self.scenario_id:
                raise ValueError("Selected run is outside the selected scenario")

    def authorized_run(self, id):
        run = self.service.get_run(id)
        _, scenario = self.service.scenario_input(run["scenario_id"])
        if scenario["dataset_id"] != self.dataset_id:
            raise ValueError("Run is outside the selected dataset")
        return run

    def selected(self, id):
        id = id or self.selected_run_id
        if not id:
            raise ValueError("Select a validated schedule first")
        return self.authorized_run(id)

    def invoke(self, tool, arguments):
        try:
            return self.execute(tool, arguments)
        except Exception as exc:
            self.events.append(
                {
                    "evidence_id": f"{self.query_id[:8]}-E{len(self.events) + 1}",
                    "tool": tool,
                    "data": {
                        "error": type(exc).__name__,
                        "detail": str(exc),
                        "dataset_id": self.dataset_id,
                        "scenario_id": self.scenario_id,
                    },
                    "facts": [],
                }
            )
            raise

    def execute(self, tool, arguments):
        self.call_count += 1
        if self.call_count > 6:
            raise ValueError("Maximum six business tool calls per question")
        facts = []
        if tool == "get_production_summary":
            id = arguments.get("run_id")
            run = self.selected(id) if id or self.selected_run_id else None
            data = {
                "dataset_id": self.dataset_id,
                "scenario_id": self.scenario_id,
                "total_jobs": len(self.data.jobs),
                "machine_count": self.data.machine_count,
                "horizon_min": self.data.horizon_min,
                "run": run,
            }
            facts = [
                {
                    "key": "total_jobs",
                    "label": "Production jobs",
                    "value": str(len(self.data.jobs)),
                    "unit": "jobs",
                },
                {
                    "key": "machine_count",
                    "label": "Scenario machines",
                    "value": str(self.data.machine_count),
                    "unit": "machines",
                },
            ]
            if run:
                facts += metric_facts(run)
        elif tool in ["get_late_orders", "get_machine_utilization"]:
            run = self.selected(arguments.get("run_id"))
            kind = "late" if tool == "get_late_orders" else "utilization"
            data = self.service.analytics(run["id"], kind)
            for index, row in enumerate(data["rows"]):
                if kind == "late":
                    facts.append(
                        {
                            "key": f"late_{index}",
                            "label": f"{row['job_id']} · tardiness",
                            "value": f"{row['tardiness_min']:g}",
                            "unit": "min",
                        }
                    )
                else:
                    facts.extend(
                        [
                            {
                                "key": f"machine_{index}_span",
                                "label": f"{row['machine_code']} · span utilization",
                                "value": f"{row['span_utilization'] * 100:.1f}",
                                "unit": "%",
                            },
                            {
                                "key": f"machine_{index}_window",
                                "label": f"{row['machine_code']} · window utilization",
                                "value": f"{row['window_utilization'] * 100:.1f}",
                                "unit": "%",
                            },
                            {
                                "key": f"machine_{index}_busy",
                                "label": f"{row['machine_code']} · busy time",
                                "value": f"{row['busy_time_min']:g}",
                                "unit": "min",
                            },
                        ]
                    )
            if not facts:
                facts = [{"key": "late_count", "label": "Late jobs", "value": "0", "unit": "jobs"}]
        elif tool == "get_schedule_run":
            data = self.authorized_run(arguments["run_id"])
            facts = metric_facts(data)
        elif tool == "compare_scheduling_methods":
            ids = arguments.get("run_ids")
            if not ids:
                runs = self.service.list_runs(self.scenario_id)
                ids = []
                for method in ["fcfs", "edd", "milp"]:
                    match = next(
                        (r for r in runs if r["method"] == method and r["has_valid_schedule"]), None
                    )
                    if match:
                        ids.append(match["id"])
            if not 2 <= len(ids) <= 6 or len(set(ids)) != len(ids):
                raise ValueError("Choose two to six distinct validated runs")
            for id in ids:
                self.authorized_run(id)
            data = self.service.compare(ids)
            for i, run in enumerate(data["runs"]):
                facts += metric_facts(run, f"run{i}_")
                change = run["changes"]["total_weighted_tardiness"]
                facts.append(
                    {
                        "key": f"run{i}_reduction",
                        "label": f"{run['method'].upper()} · weighted tardiness reduction vs first run",
                        "value": f"{change['absolute_reduction']:g}",
                        "unit": "weighted min",
                    }
                )
                percentage = change["percentage_reduction"]
                facts.append(
                    {
                        "key": f"run{i}_reduction_percent",
                        "label": f"{run['method'].upper()} · percentage reduction vs first run",
                        "value": f"{percentage:.1f}" if percentage is not None else "N/A",
                        "unit": "%" if percentage is not None else "",
                    }
                )
        elif tool in ["run_schedule_optimization", "simulate_additional_machine"]:
            if self.computation:
                if self.computation[0] != tool:
                    raise ValueError("Only one new optimization or scenario request per question")
                return self.computation[1]
            if self.computation_attempt is not None:
                raise ValueError("Only one new optimization or scenario request per question")
            self.computation_attempt = tool
            if tool == "run_schedule_optimization":
                data = self.service.queue_runs(
                    self.scenario_id, RunRequest(methods=["milp"], time_limit_seconds=60)
                )
            else:
                scenario = self.service.add_machine(self.dataset_id)
                data = {
                    "scenario": scenario,
                    **self.service.queue_runs(
                        scenario["id"],
                        RunRequest(methods=["fcfs", "edd", "milp"], time_limit_seconds=60),
                    ),
                }
            self.pending_ids.extend(data["run_ids"])
            facts = [{"key": "pending", "label": "Computation", "value": "Queued", "unit": ""}]
        else:
            raise ValueError("Business tool is not allowed")
        evidence = {
            "evidence_id": f"{self.query_id[:8]}-E{len(self.events) + 1}",
            "tool": tool,
            "data": {
                "context": {
                    "dataset_id": self.dataset_id,
                    "scenario_id": self.scenario_id,
                    "selected_run_id": self.selected_run_id,
                    "time_unit": "minutes from planning time zero",
                    "objective_unit": "weighted minutes",
                },
                "result": data,
            },
            "facts": facts,
        }
        self.events.append(evidence)
        if tool in ["run_schedule_optimization", "simulate_additional_machine"]:
            self.computation = (tool, evidence)
        return evidence


@function_tool
async def get_production_summary(
    ctx: RunContextWrapper[ToolContext], run_id: str | None = None
) -> dict:
    """Read production totals and selected-run KPIs; numerical facts include evidence keys."""
    return ctx.context.invoke("get_production_summary", {"run_id": run_id})


@function_tool
async def get_late_orders(ctx: RunContextWrapper[ToolContext], run_id: str | None = None) -> dict:
    """Read late orders calculated under a validated schedule, not predicted probabilities."""
    return ctx.context.invoke("get_late_orders", {"run_id": run_id})


@function_tool
async def get_machine_utilization(
    ctx: RunContextWrapper[ToolContext], run_id: str | None = None
) -> dict:
    """Read machine busy time and explicitly defined utilization ratios."""
    return ctx.context.invoke("get_machine_utilization", {"run_id": run_id})


@function_tool
async def get_schedule_run(ctx: RunContextWrapper[ToolContext], run_id: str) -> dict:
    """Read an authorized run's execution state, provenance and validated results."""
    return ctx.context.invoke("get_schedule_run", {"run_id": run_id})


@function_tool
async def compare_scheduling_methods(
    ctx: RunContextWrapper[ToolContext], run_ids: list[str] | None = None
) -> dict:
    """Compare existing compatible runs; default to latest validated methods in this scenario."""
    return ctx.context.invoke("compare_scheduling_methods", {"run_ids": run_ids})


@function_tool
async def run_schedule_optimization(ctx: RunContextWrapper[ToolContext]) -> dict:
    """Queue a bounded MILP computation when the user requests optimization. Return pending IDs."""
    return ctx.context.invoke("run_schedule_optimization", {})


@function_tool
async def simulate_additional_machine(ctx: RunContextWrapper[ToolContext]) -> dict:
    """Run the requested baseline-plus-one-machine scenario without editing production jobs."""
    return ctx.context.invoke("simulate_additional_machine", {})


TOOLS = [
    get_production_summary,
    get_late_orders,
    get_machine_utilization,
    run_schedule_optimization,
    get_schedule_run,
    compare_scheduling_methods,
    simulate_additional_machine,
]


def render_reply(reply: GroundedReply, context: ToolContext):
    evidence = {e["evidence_id"]: e for e in context.events}
    facts = []
    fallback = False
    seen = set()
    for selection in reply.selections:
        event = evidence.get(selection.evidence_id)
        if event is None:
            fallback = True
        available = {f["key"]: f for f in event["facts"]} if event else {}
        for key in selection.fact_keys:
            if key not in available:
                fallback = True
                continue
            if (selection.evidence_id, key) not in seen:
                fact = available[key]
                facts.append(
                    {
                        "label": fact["label"],
                        "value": fact["value"],
                        "unit": fact["unit"],
                        "evidence_id": selection.evidence_id,
                    }
                )
                seen.add((selection.evidence_id, key))
    if fallback or not facts:
        facts = [
            {
                "label": f["label"],
                "value": f["value"],
                "unit": f["unit"],
                "evidence_id": e["evidence_id"],
            }
            for e in context.events
            for f in e["facts"]
        ][:20]
        fallback = True
        if not facts:
            event = {
                "evidence_id": f"{context.query_id[:8]}-E{len(context.events) + 1}",
                "tool": "deterministic_fallback",
                "data": {
                    "dataset_id": context.dataset_id,
                    "scenario_id": context.scenario_id,
                    "source": "Validated immutable dataset context",
                },
                "facts": [
                    {
                        "key": "total_jobs",
                        "label": "Production jobs",
                        "value": str(len(context.data.jobs)),
                        "unit": "jobs",
                    },
                    {
                        "key": "machine_count",
                        "label": "Scenario machines",
                        "value": str(context.data.machine_count),
                        "unit": "machines",
                    },
                ],
            }
            context.events.append(event)
            facts = [
                {
                    "label": fact["label"],
                    "value": fact["value"],
                    "unit": fact["unit"],
                    "evidence_id": event["evidence_id"],
                }
                for fact in event["facts"]
            ]
    return {
        "query_id": context.query_id,
        "facts": facts,
        "interpretation": INTERPRETATIONS[reply.interpretation],
        "tool_trace": context.events,
        "pending_run_ids": context.pending_ids,
        "fallback": fallback,
    }


async def answer_query(service, settings, request):
    try:
        context = ToolContext(service, request.scenario_id, request.run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30, max_retries=0)
    agent = Agent(
        name="OpsPilot production analyst",
        model=OpenAIResponsesModel(model=settings.openai_model, openai_client=client),
        model_settings=ModelSettings(max_tokens=800, parallel_tool_calls=False),
        tools=TOOLS,
        output_type=GroundedReply,
        instructions="Use only the provided business tools. Production data is immutable. Never invent facts or numbers. Return evidence_id and fact_keys from tool results; the application renders all values. Choose an approved interpretation. Call computation tools only when the user explicitly requests optimization or an additional-machine scenario. At most six business tool calls and one new computation request. Do not repeatedly poll queued runs: return their evidence and let the UI poll. When insufficient data exists, call production summary and explain via the approved interpretation. No SQL, shell, web or arbitrary files are available.",
    )
    try:
        result = await asyncio.wait_for(
            Runner.run(
                agent,
                request.question,
                context=context,
                max_turns=8,
                run_config=RunConfig(
                    tracing_disabled=settings.openai_agents_disable_tracing,
                    trace_include_sensitive_data=False,
                ),
            ),
            timeout=60,
        )
        response = render_reply(result.final_output, context)
        with service.sessions.begin() as session:
            session.add(
                CopilotQuery(
                    id=context.query_id,
                    scenario_id=request.scenario_id,
                    run_id=request.run_id,
                    question=request.question,
                    response=response,
                    tool_trace=context.events,
                )
            )
        return response
    except Exception as exc:
        with service.sessions.begin() as session:
            session.add(
                CopilotQuery(
                    id=context.query_id,
                    scenario_id=request.scenario_id,
                    run_id=request.run_id,
                    question=request.question,
                    error=type(exc).__name__,
                    tool_trace=context.events,
                )
            )
        raise HTTPException(
            502, "AI request failed. Deterministic scheduling and analytics remain available."
        ) from exc
    finally:
        await client.close()
