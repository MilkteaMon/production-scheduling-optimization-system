import csv
import hashlib
import io
import json
import zipfile

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from test_api import wait_run

from opspilot.api.main import create_app
from opspilot.config import ROOT, Settings
from opspilot.persistence.database import create_database
from opspilot.persistence.models import ScheduleRun


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(
            Settings(
                database_url=f"sqlite:///{(tmp_path / 'workflow.db').as_posix()}", ai_enabled=False
            )
        )
    ) as client:
        yield client


def workload(client, name="My production", seed=42):
    dataset = client.post(
        "/api/v1/datasets/generate",
        json={"confirmed": True, "name": name, "job_count": 4, "machine_count": 2, "seed": seed},
    ).json()
    runs = [
        wait_run(client, r["id"])
        for r in client.get(f"/api/v1/scenarios/{dataset['scenarios'][0]['id']}/runs").json()
    ]
    return dataset, runs


def test_archive_restore_preserves_inputs_and_every_run(client):
    dataset, runs = workload(client)
    id = dataset["id"]
    archived = client.patch(f"/api/v1/datasets/{id}/visibility", json={"is_archived": True}).json()
    assert archived["is_archived"] and not archived["is_test"]
    for key in ["jobs", "scenarios", "job_hash", "horizon_min"]:
        assert archived[key] == dataset[key]
    assert client.get("/api/v1/datasets").json()[0]["is_archived"]
    assert all(client.get(f"/api/v1/runs/{r['id']}").json() == r for r in runs)
    assert (
        client.post("/api/v1/exports/power-bi", json={"run_ids": [runs[0]["id"]]}).status_code
        == 200
    )
    restored = client.patch(f"/api/v1/datasets/{id}/visibility", json={"is_archived": False}).json()
    assert not restored["is_archived"] and restored["jobs"] == dataset["jobs"]
    assert (
        client.patch(
            f"/api/v1/datasets/{id}/visibility", json={"is_archived": True, "jobs": []}
        ).status_code
        == 422
    )
    assert (
        client.patch("/api/v1/datasets/missing/visibility", json={"is_archived": True}).status_code
        == 404
    )


def test_test_label_is_explicit_without_hiding_user_imports(client):
    test_data, _ = workload(client, "Browser verification isolated")
    real_data, _ = workload(client, "Synthetic production demo")
    assert test_data["is_test"] and not real_data["is_test"]


def test_bundle_has_compatible_tables_provenance_and_recomputed_metrics(client):
    content = b"job_id,processing_time_min,release_time_min,due_time_min,priority_weight\n001,3,0,2,1\n002,2,0,2,3\n"
    dataset = client.post(
        "/api/v1/datasets/import",
        files={"file": ("jobs.csv", content)},
        data={"confirmed": True, "name": "Leading zero identifiers", "machine_count": 1},
    ).json()
    base = dataset["scenarios"][0]
    runs = [
        wait_run(client, r["id"]) for r in client.get(f"/api/v1/scenarios/{base['id']}/runs").json()
    ]
    extra = client.post(f"/api/v1/datasets/{dataset['id']}/scenarios").json()
    queued = client.post(
        f"/api/v1/scenarios/{extra['id']}/runs", json={"methods": ["fcfs", "edd"]}
    ).json()
    runs += [wait_run(client, id) for id in queued["run_ids"]]
    response = client.post("/api/v1/exports/power-bi", json={"run_ids": [r["id"] for r in runs]})
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {
            "jobs.csv",
            "schedule.csv",
            "machines.csv",
            "kpis.csv",
            "manifest.json",
            "README.md",
            "PowerBI-queries.pq",
            "PowerBI-measures.dax",
        }
        tables = {
            name: list(csv.DictReader(io.StringIO(archive.read(f"{name}.csv").decode())))
            for name in ["jobs", "schedule", "machines", "kpis"]
        }
        assert {r["job_id"] for r in tables["jobs"]} == {"001", "002"}
        assert (
            len(tables["jobs"]) == 2
            and len(tables["schedule"]) == 8
            and len(tables["machines"]) == 6
        )
        assert {int(r["machine_count"]) for r in tables["kpis"]} == {1, 2}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["job_hash"] == dataset["job_hash"]
        assert {r["id"] for r in manifest["runs"]} == {r["id"] for r in runs}
        assert all(r["has_valid_schedule"] and not r["proven_optimal"] for r in manifest["runs"])
        for kpi in tables["kpis"]:
            items = [r for r in tables["schedule"] if r["run_id"] == kpi["run_id"]]
            assert sum(float(r["weighted_tardiness"]) for r in items) == float(
                kpi["total_weighted_tardiness"]
            )
            assert sum(float(r["tardiness_min"]) > 0 for r in items) == int(kpi["late_jobs"])
            assert max(float(r["completion_min"]) for r in items) == float(kpi["makespan_min"])
        assert "not a real factory shift" in archive.read("README.md").decode()


def test_bundle_rejects_incompatible_pending_missing_and_duplicate_runs(client):
    first, a = workload(client, seed=1)
    _, b = workload(client, seed=999)
    assert (
        client.post(
            "/api/v1/exports/power-bi", json={"run_ids": [a[0]["id"], b[0]["id"]]}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/exports/power-bi", json={"run_ids": [a[0]["id"], a[0]["id"]]}
        ).status_code
        == 422
    )
    assert client.post("/api/v1/exports/power-bi", json={"run_ids": []}).status_code == 422
    assert client.post("/api/v1/exports/power-bi", json={"run_ids": ["missing"]}).status_code == 404
    with client.app.state.service.sessions.begin() as session:
        run = ScheduleRun(
            scenario_id=first["scenarios"][0]["id"],
            method="milp",
            input_hash="pending",
            solver_config={},
        )
        session.add(run)
        session.flush()
        id = run.id
    assert client.post("/api/v1/exports/power-bi", json={"run_ids": [id]}).status_code == 409


def test_legacy_migration_classifies_only_known_old_fixture_and_keeps_data(tmp_path):
    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    engine = create_engine(url)
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend/alembic"))
    fixture = [
        {
            "job_id": "A",
            "processing_time_min": 3,
            "release_time_min": 0,
            "due_time_min": 2,
            "priority_weight": 1,
        },
        {
            "job_id": "B",
            "processing_time_min": 2,
            "release_time_min": 0,
            "due_time_min": 2,
            "priority_weight": 3,
        },
    ]
    digest = hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0001")
        for id, name, hash, timestamp in [
            ("browser", "Browser verification desktop", "x", "2026-10-11"),
            ("old-csv", "Synthetic production demo", digest, "2026-10-11T15:26:00+00:00"),
            ("user-csv", "Synthetic production demo", digest, "2026-10-12T00:00:00+00:00"),
            ("other", "Synthetic production demo", "other", "2026-10-11"),
        ]:
            connection.execute(
                text(
                    "INSERT INTO datasets(id,name,source_kind,job_hash,horizon_min,created_at) VALUES(:id,:name,'csv',:hash,5,:timestamp)"
                ),
                {"id": id, "name": name, "hash": hash, "timestamp": timestamp},
            )
    engine.dispose()
    upgraded, _ = create_database(url)
    with upgraded.connect() as connection:
        rows = {
            row.id: row
            for row in connection.execute(
                text("SELECT id,is_test,is_archived,job_hash FROM datasets")
            )
        }
        assert rows["browser"].is_test and rows["old-csv"].is_test
        assert not rows["user-csv"].is_test and not rows["other"].is_test
        assert rows["old-csv"].job_hash == digest and not rows["old-csv"].is_archived
    upgraded.dispose()
