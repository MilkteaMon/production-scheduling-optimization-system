import time

import pytest
from fastapi.testclient import TestClient

from opspilot.api.main import create_app
from opspilot.config import Settings


@pytest.fixture
def client(tmp_path):
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", ai_enabled=False)
    )
    with TestClient(app) as client:
        yield client


def wait_run(client, id):
    for _ in range(200):
        run = client.get(f"/api/v1/runs/{id}").json()
        if run["execution_state"] not in ["queued", "running"]:
            return run
        time.sleep(0.05)
    raise AssertionError("Run did not complete")


def test_full_non_ai_flow_and_immutable_scenario(client):
    assert client.get("/api/v1/health").json()["ai_available"] is False
    assert client.post("/api/v1/datasets/generate", json={}).status_code == 422
    response = client.post(
        "/api/v1/datasets/generate", json={"confirmed": True, "job_count": 4, "machine_count": 2}
    )
    assert response.status_code == 201, response.text
    dataset = response.json()
    base = dataset["scenarios"][0]
    ids = [r["id"] for r in client.get(f"/api/v1/scenarios/{base['id']}/runs").json()]
    results = [wait_run(client, id) for id in ids]
    assert all(r["has_valid_schedule"] for r in results)
    for table in ["jobs", "machines", "schedule", "kpis"]:
        export = client.get(f"/api/v1/runs/{ids[0]}/exports/{table}.csv")
        assert export.status_code == 200 and len(export.text.splitlines()) >= 2
    extra = client.post(f"/api/v1/datasets/{dataset['id']}/scenarios").json()
    assert extra["machine_count"] == 3
    assert client.post(f"/api/v1/datasets/{dataset['id']}/scenarios").json()["id"] == extra["id"]
    assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["jobs"] == dataset["jobs"]
    for run in results:
        assert client.get(f"/api/v1/runs/{run['id']}").json() == run
    assert client.post("/api/v1/comparisons", json={"run_ids": ids}).status_code == 200
    assert client.get(f"/api/v1/runs/{ids[0]}/late-jobs").status_code == 200
    assert (
        client.post(
            "/api/v1/copilot/query", json={"scenario_id": base["id"], "question": "late?"}
        ).status_code
        == 503
    )


def test_invalid_import_is_atomic(client):
    bad = b"job_id,processing_time_min,release_time_min,due_time_min,priority_weight\nA,1.5,0,5,1"
    assert (
        client.post(
            "/api/v1/datasets/validate-csv",
            files={"file": ("a.csv", bad)},
            data={"machine_count": 3},
        ).json()["valid"]
        is False
    )
    assert (
        client.post(
            "/api/v1/datasets/import",
            files={"file": ("a.csv", bad)},
            data={"machine_count": 3, "name": "test", "confirmed": True},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/datasets").json() == []


def test_valid_import_and_unknown_routes(client):
    content = (
        b"job_id,processing_time_min,release_time_min,due_time_min,priority_weight\nA,2,10,1,1"
    )
    response = client.post(
        "/api/v1/datasets/import",
        files={"file": ("a.csv", content)},
        data={"machine_count": 1, "name": "Imported", "confirmed": True},
    )
    assert response.status_code == 201
    assert client.get("/api/v1/runs/unknown").status_code == 404
    assert (
        client.post("/api/v1/scenarios/unknown/runs", json={"methods": ["fcfs"]}).status_code == 404
    )
