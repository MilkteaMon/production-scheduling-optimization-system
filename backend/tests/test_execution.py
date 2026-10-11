import subprocess
import threading
import time

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from opspilot.config import Settings
from opspilot.domain.models import GenerateRequest, RunRequest
from opspilot.persistence.database import create_database
from opspilot.persistence.models import ScheduleRun
from opspilot.services.application import ApplicationService
from opspilot.services.data import generate_data


@pytest.fixture
def service(tmp_path):
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'execution.db').as_posix()}")
    engine, sessions = create_database(settings.database_url)
    service = ApplicationService(sessions, settings)
    yield service
    service.close()
    engine.dispose()


def wait_idle(service):
    for _ in range(200):
        if service.pending == 0:
            return
        time.sleep(0.01)
    raise AssertionError("Execution did not finish")


def create_small(service):
    return service.create_dataset(generate_data(GenerateRequest(job_count=3)), "Test", "synthetic")


def test_restart_interrupts_unfinished_runs_and_preserves_completed(service):
    dataset = create_small(service)
    wait_idle(service)
    scenario_id = dataset["scenarios"][0]["id"]
    before = service.list_runs(scenario_id)
    with service.sessions.begin() as session:
        orphan = ScheduleRun(
            scenario_id=scenario_id, method="milp", input_hash="test", solver_config={}
        )
        session.add(orphan)
        session.flush()
        orphan_id = orphan.id
    service.close()
    restarted = ApplicationService(service.sessions, service.settings)
    try:
        interrupted = restarted.get_run(orphan_id)
        assert interrupted["execution_state"] == "interrupted"
        assert not interrupted["has_valid_schedule"] and not interrupted["proven_optimal"]
        for completed in before:
            assert restarted.get_run(completed["id"]) == completed
    finally:
        restarted.close()


def test_queue_limit_and_dataset_creation_are_atomic(service, monkeypatch):
    dataset = create_small(service)
    wait_idle(service)
    release = threading.Event()
    started = threading.Event()

    def held_worker(data, budget):
        started.set()
        release.wait(timeout=5)
        from opspilot.scheduling.heuristics import schedule_heuristic

        return schedule_heuristic(data, "edd")

    monkeypatch.setattr(service, "execute_worker", held_worker)
    try:
        for _ in range(11):
            service.queue_runs(dataset["scenarios"][0]["id"], RunRequest(methods=["milp"]))
        assert started.wait(timeout=1)
        before = len(service.list_runs(dataset["scenarios"][0]["id"]))
        with pytest.raises(HTTPException) as error:
            service.queue_runs(dataset["scenarios"][0]["id"], RunRequest(methods=["milp"]))
        assert error.value.status_code == 429
        with pytest.raises(HTTPException) as error:
            create_small(service)
        assert error.value.status_code == 429
        assert len(service.list_datasets()) == 1
        assert len(service.list_runs(dataset["scenarios"][0]["id"])) == before
    finally:
        release.set()
        wait_idle(service)


def test_watchdog_kills_worker_and_returns_labelled_fallback(service, monkeypatch):
    class StuckProcess:
        def communicate(self, payload, timeout):
            assert timeout == 31
            raise subprocess.TimeoutExpired("worker", timeout)

    process = StuckProcess()
    killed = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(service, "kill_tree", lambda process: killed.append(process))
    result = service.execute_worker(generate_data(GenerateRequest(job_count=2)), 1)
    assert killed == [process]
    assert result.result_source == "heuristic_fallback"
    assert result.solver_status == "time_limit" and not result.proven_optimal
    assert not service.processes


def test_worker_crash_is_explicit_and_baselines_remain_available(service, monkeypatch):
    dataset = create_small(service)
    wait_idle(service)

    def crash(*args):
        raise RuntimeError("Worker crashed")

    monkeypatch.setattr(service, "execute_worker", crash)
    queued = service.queue_runs(dataset["scenarios"][0]["id"], RunRequest(methods=["milp"]))
    wait_idle(service)
    failed = service.get_run(queued["run_ids"][0])
    assert failed["execution_state"] == "failed" and not failed["proven_optimal"]
    assert "Worker crashed" in failed["diagnostics"][0]
    with service.sessions() as session:
        baselines = session.scalars(select(ScheduleRun).where(ScheduleRun.method != "milp")).all()
        assert all(run.has_valid_schedule for run in baselines)


def test_worker_stdout_protocol_survives_verbose_solver_discovery(service, monkeypatch):
    monkeypatch.setenv("CBCBOX_VERBOSE", "1")
    result = service.execute_worker(generate_data(GenerateRequest(job_count=1)), 2)
    assert result.proven_optimal and result.result_source == "cbc_incumbent"
