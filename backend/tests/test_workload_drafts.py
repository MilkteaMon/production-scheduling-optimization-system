import asyncio
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_api import wait_run

from opspilot.agents import workload_parser
from opspilot.api.main import create_app
from opspilot.config import Settings
from opspilot.domain.workload_drafts import WorkloadDraft
from opspilot.services.workload_drafts import review_workload


def draft(**updates):
    value = {
        "machine_count": 1,
        "time_basis": "minutes_from_start",
        "jobs": [
            {
                "label": "A",
                "job_id": "A",
                "processing_time_min": 10,
                "release_time_min": 0,
                "due_time_min": 100,
                "priority_weight": 1,
                "must_finish_on_time": False,
            },
            {
                "label": "B",
                "job_id": "B",
                "processing_time_min": 1,
                "release_time_min": 1,
                "due_time_min": 2,
                "priority_weight": 10,
                "must_finish_on_time": True,
            },
        ],
        "clarifications": [],
        "unsupported_requirements": [],
    }
    return WorkloadDraft.model_validate({**value, **updates})


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(
            Settings(
                _env_file=None, database_url=f"sqlite:///{tmp_path / 'drafts.db'}", ai_enabled=False
            )
        )
    ) as client:
        yield client


def confirmation(value=None, **changes):
    return {
        "description": "A and B on one machine",
        "draft": (value or draft()).model_dump(),
        "name": "Reviewed workload",
        "confirmation_id": str(uuid4()),
        "confirmed": True,
        "time_limit_seconds": 10,
        **changes,
    }


def test_missing_fields_stay_missing_and_never_form_a_plan():
    row = draft().jobs[0].model_copy(update={"processing_time_min": None, "due_time_min": None})
    value = draft(machine_count=None, jobs=[row.model_dump()])
    result = review_workload("订单 A", value)
    assert not result["ready"] and result["planning_input"] is None
    assert len(result["questions"]) == 3
    assert result["draft"]["jobs"][0]["processing_time_min"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("processing_time_min", 0),
        ("due_time_min", -1),
        ("release_time_min", -1),
        ("priority_weight", 11),
        ("job_id", "has spaces"),
    ],
)
def test_invalid_supplied_values_rejected_even_in_incomplete_rows(field, value):
    row = draft().jobs[0].model_dump()
    row["due_time_min"] = None
    row[field] = value
    result = review_workload("draft", draft(jobs=[row]))
    assert not result["ready"] and result["errors"] and result["planning_input"] is None


def test_defaults_and_suggested_ids_are_explicit_and_avoid_collisions():
    first = draft().jobs[0].model_dump()
    first.update(label="订单甲", job_id=None, release_time_min=None, priority_weight=None)
    second = draft().jobs[1].model_dump()
    second["job_id"] = "JOB-001"
    result = review_workload("订单甲和订单乙", draft(jobs=[first, second]))
    assert result["ready"] and len(result["assumptions"]) == 3
    assert result["planning_input"]["jobs"][0]["job_id"] == "JOB-002"
    assert result["planning_input"]["jobs"][0]["release_time_min"] == 0
    assert result["planning_input"]["jobs"][0]["priority_weight"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"time_basis": "needs_clarification"},
        {"clarifications": ["Which of the contradictory due times is correct?"]},
        {"unsupported_requirements": ["Machine-specific eligibility"]},
        {"machine_count": 6},
        {"jobs": []},
    ],
)
def test_ambiguity_unsupported_and_boundaries_block_confirmation(client, changes):
    value = draft(**changes)
    result = client.post(
        "/api/v1/natural-language/review",
        json={"description": "draft", "draft": value.model_dump()},
    )
    assert result.status_code == 200 and not result.json()["ready"]
    assert (
        client.post("/api/v1/natural-language/confirm", json=confirmation(value)).status_code == 422
    )
    assert client.get("/api/v1/datasets").json() == []


