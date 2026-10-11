"""Create an actual default demonstration through the running local API."""

import argparse
import json
import time
import urllib.request
from pathlib import Path


def main(base_url, output):
    output.mkdir(parents=True, exist_ok=True)

    def api(path, body=None):
        request = urllib.request.Request(
            base_url + "/api/v1" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)

    def completed(ids):
        deadline = time.monotonic() + 200
        while time.monotonic() < deadline:
            runs = [api(f"/runs/{id}") for id in ids]
            if all(r["execution_state"] not in ["queued", "running"] for r in runs):
                if not all(r["has_valid_schedule"] for r in runs):
                    raise RuntimeError(f"Demonstration failed: {runs}")
                return runs
            time.sleep(1)
        raise TimeoutError("Demonstration queue did not finish in time")

    dataset = api(
        "/datasets/generate",
        {
            "confirmed": True,
            "name": "Portfolio demonstration · 30 jobs",
            "job_count": 30,
            "machine_count": 4,
            "seed": 42,
            "profile": "tight",
        },
    )
    baseline = dataset["scenarios"][0]
    queued = api(
        f"/scenarios/{baseline['id']}/runs", {"methods": ["milp"], "time_limit_seconds": 60}
    )
    runs = api(f"/scenarios/{baseline['id']}/runs")
    runs = completed([r["id"] for r in runs])
    extra = api(f"/datasets/{dataset['id']}/scenarios", {})
    extra_ids = api(
        f"/scenarios/{extra['id']}/runs",
        {"methods": ["fcfs", "edd", "milp"], "time_limit_seconds": 60},
    )["run_ids"]
    extra_runs = completed(extra_ids)
    receipt = {
        "dataset": dataset,
        "baseline_runs": runs,
        "additional_machine": extra,
        "additional_machine_runs": extra_runs,
        "optimization_run_id": queued["run_ids"][0],
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    for table in ["jobs", "machines", "schedule", "kpis"]:
        url = base_url + f"/api/v1/runs/{queued['run_ids'][0]}/exports/{table}.csv"
        with urllib.request.urlopen(url, timeout=15) as response:
            (output / f"{table}.csv").write_bytes(response.read())
    print(f"Saved actual API results and CSV exports: {output}")
    for run in runs + extra_runs:
        print(
            f"{run['method']} {run['solver_status']} {run['result_source']} objective={run['objective']} optimal={run['proven_optimal']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("docs/opspilot/demo-artifacts"))
    args = parser.parse_args()
    main(args.base_url.rstrip("/"), args.output)
