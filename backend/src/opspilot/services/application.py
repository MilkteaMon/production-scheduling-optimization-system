import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import pandas as pd
import psutil
from fastapi import HTTPException
from sqlalchemy import select, update

from opspilot import SOLVER_ADAPTER_VERSION
from opspilot.analytics.metrics import calculate_metrics, late_jobs, machine_utilization, reduction
from opspilot.domain.models import (
    Job,
    Placement,
    PlanningInput,
    RunRequest,
    ScheduleResult,
)
from opspilot.persistence.models import (
    Dataset,
    JobRecord,
    Machine,
    Scenario,
    ScheduleItem,
    ScheduleRun,
    now,
)
from opspilot.scheduling.heuristics import schedule_heuristic
from opspilot.scheduling.validation import validate_schedule


class ApplicationService:
    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="opspilot")
        self.lock = threading.RLock()
        self.pending = 0
        self.processes = set()
        self.closing = False
        with sessions.begin() as session:
            session.execute(
                update(ScheduleRun)
                .where(ScheduleRun.execution_state.in_(["queued", "running"]))
                .values(
                    execution_state="interrupted",
                    diagnostics=["Server restarted before this run finished"],
                    finished_at=now(),
                )
            )

    def close(self):
        with self.lock:
            self.closing = True
            processes = list(self.processes)
        for process in processes:
            self.kill_tree(process)
        self.executor.shutdown(wait=True)

    @staticmethod
    def kill_tree(process):
        try:
            parent = psutil.Process(process.pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            parent.kill()
            process.wait(timeout=5)
        except (psutil.Error, subprocess.TimeoutExpired):
            pass

    def list_datasets(self):
        with self.sessions() as session:
            datasets = session.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all()
            return [self.dataset_detail(d.id, session) for d in datasets]

    def dataset_detail(self, dataset_id, session=None):
        if session is None:
            with self.sessions() as owned:
                return self.dataset_detail(dataset_id, owned)
        dataset = session.get(Dataset, dataset_id)
        if not dataset:
            raise HTTPException(404, "Dataset not found")
        jobs = session.scalars(
            select(JobRecord).where(JobRecord.dataset_id == dataset_id).order_by(JobRecord.job_id)
        ).all()
        scenarios = session.scalars(
            select(Scenario).where(Scenario.dataset_id == dataset_id).order_by(Scenario.created_at)
        ).all()
        return {
            "id": dataset.id,
            "name": dataset.name,
            "source_kind": dataset.source_kind,
            "seed": dataset.seed,
            "generator_params": dataset.generator_params,
            "job_hash": dataset.job_hash,
            "horizon_min": dataset.horizon_min,
            "created_at": dataset.created_at,
            "is_archived": dataset.is_archived,
            "is_test": dataset.is_test,
            "jobs": [self.job_dict(j) for j in jobs],
            "scenarios": [self.scenario_dict(s, session) for s in scenarios],
        }

    def set_dataset_visibility(self, dataset_id, archived):
        with self.sessions.begin() as session:
            dataset = session.get(Dataset, dataset_id)
            if dataset is None:
                raise HTTPException(404, "Dataset not found")
            dataset.is_archived = archived
        return self.dataset_detail(dataset_id)

    @staticmethod
    def job_dict(j):
        return {field: getattr(j, field) for field in Job.model_fields}

    @staticmethod
    def scenario_dict(s, session):
        machines = session.scalars(
            select(Machine).where(Machine.scenario_id == s.id).order_by(Machine.machine_code)
        ).all()
        return {
            "id": s.id,
            "dataset_id": s.dataset_id,
            "name": s.name,
            "kind": s.kind,
            "must_finish_job_ids": s.must_finish_job_ids or [],
            "parent_scenario_id": s.parent_scenario_id,
            "machine_count": len(machines),
            "machines": [{"id": m.id, "machine_code": m.machine_code} for m in machines],
        }

    def scenario_input(self, scenario_id):
        with self.sessions() as session:
            scenario = session.get(Scenario, scenario_id)
            if not scenario:
                raise HTTPException(404, "Scenario not found")
            dataset = session.get(Dataset, scenario.dataset_id)
            jobs = session.scalars(
                select(JobRecord)
                .where(JobRecord.dataset_id == dataset.id)
                .order_by(JobRecord.job_id)
            ).all()
            info = self.scenario_dict(scenario, session)
            return PlanningInput(
                jobs=[Job(**self.job_dict(j)) for j in jobs],
                machine_count=info["machine_count"],
                horizon_min=dataset.horizon_min,
                must_finish_job_ids=info["must_finish_job_ids"],
            ), info

    def preview_rules(self, scenario_id, request):
        data, scenario = self.scenario_input(scenario_id)
        unknown = set(request.job_ids) - {j.job_id for j in data.jobs}
        if unknown:
            raise HTTPException(
                422, "Unknown job IDs in this dataset: " + ", ".join(sorted(unknown))
            )
        count = data.machine_count + int(request.add_machine)
        if count > 6:
            raise HTTPException(
                422, "At most six machines are supported, including the additional machine"
            )
        ids = sorted(set(data.must_finish_job_ids) | set(request.job_ids))
        if not ids and not request.add_machine:
            raise HTTPException(422, "Select at least one hard-deadline job or add one machine")
        constrained = data.model_copy(update={"machine_count": count, "must_finish_job_ids": ids})
        deadlines = [
            {
                "job_id": j.job_id,
                "due_time_min": j.due_time_min,
                "earliest_completion_min": j.release_time_min + j.processing_time_min,
            }
            for j in data.jobs
            if j.job_id in ids
        ]
        return {
            "scenario_id": scenario_id,
            "dataset_id": scenario["dataset_id"],
            "job_hash": data.job_hash,
            "horizon_min": data.horizon_min,
            "input_hash": constrained.input_hash,
            "base_machine_count": data.machine_count,
            "machine_count": count,
            "job_ids": ids,
            "add_machine": request.add_machine,
            "deadlines": deadlines,
            "warnings": [
                f"{d['job_id']}: earliest completion exceeds its hard deadline"
                for d in deadlines
                if d["earliest_completion_min"] > d["due_time_min"]
            ],
        }

    def apply_rules(self, scenario_id, request):
        if not request.confirmed:
            raise HTTPException(422, "Confirm the previewed scenario rules first")
        with self.lock:
            preview = self.preview_rules(scenario_id, request)
            if self.closing or self.pending + 3 > self.settings.queue_limit + 1:
                raise HTTPException(429, "Scheduling queue is full; retry shortly")
            kind = "what_if:" + preview["input_hash"]
            with self.sessions.begin() as session:
                existing = session.scalar(
                    select(Scenario).where(
                        Scenario.dataset_id == preview["dataset_id"], Scenario.kind == kind
                    )
                )
                if existing:
                    info = self.scenario_dict(existing, session)
                else:
                    scenario = Scenario(
                        dataset_id=preview["dataset_id"],
                        parent_scenario_id=scenario_id,
                        kind=kind,
                        name=f"{preview['machine_count']} machines · {len(preview['job_ids'])} hard deadlines",
                        must_finish_job_ids=preview["job_ids"],
                    )
                    session.add(scenario)
                    session.flush()
                    session.add_all(
                        Machine(scenario_id=scenario.id, machine_code=f"M{k}")
                        for k in range(1, preview["machine_count"] + 1)
                    )
                    session.flush()
                    info = self.scenario_dict(scenario, session)
            runs = self.list_runs(info["id"])
            cached = [
                next(
                    (
                        r
                        for r in runs
                        if r["method"] == method
                        and r["solver_config"]["time_limit_seconds"] == request.time_limit_seconds
                    ),
                    None,
                )
                for method in ["fcfs", "edd", "milp"]
            ]
            if all(cached):
                ids = [r["id"] for r in cached]
            else:
                ids = self.queue_runs(
                    info["id"],
                    RunRequest(
                        methods=["fcfs", "edd", "milp"],
                        time_limit_seconds=request.time_limit_seconds,
                    ),
                )["run_ids"]
            return {"scenario": info, "run_ids": ids, "preview": preview}

    def create_dataset(self, data, name, source_kind, params=None, initial_run_request=None):
        initial_run_request = initial_run_request or RunRequest(methods=["fcfs", "edd"])
        with self.lock:
            if (
                self.closing
                or self.pending + len(initial_run_request.methods) > self.settings.queue_limit + 1
            ):
                raise HTTPException(429, "Scheduling queue is full; retry before creating data")
            with self.sessions.begin() as session:
                dataset = Dataset(
                    name=name,
                    source_kind=source_kind,
                    seed=params.get("seed") if params else None,
                    generator_params=params,
                    job_hash=data.job_hash,
                    horizon_min=data.horizon_min,
                    is_test=name.startswith("Browser verification"),
                )
                session.add(dataset)
                session.flush()
                session.add_all(
                    JobRecord(dataset_id=dataset.id, **j.model_dump()) for j in data.jobs
                )
                session.flush()
                scenario = Scenario(
                    dataset_id=dataset.id,
                    name="Current capacity",
                    kind="baseline",
                    must_finish_job_ids=data.must_finish_job_ids,
                )
                session.add(scenario)
                session.flush()
                session.add_all(
                    Machine(scenario_id=scenario.id, machine_code=f"M{k}")
                    for k in range(1, data.machine_count + 1)
                )
                dataset_id, scenario_id = dataset.id, scenario.id
            self.queue_runs(scenario_id, initial_run_request)
            return self.dataset_detail(dataset_id)

    def add_machine(self, dataset_id):
        with self.lock:
            with self.sessions.begin() as session:
                baseline = session.scalar(
                    select(Scenario).where(
                        Scenario.dataset_id == dataset_id, Scenario.kind == "baseline"
                    )
                )
                if not baseline:
                    raise HTTPException(404, "Dataset not found")
                existing = session.scalar(
                    select(Scenario).where(
                        Scenario.dataset_id == dataset_id, Scenario.kind == "additional_machine"
                    )
                )
                if existing:
                    return self.scenario_dict(existing, session)
                base_machines = session.scalars(
                    select(Machine).where(Machine.scenario_id == baseline.id)
                ).all()
                if len(base_machines) >= 6:
                    raise HTTPException(422, "At most six machines are supported")
                scenario = Scenario(
                    dataset_id=dataset_id,
                    parent_scenario_id=baseline.id,
                    name="One additional machine",
                    kind="additional_machine",
                    must_finish_job_ids=baseline.must_finish_job_ids or [],
                )
                session.add(scenario)
                session.flush()
                session.add_all(
                    Machine(scenario_id=scenario.id, machine_code=f"M{k}")
                    for k in range(1, len(base_machines) + 2)
                )
                session.flush()
                result = self.scenario_dict(scenario, session)
        return result

    def list_runs(self, scenario_id):
        self.scenario_input(scenario_id)
        with self.sessions() as session:
            ids = session.scalars(
                select(ScheduleRun.id)
                .where(ScheduleRun.scenario_id == scenario_id)
                .order_by(ScheduleRun.created_at.desc())
            ).all()
        return [self.get_run(id) for id in ids]

    def queue_runs(self, scenario_id, request):
        data, _ = self.scenario_input(scenario_id)
        with self.lock:
            if self.closing or self.pending + len(request.methods) > self.settings.queue_limit + 1:
                raise HTTPException(
                    429, "Scheduling queue is full; retry shortly", headers={"Retry-After": "5"}
                )
            with self.sessions.begin() as session:
                runs = [
                    ScheduleRun(
                        scenario_id=scenario_id,
                        method=method,
                        input_hash=data.input_hash,
                        model_version="2.0",
                        solver_config={
                            "time_limit_seconds": request.time_limit_seconds,
                            "solver": "cbc",
                            "threads": 1,
                            "seed": 42,
                            "adapter_version": SOLVER_ADAPTER_VERSION,
                            "must_finish_job_ids": data.must_finish_job_ids,
                        },
                    )
                    for method in request.methods
                ]
                session.add_all(runs)
                session.flush()
                ids = [r.id for r in runs]
            self.pending += len(ids)
            for id, method in zip(ids, request.methods):
                self.executor.submit(self.execute_run, id, data, method, request.time_limit_seconds)
        return {"run_ids": ids}

    def execute_run(self, run_id, data, method, budget):
        clock = perf_counter()
        try:
            with self.sessions.begin() as session:
                run = session.get(ScheduleRun, run_id)
                if self.closing:
                    run.execution_state = "interrupted"
                    run.finished_at = now()
                    return
                run.execution_state = "running"
            if method != "milp":
                result = schedule_heuristic(data, method)
            else:
                result = self.execute_worker(data, budget)
            independent_errors = (
                validate_schedule(data, result.placements) if result.placements else []
            )
            valid = bool(result.placements) and not independent_errors
            with self.sessions.begin() as session:
                run = session.get(ScheduleRun, run_id)
                scenario = session.get(Scenario, run.scenario_id)
                machines = {
                    m.machine_code: m.id
                    for m in session.scalars(
                        select(Machine).where(Machine.scenario_id == run.scenario_id)
                    )
                }
                run.execution_state = (
                    "completed"
                    if valid
                    or (
                        not result.placements
                        and result.solver_status in ["infeasible", "time_limit", "gap_limit"]
                    )
                    else "failed"
                )
                run.has_valid_schedule = valid
                for field in [
                    "solver_status",
                    "result_source",
                    "best_bound",
                    "relative_gap",
                    "solver_runtime_seconds",
                    "diagnostics",
                ]:
                    setattr(run, field, getattr(result, field))
                run.proven_optimal = result.proven_optimal and valid
                run.validation_errors = independent_errors
                run.total_runtime_seconds = perf_counter() - clock
                run.finished_at = now()
                if valid:
                    metrics = calculate_metrics(data, result.placements)
                    run.metrics = metrics.model_dump()
                    run.objective = metrics.total_weighted_tardiness
                    session.add_all(
                        ScheduleItem(
                            run_id=run.id,
                            dataset_id=scenario.dataset_id,
                            job_id=p.job_id,
                            machine_id=machines[p.machine_code],
                            start_min=int(p.start_min),
                            completion_min=int(p.completion_min),
                        )
                        for p in result.placements
                    )
        except Exception as exc:
            with self.sessions.begin() as session:
                run = session.get(ScheduleRun, run_id)
                run.execution_state = "interrupted" if self.closing else "failed"
                run.solver_status = "error"
                run.diagnostics = [f"{type(exc).__name__}: {exc}"]
                run.finished_at = now()
                run.total_runtime_seconds = perf_counter() - clock
        finally:
            with self.lock:
                self.pending -= 1

    def execute_worker(self, data, budget):
        process = subprocess.Popen(
            [sys.executable, "-m", "opspilot.worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        with self.lock:
            self.processes.add(process)
        try:
            output, stderr = process.communicate(
                json.dumps({"data": data.model_dump(), "time_limit_seconds": budget}),
                timeout=budget + 30,
            )
            if process.returncode:
                raise RuntimeError(
                    f"Optimization worker exited {process.returncode}: {stderr[-1500:]}"
                )
            return ScheduleResult.model_validate_json(output)
        except subprocess.TimeoutExpired:
            self.kill_tree(process)
            feasible = [
                r
                for r in [schedule_heuristic(data, "fcfs"), schedule_heuristic(data, "edd")]
                if not validate_schedule(data, r.placements)
            ]
            if not feasible:
                return ScheduleResult(
                    method="milp",
                    placements=[],
                    result_source=None,
                    solver_status="time_limit",
                    diagnostics=[
                        "Watchdog terminated solver; no feasible schedule found. Infeasibility is not proven."
                    ],
                )
            baseline = min(
                feasible,
                key=lambda r: r.metrics.total_weighted_tardiness,
            )
            return baseline.model_copy(
                update={
                    "method": "milp",
                    "solver_status": "time_limit",
                    "result_source": "heuristic_fallback",
                    "diagnostics": ["Watchdog terminated solver process tree; retained heuristic"],
                }
            )
        finally:
            with self.lock:
                self.processes.discard(process)

    def get_run(self, run_id):
        with self.sessions() as session:
            run = session.get(ScheduleRun, run_id)
            if not run:
                raise HTTPException(404, "Run not found")
            fields = [
                "id",
                "scenario_id",
                "method",
                "input_hash",
                "model_version",
                "execution_state",
                "solver_config",
                "solver_status",
                "result_source",
                "proven_optimal",
                "has_valid_schedule",
                "objective",
                "best_bound",
                "relative_gap",
                "solver_runtime_seconds",
                "total_runtime_seconds",
                "validation_errors",
                "diagnostics",
                "metrics",
                "created_at",
                "finished_at",
            ]
            result = {field: getattr(run, field) for field in fields}
            scenario = session.get(Scenario, run.scenario_id)
            result["must_finish_job_ids"] = scenario.must_finish_job_ids or []
            items = session.execute(
                select(ScheduleItem, Machine.machine_code)
                .join(Machine, ScheduleItem.machine_id == Machine.id)
                .where(ScheduleItem.run_id == run_id)
                .order_by(Machine.machine_code, ScheduleItem.start_min)
            ).all()
            result["placements"] = [
                {
                    "job_id": p.job_id,
                    "machine_code": code,
                    "start_min": p.start_min,
                    "completion_min": p.completion_min,
                }
                for p, code in items
            ]
            return result

    def require_result(self, run_id):
        run = self.get_run(run_id)
        if not run["has_valid_schedule"]:
            raise HTTPException(409, "Run has no validated schedule yet")
        data, scenario = self.scenario_input(run["scenario_id"])
        return run, data, [Placement(**p) for p in run["placements"]], scenario

    def compare(self, ids):
        runs = [self.require_result(id) for id in ids]
        first = runs[0][1]
        if any(
            data.job_hash != first.job_hash or data.horizon_min != first.horizon_min
            for _, data, _, _ in runs
        ):
            raise HTTPException(409, "Comparisons require identical jobs and horizon")
        baseline = runs[0][0]["metrics"]
        return {
            "baseline_run_id": ids[0],
            "job_hash": first.job_hash,
            "horizon_min": first.horizon_min,
            "runs": [
                {
                    **run,
                    "machine_count": data.machine_count,
                    "scenario_name": scenario["name"],
                    "constraints_differ": data.must_finish_job_ids != first.must_finish_job_ids,
                    "changes": {
                        k: reduction(baseline[k], run["metrics"][k])
                        for k in ["late_jobs", "total_weighted_tardiness", "makespan_min"]
                    },
                    "window_utilization_change_pp": 100
                    * (run["metrics"]["window_utilization"] - baseline["window_utilization"]),
                    "span_utilization_change_pp": 100
                    * (run["metrics"]["span_utilization"] - baseline["span_utilization"]),
                }
                for run, data, _, scenario in runs
            ],
        }

    def export(self, run_id, table):
        run, data, placements, scenario = self.require_result(run_id)
        keys = {
            "dataset_id": scenario["dataset_id"],
            "scenario_id": scenario["id"],
            "run_id": run_id,
        }
        if table == "jobs":
            rows = [{"dataset_id": scenario["dataset_id"], **j.model_dump()} for j in data.jobs]
        elif table == "machines":
            rows = [{**keys, **m} for m in machine_utilization(data, placements)]
        elif table == "schedule":
            jobs = {j.job_id: j for j in data.jobs}
            rows = [
                {
                    **keys,
                    **p.model_dump(),
                    "method": run["method"],
                    "due_time_min": jobs[p.job_id].due_time_min,
                    "tardiness_min": max(0, p.completion_min - jobs[p.job_id].due_time_min),
                    "priority_weight": jobs[p.job_id].priority_weight,
                    "weighted_tardiness": max(0, p.completion_min - jobs[p.job_id].due_time_min)
                    * jobs[p.job_id].priority_weight,
                    "must_finish_on_time": p.job_id in data.must_finish_job_ids,
                }
                for p in placements
            ]
        elif table == "kpis":
            rows = [
                {
                    **keys,
                    "job_hash": data.job_hash,
                    "input_hash": run["input_hash"],
                    "model_version": run["model_version"],
                    "hard_deadline_count": len(data.must_finish_job_ids),
                    "must_finish_job_ids": ",".join(data.must_finish_job_ids),
                    "time_limit_seconds": run["solver_config"]["time_limit_seconds"],
                    "created_at": run["created_at"],
                    "finished_at": run["finished_at"],
                    **run["metrics"],
                    **{
                        k: run[k]
                        for k in [
                            "method",
                            "solver_status",
                            "result_source",
                            "proven_optimal",
                            "best_bound",
                            "relative_gap",
                            "solver_runtime_seconds",
                            "total_runtime_seconds",
                        ]
                    },
                }
            ]
        else:
            raise HTTPException(404, "Unknown export table")
        output = io.StringIO()
        pd.DataFrame(rows).to_csv(output, index=False, lineterminator="\n")
        return output.getvalue()

    def analytics(self, run_id, kind):
        run, data, placements, scenario = self.require_result(run_id)
        values = (
            late_jobs(data, placements) if kind == "late" else machine_utilization(data, placements)
        )
        return {
            "run_id": run_id,
            "dataset_id": scenario["dataset_id"],
            "scenario_id": run["scenario_id"],
            "method": run["method"],
            "solver_status": run["solver_status"],
            "result_source": run["result_source"],
            "proven_optimal": run["proven_optimal"],
            "rows": values,
        }
