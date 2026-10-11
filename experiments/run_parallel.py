"""Three independent serial-CBC experiment shards; the interactive API remains single-worker."""

import csv
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from opspilot import SOLVER_ADAPTER_VERSION

output = Path("experiments/results/full-60s")
output.mkdir(parents=True, exist_ok=True)
processes = []
logs = []
try:
    for index in range(3):
        folder = output / "shards" / f"shard-{index}"
        folder.mkdir(parents=True, exist_ok=True)
        log = (folder / "execution.log").open("w", encoding="utf-8")
        logs.append(log)
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "experiments/benchmark.py",
                    "--output",
                    str(folder),
                    "--shard-index",
                    str(index),
                    "--shard-count",
                    "3",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )
    return_codes = [process.wait() for process in processes]
    if any(code != 0 for code in return_codes):
        raise RuntimeError("A benchmark shard failed; inspect its log and rerun to resume")
finally:
    for log in logs:
        log.close()
rows = []
for index in range(3):
    rows.extend(
        json.loads(line)
        for line in (output / "shards" / f"shard-{index}" / "runs.jsonl").read_text().splitlines()
    )
assert len(rows) == 285 and len({row["experiment_key"] for row in rows}) == 285
assert all(row["solver_adapter_version"] == SOLVER_ADAPTER_VERSION for row in rows)
rows.sort(
    key=lambda r: (
        r["additional_machine"],
        r["jobs"],
        r["base_machines"],
        r["profile"],
        r["seed"],
        ["fcfs", "edd", "milp"].index(r["method"]),
    )
)
(output / "runs.jsonl").write_text(
    "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
)
meta = json.loads((output / "shards" / "shard-0" / "environment.json").read_text())
meta.update(
    {
        "concurrent_benchmark_workers": 3,
        "note": "Three concurrent independent experiment processes, each with serial CBC. Interactive API has its own one-worker queue. Descriptive elapsed timings on a development machine, not controlled throughput claims.",
    }
)
(output / "environment.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
flat = [
    {
        **{
            k: row[k]
            for k in row
            if k not in ["placements", "metrics", "diagnostics", "validation_errors"]
        },
        **row["metrics"],
    }
    for row in rows
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
            "additional_machine_scenarios": 5,
            "method_results": len(rows),
            "all_validated": all(row["validated"] for row in rows),
            "solver_adapter_version": SOLVER_ADAPTER_VERSION,
            "benchmark_workers": 3,
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("All 285 corrected benchmark records saved.")
