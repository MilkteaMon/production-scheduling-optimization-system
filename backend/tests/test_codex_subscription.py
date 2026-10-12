import ast
import asyncio
import json
import threading

import pytest
from agents import Agent, ModelSettings, RunConfig, Runner
from fastapi.testclient import TestClient
from openai.types.shared import Reasoning
from test_copilot import FakeService

from opspilot.agents import codex_subscription as transport
from opspilot.agents.copilot import TOOLS, GroundedReply, ToolContext, render_reply
from opspilot.api.main import create_app
from opspilot.config import Settings


def cli_events(decision):
    return "\n".join(
        json.dumps(event)
        for event in [
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps(decision)},
            },
            {"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 10}},
        ]
    )


def test_local_cli_enforces_subscription_model_and_scope():
    command = transport.cli_command("codex.exe", "gpt-6.1-sol", "isolated", "schema.json")
    assert command[command.index("--model") + 1] == "gpt-6.1-sol"
    assert 'model_reasoning_effort="low"' in command
    assert 'forced_login_method="chatgpt"' in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in command and "--ignore-user-config" in command
    for feature in ("shell_tool", "unified_exec", "apps", "plugins", "multi_agent", "memories"):
        assert any(command[i : i + 2] == ["--disable", feature] for i in range(len(command)))


@pytest.mark.parametrize("item", ["command_execution", "mcp_tool_call", "file_change"])
def test_unexpected_native_tools_are_rejected(item):
    with pytest.raises(RuntimeError, match="tool activity"):
        transport.decode_events(json.dumps({"type": "item.completed", "item": {"type": item}}))


def test_cli_uses_stdin_without_copying_api_credentials(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "private-api-key")
    monkeypatch.setenv("CODEX_API_KEY", "other-key")

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            captured.update(command=command, **kwargs)

        def communicate(self, text):
            captured["prompt"] = text
            return "reply", "diagnostics"

    monkeypatch.setattr(transport.subprocess, "Popen", Process)
    assert asyncio.run(transport.execute_cli(["official-codex", "-"], "user request")) == "reply"
    assert captured["prompt"] == "user request"
    assert "user request" not in captured["command"]
    assert "OPENAI_API_KEY" not in captured["env"] and "CODEX_API_KEY" not in captured["env"]
    assert "shell" not in captured or captured["shell"] is False


def test_timed_out_cli_is_killed(monkeypatch):
    stopped = threading.Event()

    class Process:
        returncode = None

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, text):
            assert stopped.wait(2)
            return "", ""

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -1
            stopped.set()

    monkeypatch.setattr(transport.subprocess, "Popen", Process)
    monkeypatch.setattr(transport, "CLI_TIMEOUT_SECONDS", 0.02)
    with pytest.raises(TimeoutError):
        asyncio.run(transport.execute_cli(["official-codex"], "request"))
    assert stopped.is_set()


def test_subscription_model_runs_existing_business_tools_and_grounded_rendering(monkeypatch):
    prompts = []

    async def fake_cli(command, prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            decision = {
                "kind": "tool",
                "tool": "get_production_summary",
                "arguments": '{"run_id":null}',
                "reply": {"selections": [], "interpretation": "none"},
            }
        else:
            conversation = json.loads(prompt[prompt.index('{"instructions"') :])["conversation"]
            evidence = next(
                ast.literal_eval(item["output"])
                for item in conversation
                if item.get("type") == "function_call_output"
            )
            decision = {
                "kind": "final",
                "tool": "none",
                "arguments": "{}",
                "reply": {
                    "selections": [
                        {"evidence_id": evidence["evidence_id"], "fact_keys": ["total_jobs"]}
                    ],
                    "interpretation": "none",
                },
            }
        return cli_events(decision)

    monkeypatch.setattr(transport, "execute_cli", fake_cli)
    context = ToolContext(FakeService(), "base", None)
    agent = Agent(
        name="local test",
        model=transport.CodexSubscriptionModel("gpt-6.1-sol", "official-codex"),
        model_settings=ModelSettings(reasoning=Reasoning(effort="low"), parallel_tool_calls=False),
        tools=TOOLS,
        output_type=GroundedReply,
        instructions="Return exact evidence only.",
    )
    result = asyncio.run(
        Runner.run(
            agent, "多少订单？", context=context, run_config=RunConfig(tracing_disabled=True)
        )
    )
    reply = render_reply(result.final_output, context)
    assert len(prompts) == 2 and context.call_count == 1
    assert reply["facts"][0]["value"] == "3" and not reply["fallback"]


@pytest.mark.parametrize(
    ("client_host", "base_url", "origin", "expected"),
    [
        ("192.0.2.3", "http://127.0.0.1:8000", None, 403),
        ("127.0.0.1", "http://evil.example:8000", None, 403),
        ("127.0.0.1", "http://127.0.0.1:8000", "https://evil.example", 403),
        ("127.0.0.1", "http://127.0.0.1:8000", "http://localhost:9000", 403),
        ("127.0.0.1", "http://127.0.0.1:8000", "http://localhost:broken", 403),
        ("127.0.0.1", "http://127.0.0.1:8000", "http://localhost:8000", 200),
    ],
)
def test_subscription_endpoint_is_local_and_same_origin(
    tmp_path, monkeypatch, client_host, base_url, origin, expected
):
    calls = []
    monkeypatch.setattr(transport, "codex_executable", lambda configured="": "official-codex")
    monkeypatch.setattr(transport, "subscription_signed_in", lambda exe: True)

    async def fake_answer(*args):
        calls.append(True)
        return {
            "query_id": "test",
            "facts": [],
            "interpretation": None,
            "tool_trace": [],
            "pending_run_ids": [],
            "fallback": False,
        }

    monkeypatch.setattr("opspilot.agents.copilot.answer_query", fake_answer)
    settings = Settings(
        _env_file=None,
        ai_enabled=True,
        ai_provider="codex_subscription",
        openai_model="gpt-6.1-sol",
        database_url=f"sqlite:///{tmp_path / 'local.db'}",
    )
    with TestClient(create_app(settings), base_url=base_url, client=(client_host, 50000)) as client:
        health = client.get("/api/v1/health").json()
        assert health["ai_provider"] == "codex_subscription"
        assert health["ai_model"] == "gpt-6.1-sol" and health["ai_reasoning_effort"] == "low"
        response = client.post(
            "/api/v1/copilot/query",
            json={"scenario_id": "unused", "question": "多少订单？"},
            headers={"Origin": origin} if origin else {},
        )
        assert response.status_code == expected
        assert bool(calls) == (expected == 200)
