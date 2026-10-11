"""Sequential, resumable experiments. Run from the repository root."""

import argparse
import csv
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from opspilot import SOLVER_ADAPTER_VERSION
from opspilot.domain.models import GenerateRequest, PlanningInput, ScheduleResult
from opspilot.scheduling.heuristics import schedule_heuristic
from opspilot.scheduling.milp import solver_path
from opspilot.scheduling.validation import validate_schedule
from opspilot.services.data import GENERATOR_VERSION, generate_data


def run(output: Path, budget: int, shard_index: int = 0, shard_count: int = 1):
    output.mkdir(parents=True, exist_ok=True)
    metadata_file = output / "environment.json"
    if not metadata_file.exists():
        metadata_file.write_text(
            json.dumps(
                {
                    "started_at": datetime.now(UTC).isoformat(),
                    "platform": platform.platform(),
                    "processor": platform.processor(),
                    "python": platform.python_version(),
                    "solver_path": "project-local CBC standalone"
                    if "runtime" in solver_path()
                    else "packaged CBC",
                    "cbc_banner": subprocess.run(
                        [solver_path(), "-stop"],
                        capture_output=True,
                        text=True,
                        check=False,
                    ).stdout,
                    "packages": {
                        p: importlib.metadata.version(p)
                        for p in ["pulp", "numpy", "pandas", "psutil"]
                    },
                    "time_limit_seconds": budget,
                    "solver_threads": 1,
                    "solver_seed": 42,
                    "generator_version": GENERATOR_VERSION,
                    "model_version": "1.0",
                    "solver_adapter_version": SOLVER_ADAPTER_VERSION,
                    "shard_index": shard_index,
                    "shard_count": shard_count,
                    "note": "Sequential CBC runs on a local development machine. Other development work may affect runtime; timings are descriptive, not controlled performance claims.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    else:
        meta = json.loads(metadata_file.read_text())
        if (
            meta["time_limit_seconds"] != budget
            or meta.get("solver_adapter_version") != SOLVER_ADAPTER_VERSION
        ):
            raise ValueError("Cannot resume with a different solver configuration")
    raw_file = output / "runs.jsonl"
    rows = (
        [json.loads(line) for line in raw_file.read_text().splitlines()]
        if raw_file.exists()
        else []
    )
    done = {r["experiment_key"] for r in rows}
    configs = [
        (n, m, profile, seed, False)
        for n in [20, 35, 50]
        for m in [3, 5]
        for profile in ["relaxed", "tight", "staggered"]
        for seed in range(5)
    ]
    configs += [(35, 3, "tight", seed, True) for seed in range(5)]
    for number, (n, m, profile, seed, extra) in enumerate(configs, 1):
        if (number - 1) % shard_count != shard_index:
            continue
        config = GenerateRequest(job_count=n, machine_count=m, profile=profile, seed=seed)
        base = generate_data(config)
        data = PlanningInput(
            jobs=base.jobs, machine_count=m + int(extra), horizon_min=base.horizon_min
        )
        for method in ["fcfs", "edd", "milp"]:
            key = f"{n}:{m}:{profile}:{seed}:{extra}:{method}"
            if key in done:
                continue
            if method == "milp":
                p = subprocess.Popen(
                    [sys.executable, "-m", "opspilot.worker"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                try:
                    stdout, stderr = p.communicate(
                        json.dumps({"data": data.model_dump(), "time_limit_seconds": budget}),
                        timeout=budget + 30,
                    )
                except subprocess.TimeoutExpired:
                    from opspilot.services.application import ApplicationService

                    ApplicationService.kill_tree(p)
                    raise RuntimeError(f"Watchdog interrupted {key}; rerun to resume")
                if p.returncode:
                    raise RuntimeError(stderr)
                result = ScheduleResult.model_validate_json(stdout)
            else:
                result = schedule_heuristic(data, method)
            errors = validate_schedule(data, result.placements)
            row = {
                "experiment_key": key,
                "jobs": n,
                "base_machines": m,
                "machines": data.machine_count,
                "profile": profile,
                "seed": seed,
                "additional_machine": extra,
                "job_hash": data.job_hash,
                "input_hash": data.input_hash,
                "solver_adapter_version": SOLVER_ADAPTER_VERSION,
                "time_limit_seconds": budget if method == "milp" else None,
                "validated": not errors,
                **result.model_dump(),
            }
            with raw_file.open("a", encoding="utf-8") as file:
                file.write(json.dumps(row) + "\n")
            rows.append(row)
            print(
                f"[{number}/{len(configs)}] {key} {result.solver_status} objective={result.metrics.total_weighted_tardiness} source={result.result_source}",
                flush=True,
            )
    flat = [
        {
            **{
                k: r[k]
                for k in [
                    "experiment_key",
                    "jobs",
                    "base_machines",
                    "machines",
                    "profile",
                    "seed",
                    "additional_machine",
                    "method",
                    "solver_status",
                    "result_source",
                    "proven_optimal",
                    "best_bound",
                    "relative_gap",
                    "solver_runtime_seconds",
                    "total_runtime_seconds",
                    "validated",
                ]
            },
            **r["metrics"],
        }
        for r in rows
    ]
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    (output / "completion.json").write_text(
        json.dumps(
            {
                "completed_at": datetime.now(UTC).isoformat(),
                "datasets": 90,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "additional_machine_scenarios": 5,
                "method_results": len(rows),
                "all_validated": all(r["validated"] for r in rows),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("experiments/results/full-60s"))
    parser.add_argument("--time-limit", type=int, default=60)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.shard_count:
        raise ValueError("Invalid benchmark shard")
    run(args.output, args.time_limit, args.shard_index, args.shard_count)
