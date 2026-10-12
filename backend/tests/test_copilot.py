import pytest

from opspilot.agents.copilot import TOOLS, FactSelection, GroundedReply, ToolContext, render_reply


class FakeService:
    def __init__(self):
        from opspilot.domain.models import GenerateRequest
        from opspilot.services.data import generate_data

        self.data = generate_data(GenerateRequest(job_count=3, machine_count=1))
        self.queued = 0

    def scenario_input(self, id):
        return self.data, {"id": id, "dataset_id": "other" if id == "other" else "dataset"}

    def get_run(self, id):
        return {
            "id": id,
            "scenario_id": "other" if id == "outside" else "base",
            "method": "edd",
            "metrics": {
                "late_jobs": 2,
                "total_weighted_tardiness": 91,
                "makespan_min": 100,
                "window_utilization": 0.4,
                "span_utilization": 0.5,
            },
        }

    def queue_runs(self, id, request):
        self.queued += 1
        return {"run_ids": ["queued"]}


def test_tools_allowlist_and_scope():
    assert {t.name for t in TOOLS} == {
        "get_production_summary",
        "get_late_orders",
        "get_machine_utilization",
        "run_schedule_optimization",
        "get_schedule_run",
        "compare_scheduling_methods",
        "simulate_additional_machine",
        "propose_deadline_constraints",
        "get_schedule_explanation",
    }
    context = ToolContext(FakeService(), "base", "selected")
    with pytest.raises(ValueError, match="outside"):
        context.invoke("get_schedule_run", {"run_id": "outside"})
    with pytest.raises(ValueError, match="not allowed"):
        context.invoke("execute_sql", {})
    with pytest.raises(ValueError, match="selected scenario"):
        ToolContext(FakeService(), "extra", "selected")
    with pytest.raises(ValueError, match="two to six"):
        context.invoke("compare_scheduling_methods", {"run_ids": [str(i) for i in range(7)]})


def test_computation_deduplicates_and_limits():
    service = FakeService()
    context = ToolContext(service, "base", None)
    assert context.invoke("run_schedule_optimization", {}) == context.invoke(
        "run_schedule_optimization", {}
    )
    assert service.queued == 1
    with pytest.raises(ValueError, match="Only one"):
        context.invoke("simulate_additional_machine", {})
    for _ in range(3):
        context.invoke("get_production_summary", {})
    with pytest.raises(ValueError, match="Maximum six"):
        context.invoke("get_production_summary", {})


def test_failed_computation_still_consumes_single_request(monkeypatch):
    service = FakeService()
    context = ToolContext(service, "base", None)

    def busy(*args):
        raise RuntimeError("Queue full")

    monkeypatch.setattr(service, "queue_runs", busy)
    with pytest.raises(RuntimeError, match="Queue full"):
        context.invoke("run_schedule_optimization", {})
    with pytest.raises(ValueError, match="Only one"):
        context.invoke("simulate_additional_machine", {})


def test_numerical_output_only_comes_from_evidence():
    context = ToolContext(FakeService(), "base", "selected")
    event = context.invoke("get_production_summary", {})
    reply = GroundedReply(
        selections=[
            FactSelection(evidence_id=event["evidence_id"], fact_keys=["total_weighted_tardiness"])
        ],
        interpretation="priority",
    )
    result = render_reply(reply, context)
    assert result["facts"][0]["value"] == "91"
    assert not result["fallback"]
    invalid = reply.model_copy(
        update={"selections": [FactSelection(evidence_id="invented", fact_keys=["fake_999"])]}
    )
    result = render_reply(invalid, context)
    assert result["fallback"]
    assert all(f["evidence_id"] == event["evidence_id"] for f in result["facts"])


def test_empty_agent_evidence_has_deterministic_fallback():
    context = ToolContext(FakeService(), "base", None)
    result = render_reply(GroundedReply(selections=[], interpretation="none"), context)
    assert result["fallback"] and result["facts"][0]["value"] == "3"
    assert result["tool_trace"][0]["tool"] == "deterministic_fallback"


def test_copilot_percentage_template_preserves_zero_baseline(monkeypatch):
    service = FakeService()
    run = service.get_run("base1")
    run["changes"] = {
        "total_weighted_tardiness": {"absolute_reduction": 0, "percentage_reduction": None}
    }
    monkeypatch.setattr(service, "compare", lambda ids: {"runs": [run, run]}, raising=False)
    context = ToolContext(service, "base", None)
    event = context.invoke("compare_scheduling_methods", {"run_ids": ["base1", "base2"]})
    percentages = [fact for fact in event["facts"] if fact["key"].endswith("reduction_percent")]
    assert len(percentages) == 2 and all(fact["value"] == "N/A" for fact in percentages)


def test_mocked_agent_response_is_persisted_without_remote_calls(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from opspilot.api.main import create_app
    from opspilot.config import Settings
    from opspilot.persistence.models import CopilotQuery

    async def fake_runner(agent, question, *, context, max_turns, run_config):
        assert agent.model.model == "explicit-test-model"
        assert agent.model_settings.to_json_dict()["reasoning"]["effort"] == "low"
        assert run_config.tracing_disabled and max_turns == 8
        event = context.invoke("get_production_summary", {})
        return SimpleNamespace(
            final_output=GroundedReply(
                selections=[
                    FactSelection(evidence_id=event["evidence_id"], fact_keys=["total_jobs"])
                ],
                interpretation="lateness",
            )
        )

    monkeypatch.setattr("opspilot.agents.copilot.Runner.run", fake_runner)
    app = create_app(
        Settings(
            _env_file=None,
            ai_provider="openai_api",
            database_url=f"sqlite:///{(tmp_path / 'agent.db').as_posix()}",
            ai_enabled=True,
            openai_api_key="mock-not-a-real-key",
            openai_model="explicit-test-model",
        )
    )
    with TestClient(app) as client:
        dataset = client.post(
            "/api/v1/datasets/generate", json={"confirmed": True, "job_count": 3}
        ).json()
        response = client.post(
            "/api/v1/copilot/query",
            json={
                "scenario_id": dataset["scenarios"][0]["id"],
                "question": "How many production jobs?",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["facts"][0]["value"] == "3" and not payload["fallback"]
        assert payload["tool_trace"][0]["data"]["context"]["dataset_id"] == dataset["id"]
        with app.state.service.sessions() as session:
            saved = session.scalar(select(CopilotQuery))
            assert saved.response == payload and saved.error is None
