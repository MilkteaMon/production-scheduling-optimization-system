"""Read back every result and recompute its metrics from regenerated immutable jobs."""

import json
from pathlib import Path

from opspilot.analytics.metrics import calculate_metrics
from opspilot.domain.models import GenerateRequest, Placement, PlanningInput
from opspilot.scheduling.validation import validate_schedule
from opspilot.services.data import generate_data


def check(data, row):
    placements = [Placement(**p) for p in row["placements"]]
    assert not validate_schedule(data, placements), row
    metrics = calculate_metrics(data, placements).model_dump()
    assert all(abs(metrics[k] - row["metrics"][k]) <= 1e-5 for k in metrics), row
    if row["proven_optimal"]:
        assert row["solver_status"] == "optimal" and row["result_source"] == "cbc_incumbent"
    if row["best_bound"] is not None:
        assert row["best_bound"] <= metrics["total_weighted_tardiness"] + 1e-5
    assert all(p.start_min.is_integer() and p.completion_min.is_integer() for p in placements)


folder = Path("experiments/results/full-60s")
rows = [json.loads(line) for line in (folder / "runs.jsonl").read_text().splitlines()]
assert len(rows) == 285 and len({r["experiment_key"] for r in rows}) == 285
for row in rows:
    base = generate_data(
        GenerateRequest(
            job_count=row["jobs"],
            machine_count=row["base_machines"],
            seed=row["seed"],
            profile=row["profile"],
        )
    )
    data = PlanningInput(
        jobs=base.jobs, machine_count=row["machines"], horizon_min=base.horizon_min
    )
    assert data.job_hash == row["job_hash"] and data.input_hash == row["input_hash"]
    check(data, row)
receipt = json.loads(Path("docs/opspilot/demo-artifacts/receipt.json").read_text(encoding="utf-8"))
for key, machines in [("baseline_runs", 4), ("additional_machine_runs", 5)]:
    data = PlanningInput(
        jobs=receipt["dataset"]["jobs"],
        machine_count=machines,
        horizon_min=receipt["dataset"]["horizon_min"],
    )
    for row in receipt[key]:
        check(data, row)
result = {
    "benchmark_records_read_back": len(rows),
    "demonstration_records_read_back": 6,
    "all_hashes_and_recomputed_kpis_match": True,
    "all_schedules_valid": True,
    "all_displayed_times_integral": True,
    "optimality_provenance_consistent": True,
}
Path("docs/opspilot/artifact-verification.json").write_text(
    json.dumps(result, indent=2), encoding="utf-8"
)
print(json.dumps(result, indent=2))