def test_creation_confirmed_only_persists_hard_rules_and_is_retry_safe(client):
    body = confirmation()
    assert (
        client.post(
            "/api/v1/natural-language/confirm", json={**body, "confirmed": False}
        ).status_code
        == 422
    )
    assert client.get("/api/v1/datasets").json() == []
    response = client.post("/api/v1/natural-language/confirm", json=body)
    assert response.status_code == 201, response.text
    dataset = response.json()
    base = dataset["scenarios"][0]
    assert base["must_finish_job_ids"] == ["B"] and dataset["source_kind"] == "natural_language"
    runs = client.get(f"/api/v1/scenarios/{base['id']}/runs").json()
    assert {r["method"] for r in runs} == {"fcfs", "edd", "milp"}
    complete = [wait_run(client, r["id"]) for r in runs]
    milp = next(r for r in complete if r["method"] == "milp")
    assert milp["has_valid_schedule"] and milp["metrics"]["total_weighted_tardiness"] == 0
    assert next(p for p in milp["placements"] if p["job_id"] == "B")["completion_min"] <= 2
    assert all(not r["has_valid_schedule"] for r in complete if r["method"] != "milp")
    duplicate = client.post("/api/v1/natural-language/confirm", json=body)
    assert duplicate.status_code == 201 and duplicate.json()["id"] == dataset["id"]
    assert len(client.get("/api/v1/datasets").json()) == 1
    assert len(client.get(f"/api/v1/scenarios/{base['id']}/runs").json()) == 3
    assert (
        client.post(
            "/api/v1/natural-language/confirm", json={**body, "name": "Changed"}
        ).status_code
        == 409
    )
    extra = client.post(f"/api/v1/datasets/{dataset['id']}/scenarios").json()
    assert extra["must_finish_job_ids"] == ["B"] and extra["machine_count"] == 2


def test_busy_queue_does_not_create_partial_workload(client):
    service = client.app.state.service
    service.pending = service.settings.queue_limit
    try:
        assert (
            client.post("/api/v1/natural-language/confirm", json=confirmation()).status_code == 429
        )
        assert client.get("/api/v1/datasets").json() == []
    finally:
        service.pending = 0


def test_duplicate_ids_fail_review():
    rows = [j.model_dump() for j in draft().jobs]
    rows[1]["job_id"] = "A"
    result = review_workload("draft", draft(jobs=rows))
    assert not result["ready"] and any("Duplicate" in e for e in result["errors"])


def test_parse_only_has_no_persistence_and_api_failure_is_sanitized(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        ai_enabled=True,
        ai_provider="openai_api",
        openai_api_key="test-secret",
        openai_model="gpt-6.1-sol",
        database_url=f"sqlite:///{tmp_path / 'parser.db'}",
    )

    async def parse(*args):
        return draft()

    monkeypatch.setattr(workload_parser, "parse_workload", parse)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/natural-language/parse", json={"description": "test"})
        assert response.status_code == 200 and response.json()["ready"]
        assert client.get("/api/v1/datasets").json() == []

        async def fail(*args):
            raise RuntimeError("test-secret")

        monkeypatch.setattr(workload_parser, "parse_workload", fail)
        response = client.post("/api/v1/natural-language/parse", json={"description": "test"})
        assert response.status_code == 502 and "test-secret" not in response.text
        assert client.get("/api/v1/datasets").json() == []


def test_disabled_parser_and_oversized_description_do_not_call_model(client, monkeypatch):
    async def unexpected(*args):
        raise AssertionError("No model call should occur")

    monkeypatch.setattr(workload_parser, "parse_workload", unexpected)
    assert (
        client.post("/api/v1/natural-language/parse", json={"description": "test"}).status_code
        == 503
    )
    assert (
        client.post("/api/v1/natural-language/parse", json={"description": "x" * 8001}).status_code
        == 422
    )


def test_subscription_parser_is_stateless_uses_low_and_no_native_tools(monkeypatch):
    calls = []

    async def execute(command, prompt):
        calls.append((command, prompt))
        return "\n".join(
            json.dumps(e)
            for e in [
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": draft().model_dump_json()},
                },
                {"type": "turn.completed", "usage": {}},
            ]
        )

    monkeypatch.setattr(workload_parser, "codex_executable", lambda path: "codex.exe")
    monkeypatch.setattr(workload_parser, "execute_cli", execute)
    value = asyncio.run(
        workload_parser.parse_workload(
            Settings(_env_file=None, ai_provider="codex_subscription", openai_model="gpt-6.1-sol"),
            "A and B",
        )
    )
    assert value == draft() and len(calls) == 1
    assert 'model_reasoning_effort="low"' in calls[0][0] and "--ephemeral" in calls[0][0]
    assert "Never invent" in calls[0][1]


def test_remote_subscription_parse_is_blocked_before_model(tmp_path, monkeypatch):
    async def unexpected(*args):
        raise AssertionError("Blocked remote client")

    monkeypatch.setattr(workload_parser, "parse_workload", unexpected)
    settings = Settings(
        _env_file=None,
        ai_enabled=True,
        ai_provider="codex_subscription",
        database_url=f"sqlite:///{tmp_path / 'remote.db'}",
    )
    with TestClient(
        create_app(settings), base_url="http://127.0.0.1:8000", client=("192.0.2.3", 50000)
    ) as client:
        assert (
            client.post("/api/v1/natural-language/parse", json={"description": "test"}).status_code
            == 403
        )
        assert (
            client.post("/api/v1/natural-language/confirm", json=confirmation()).status_code == 403
        )
