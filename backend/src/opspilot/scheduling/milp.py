import math
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter

import pulp

from opspilot.analytics.metrics import calculate_metrics
from opspilot.config import ROOT, Settings
from opspilot.domain.models import Placement, PlanningInput, ScheduleResult
from opspilot.scheduling.heuristics import schedule_heuristic
from opspilot.scheduling.validation import TOLERANCE, normalize_schedule, validate_schedule


def solver_path() -> str:
    configured = Settings().cbc_path
    standalone = (
        ROOT
        / "runtime"
        / "solvers"
        / "bin"
        / ("cbc.exe" if __import__("os").name == "nt" else "cbc")
    )
    return configured or (str(standalone) if standalone.is_file() else pulp.COIN_CMD().path)


def solver_available() -> bool:
    try:
        probe = subprocess.run(
            [solver_path(), "-stop"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__("os").name == "nt" else 0,
        )
        return probe.returncode == 0
    except Exception:
        return False


def build_model(data: PlanningInput, seed_schedule: ScheduleResult):
    jobs = sorted(data.jobs, key=lambda j: j.job_id)
    n, m, horizon = len(jobs), data.machine_count, data.horizon_min
    model = pulp.LpProblem("OpsPilot_weighted_tardiness", pulp.LpMinimize)
    x = {(i, k): model.add_variable(f"x_{i}_{k}", cat="Binary") for i in range(n) for k in range(m)}
    y = {
        (i, j): model.add_variable(f"y_{i}_{j}", cat="Binary")
        for i in range(n)
        for j in range(i + 1, n)
    }
    start = {
        i: model.add_variable(
            f"s_{i}", jobs[i].release_time_min, horizon - jobs[i].processing_time_min
        )
        for i in range(n)
    }
    tardy = {
        i: model.add_variable(f"t_{i}", 0, max(0, horizon - jobs[i].due_time_min)) for i in range(n)
    }
    model += pulp.lpSum(jobs[i].priority_weight * tardy[i] for i in range(n))
    for i, job in enumerate(jobs):
        model += pulp.lpSum(x[i, k] for k in range(m)) == 1
        model += tardy[i] >= start[i] + job.processing_time_min - job.due_time_min
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(m):
                model += start[i] + jobs[i].processing_time_min <= start[j] + horizon * (
                    3 - y[i, j] - x[i, k] - x[j, k]
                )
                model += start[j] + jobs[j].processing_time_min <= start[i] + horizon * (
                    2 + y[i, j] - x[i, k] - x[j, k]
                )
    initial = {p.job_id: p for p in seed_schedule.placements}
    for i, job in enumerate(jobs):
        p = initial[job.job_id]
        start[i].setInitialValue(p.start_min)
        tardy[i].setInitialValue(max(0, p.completion_min - job.due_time_min))
        for k in range(m):
            x[i, k].setInitialValue(int(p.machine_code == f"M{k + 1}"))
    for (i, j), variable in y.items():
        variable.setInitialValue(
            int(initial[jobs[i].job_id].start_min <= initial[jobs[j].job_id].start_min)
        )
    return model, jobs, x, start


def extract_candidate(data, jobs, x, start):
    placements = []
    for i, job in enumerate(jobs):
        values = [pulp.value(x[i, k]) for k in range(data.machine_count)]
        if any(
            v is None or not math.isfinite(v) or min(abs(v), abs(v - 1)) > TOLERANCE for v in values
        ):
            raise ValueError("Solver returned nonintegral assignment")
        if abs(sum(values) - 1) > TOLERANCE:
            raise ValueError("Solver returned invalid assignment sum")
        k = max(range(data.machine_count), key=lambda k: values[k])
        s = pulp.value(start[i])
        if s is None or not math.isfinite(s):
            raise ValueError("Solver returned invalid start time")
        placements.append(
            Placement(
                job_id=job.job_id,
                machine_code=f"M{k + 1}",
                start_min=s,
                completion_min=s + job.processing_time_min,
            )
        )
    errors = validate_schedule(data, placements)
    if errors:
        raise ValueError("; ".join(errors))
    return normalize_schedule(data, placements)


def optimize(data: PlanningInput, time_limit_seconds: float = 60, seed: int = 42) -> ScheduleResult:
    clock = perf_counter()
    baselines = [schedule_heuristic(data, "fcfs"), schedule_heuristic(data, "edd")]
    best = min(
        baselines, key=lambda r: (r.metrics.total_weighted_tardiness, r.metrics.makespan_min)
    )
    result = ScheduleResult(
        method="milp",
        placements=best.placements,
        result_source="heuristic_fallback",
        solver_status="error",
        metrics=best.metrics,
    )
    try:
        if not solver_available():
            raise RuntimeError("CBC unavailable; install the locked pulp[cbc] dependency")
        model, jobs, x, start = build_model(data, best)
        # CBC's Windows build prepends .\ to MIP-start filenames. Keep every solver
        # argument relative and space-free, without changing the process working directory.
        with tempfile.TemporaryDirectory(prefix=".opspilot-cbc-", dir=".") as directory:
            solver = pulp.COIN_CMD(
                path=solver_path(),
                msg=False,
                timeLimit=time_limit_seconds,
                threads=1,
                randomSeed=seed,
                warmStart=True,
                keepFiles=True,
                gapRel=0,
                gapAbs=0,
                timeMode="elapsed",
                logPath=str(Path(directory) / "solver.log"),
            )
            # A unique relative prefix also keeps concurrent benchmark workers isolated.
            model.name = str(Path(directory).relative_to(Path.cwd()) / "model")
            stats = model.solve(solver)
            log_file = Path(directory) / "solver.log"
            log = log_file.read_text(errors="replace") if log_file.is_file() else ""
            for line in log.splitlines():
                if "MIPStart values read" in line or "MIPStart provided solution" in line:
                    result.diagnostics.append(line.strip())
            statuses = {
                "Optimal": "optimal",
                "TimeLimit": "time_limit",
                "GapLimit": "gap_limit",
                "Infeasible": "infeasible",
                "Unbounded": "unbounded",
                "Interrupted": "error",
                "Stopped": "error",
                "NotSolved": "error",
                "Undefined": "error",
            }
            result.solver_status = statuses.get(stats.status_str, "error")
            result.solver_runtime_seconds = stats.time
            result.diagnostics.append(
                f"CBC {stats.solver_version or 'version unavailable'}: {stats.status_str}; raw objective={stats.objective}"
            )
            if stats.best_bound is not None and math.isfinite(stats.best_bound):
                result.best_bound = float(stats.best_bound)
            if stats.has_solution:
                candidate = extract_candidate(data, jobs, x, start)
                metrics = calculate_metrics(data, candidate)
                if (
                    metrics.total_weighted_tardiness
                    <= best.metrics.total_weighted_tardiness + TOLERANCE
                ):
                    result.placements = candidate
                    result.metrics = metrics
                    result.result_source = "cbc_incumbent"
                    result.proven_optimal = result.solver_status == "optimal"
                else:
                    result.diagnostics.append(
                        "Solver candidate was worse than the retained heuristic"
                    )
                    if result.solver_status == "optimal":
                        result.solver_status = "error"
                        result.diagnostics.append(
                            "Optimality claim inconsistent with a known feasible schedule"
                        )
            elif result.solver_status in ("infeasible", "unbounded"):
                result.diagnostics.append(
                    "Unexpected termination: this input has a known feasible baseline"
                )
            else:
                result.diagnostics.append("No solver incumbent; retaining a validated heuristic")
    except Exception as exc:
        result.solver_status = "error"
        result.proven_optimal = False
        result.diagnostics.append(f"{type(exc).__name__}: {exc}")
    result.validation_errors = validate_schedule(data, result.placements)
    if result.validation_errors:
        result.proven_optimal = False
    objective = result.metrics.total_weighted_tardiness
    if result.best_bound is not None:
        if result.best_bound <= objective + TOLERANCE:
            result.relative_gap = max(0, objective - result.best_bound) / max(abs(objective), 1)
        else:
            result.best_bound = None
            result.diagnostics.append("Discarded inconsistent solver bound")
    result.total_runtime_seconds = perf_counter() - clock
    return result
