import asyncio
import csv
import io
import itertools
import json
import time
import zipfile
from types import SimpleNamespace

import pulp
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from opspilot.agents.copilot import GroundedReply, ToolContext, render_reply
from opspilot.api.main import create_app
from opspilot.config import Settings
from opspilot.domain.models import Job, PlanningInput
from opspilot.scheduling.heuristics import schedule_heuristic
from opspilot.scheduling.milp import optimize
from opspilot.scheduling.validation import validate_schedule


def job(id, p, r, d, w=1):
    return Job(
        job_id=id, processing_time_min=p, release_time_min=r, due_time_min=d, priority_weight=w
    )


def waiting_data():
    return PlanningInput(
        jobs=[job("A", 10, 0, 100), job("B", 1, 1, 2, 10)],
        machine_count=1,
        must_finish_job_ids=["B"],
    )


def test_hard_deadline_requires_intentional_waiting_and_no_invalid_seed():
    data = waiting_data()
    for method in ["fcfs", "edd"]:
        baseline = schedule_heuristic(data, method)
        assert any("B: hard deadline" in e for e in validate_schedule(data, baseline.placements))
    result = optimize(data, 10)
    assert result.proven_optimal and result.result_source == "cbc_incumbent"
    assert result.metrics.total_weighted_tardiness == 0
    assert not validate_schedule(data, result.placements)
    assert next(p for p in result.placements if p.job_id == "B").completion_min == 2


def test_joint_capacity_infeasibility_and_extra_machine():
    data = PlanningInput(
        jobs=[job("A", 2, 0, 2), job("B", 2, 0, 2)], machine_count=1, must_finish_job_ids=["A", "B"]
    )
    result = optimize(data, 10)
    assert result.solver_status == "infeasible"
    assert not result.placements and result.metrics is None and result.result_source is None
    extra = optimize(data.model_copy(update={"machine_count": 2}), 10)
    assert extra.proven_optimal and extra.metrics.late_jobs == 0


@pytest.mark.parametrize("unavailable", [True, False])
def test_no_valid_fallback_without_feasible_incumbent(monkeypatch, unavailable):
    monkeypatch.setattr("opspilot.scheduling.milp.solver_available", lambda: not unavailable)
    monkeypatch.setattr(
        pulp.LpProblem,
        "solve",
        lambda *args: SimpleNamespace(
            status_str="TimeLimit",
            has_solution=False,
            best_bound=None,
            time=0.01,
            solver_version=None,
            objective=None,
        ),
    )
    result = optimize(waiting_data(), 1)
    assert not result.placements and result.metrics is None and result.result_source is None
    assert result.solver_status == ("error" if unavailable else "time_limit")
    assert not result.proven_optimal and result.relative_gap is None


def test_impossible_single_job_is_explained():
    result = optimize(
        PlanningInput(jobs=[job("A", 3, 4, 6)], machine_count=1, must_finish_job_ids=["A"]), 1
    )
    assert result.solver_status == "infeasible" and not result.placements
    assert "earliest completion 7" in result.diagnostics[0]
    with pytest.raises(ValueError, match="belong"):
        PlanningInput(jobs=[job("A", 1, 0, 1)], machine_count=1, must_finish_job_ids=["OUTSIDE"])


@settings(max_examples=12, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(1, 4),
            st.integers(0, 4),
            st.integers(1, 13),
            st.integers(1, 4),
            st.booleans(),
        ),
        min_size=1,
        max_size=6,
    ),
    st.integers(1, 2),
)
def test_constrained_milp_matches_independent_exhaustive_oracle(rows, machines):
    jobs = [job(f"J{i}", p, r, d, w) for i, (p, r, d, w, hard) in enumerate(rows)]
    hard = {f"J{i}" for i, row in enumerate(rows) if row[4]}
    data = PlanningInput(jobs=jobs, machine_count=machines, must_finish_job_ids=sorted(hard))
    best = float("inf")
    for assignment in itertools.product(range(machines), repeat=len(jobs)):
        groups = [[j for j, k in zip(jobs, assignment) if k == m] for m in range(machines)]
        for orders in itertools.product(*(itertools.permutations(g) for g in groups)):
            feasible, total = True, 0
            for order in orders:
                finish = 0
                for j in order:
                    finish = max(finish, j.release_time_min) + j.processing_time_min
                    if j.job_id in hard and finish > j.due_time_min:
                        feasible = False
                    total += max(0, finish - j.due_time_min) * j.priority_weight
            if feasible:
                best = min(best, total)
    result = optimize(data, 10)
    if best == float("inf"):
        assert result.solver_status == "infeasible" and not result.placements
    else:
        assert result.proven_optimal, result.diagnostics
        assert result.metrics.total_weighted_tardiness == best


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(
            Settings(
                database_url=f"sqlite:///{(tmp_path / 'rules.db').as_posix()}", ai_enabled=False
            )
        )
    ) as client:
        yield client


def dataset(client, impossible=False):
    text = "job_id,processing_time_min,release_time_min,due_time_min,priority_weight\n" + (
        "A,2,0,2,1\nB,2,0,2,1\n" if impossible else "A,10,0,100,1\nB,1,1,2,10\n"
    )
    response = client.post(
        "/api/v1/datasets/import",
        files={"file": ("jobs.csv", text.encode())},
        data={"confirmed": True, "machine_count": 1, "name": "Rule fixture"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait(client, id):
    for _ in range(150):
        run = client.get("/api/v1/runs/" + id).json()
        if run["execution_state"] not in ["queued", "running"]:
            return run
        time.sleep(0.05)
    raise AssertionError("Run did not finish")


def test_preview_confirmation_dedup_export_and_explanations(client):
    data = dataset(client)
    base = data["scenarios"][0]["id"]
    initial = [wait(client, r["id"]) for r in client.get(f"/api/v1/scenarios/{base}/runs").json()]
    body = {"job_ids": ["B"], "time_limit_seconds": 10}
    preview = client.post(f"/api/v1/scenarios/{base}/rules/preview", json=body)
    assert preview.status_code == 200 and preview.json()["deadlines"][0]["due_time_min"] == 2
    assert len(client.get(f"/api/v1/datasets/{data['id']}").json()["scenarios"]) == 1
    assert client.post(f"/api/v1/scenarios/{base}/rules", json=body).status_code == 422
    assert (
        client.post(
            f"/api/v1/scenarios/{base}/rules/preview", json={"job_ids": ["OUTSIDE"]}
        ).status_code
        == 422
    )
    applied = client.post(
        f"/api/v1/scenarios/{base}/rules", json={**body, "confirmed": True}
    ).json()
    runs = [wait(client, id) for id in applied["run_ids"]]
    milp = next(r for r in runs if r["method"] == "milp")
    assert (
        milp["has_valid_schedule"]
        and milp["proven_optimal"]
        and milp["metrics"]["total_weighted_tardiness"] == 0
    )
    assert all(
        not r["has_valid_schedule"] and r["execution_state"] == "failed"
        for r in runs
        if r["method"] != "milp"
    )
    repeated = client.post(
        f"/api/v1/scenarios/{base}/rules", json={**body, "confirmed": True}
    ).json()
    assert (
        repeated["scenario"]["id"] == applied["scenario"]["id"]
        and repeated["run_ids"] == applied["run_ids"]
    )
    for r in initial:
        assert client.get("/api/v1/runs/" + r["id"]).json() == r
    explanation = client.get(
        f"/api/v1/runs/{milp['id']}/explanation", params={"baseline_run_id": initial[0]["id"]}
    ).json()
    assert explanation["changes"]["total_weighted_tardiness"]["absolute_reduction"] == 90
    assert sum(row["weighted_tardiness_reduction"] for row in explanation["job_changes"]) == 90
    comparison = client.post(
        "/api/v1/comparisons", json={"run_ids": [initial[0]["id"], milp["id"]]}
    ).json()
    assert comparison["runs"][1]["constraints_differ"]
    bundle = client.post("/api/v1/exports/power-bi", json={"run_ids": [milp["id"]]})
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["runs"][0]["must_finish_job_ids"] == ["B"]
        records = list(csv.DictReader(io.StringIO(archive.read("schedule.csv").decode())))
        assert next(r for r in records if r["job_id"] == "B")["must_finish_on_time"] == "True"
    assert (
        client.post(
            "/api/v1/exports/power-bi",
            json={"run_ids": [next(r["id"] for r in runs if r["method"] == "fcfs")]},
        ).status_code
        == 409
    )


def test_infeasible_run_persists_no_invalid_schedule_and_extra_inherits_rules(client):
    data = dataset(client, True)
    base = data["scenarios"][0]["id"]
    response = client.post(
        f"/api/v1/scenarios/{base}/rules",
        json={"job_ids": ["A", "B"], "confirmed": True, "time_limit_seconds": 10},
    ).json()
    milp = next(
        wait(client, id)
        for id in response["run_ids"]
        if client.get("/api/v1/runs/" + id).json()["method"] == "milp"
    )
    assert milp["execution_state"] == "completed" and milp["solver_status"] == "infeasible"
    assert not milp["has_valid_schedule"] and not milp["placements"] and milp["metrics"] is None
    explain = client.get(f"/api/v1/runs/{milp['id']}/explanation").json()
    assert "No schedule can meet" in explain["summary"][0]
    extra = client.post(
        f"/api/v1/scenarios/{response['scenario']['id']}/rules",
        json={"add_machine": True, "confirmed": True, "time_limit_seconds": 10},
    ).json()
    assert (
        extra["scenario"]["must_finish_job_ids"] == ["A", "B"]
        and extra["scenario"]["machine_count"] == 2
    )
    assert all(wait(client, id)["has_valid_schedule"] for id in extra["run_ids"])


def test_agent_proposal_is_scoped_deduplicated_and_never_computes(client):
    data = dataset(client)
    service = client.app.state.service
    context = ToolContext(service, data["scenarios"][0]["id"], None)
    context.invoke("propose_deadline_constraints", {"job_ids": ["B"], "add_machine": True})
    context.invoke("propose_deadline_constraints", {"job_ids": ["B"], "add_machine": True})
    assert context.proposal["machine_count"] == 2
    assert len(service.dataset_detail(data["id"])["scenarios"]) == 1
    response = render_reply(GroundedReply(selections=[], interpretation="constraints"), context)
    assert response["proposal"]["job_ids"] == ["B"] and response["pending_run_ids"] == []
    with pytest.raises(ValueError, match="Confirm"):
        context.invoke("run_schedule_optimization", {})
    with pytest.raises(Exception, match="Unknown"):
        context.invoke("propose_deadline_constraints", {"job_ids": ["OUTSIDE"]})


def test_mocked_ai_request_returns_confirmable_proposal(client, monkeypatch):
    from opspilot.agents.copilot import answer_query
    from opspilot.domain.models import CopilotRequest

    data = dataset(client)
    scenario = data["scenarios"][0]["id"]

    async def runner(agent, question, *, context, max_turns, run_config):
        assert agent.model_settings.reasoning.effort == "low"
        context.invoke("propose_deadline_constraints", {"job_ids": ["B"], "add_machine": False})
        return SimpleNamespace(
            final_output=GroundedReply(selections=[], interpretation="constraints")
        )

    monkeypatch.setattr("opspilot.agents.copilot.Runner.run", runner)
    response = asyncio.run(
        answer_query(
            client.app.state.service,
            Settings(_env_file=None, openai_api_key="mock-key", openai_model="gpt-6.1-sol"),
            CopilotRequest(scenario_id=scenario, question="B必须按时完成"),
        )
    )
    assert response["proposal"]["job_ids"] == ["B"]
    assert len(client.app.state.service.dataset_detail(data["id"])["scenarios"]) == 1
