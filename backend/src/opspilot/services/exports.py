"""Bounded, compatible, read-only exports for a local Power BI workflow."""

import csv
import io
import json
import zipfile

from fastapi import HTTPException

from opspilot.branding import PRODUCT_NAME
from opspilot.persistence.models import now

POWER_QUERY = r"""// Power BI: create a Blank Query named ExportBundle, then paste into Advanced Editor.
// Change only ExportFolder to the folder containing the extracted CSV files.
let
    ExportFolder = "C:\replace-with-your-export-folder",
    Load = (filename as text) as table => Table.PromoteHeaders(
        Csv.Document(File.Contents(ExportFolder & "/" & filename),
            [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
        [PromoteAllScalars=true]),
    Jobs = Table.AddColumn(Table.TransformColumnTypes(Load("jobs.csv"),
        {{"processing_time_min", Int64.Type}, {"release_time_min", Int64.Type},
         {"due_time_min", Int64.Type}, {"priority_weight", Int64.Type}}, "en-US"),
        "JobKey", each [dataset_id] & "|" & [job_id], type text),
    Schedule = Table.AddColumn(Table.TransformColumnTypes(Load("schedule.csv"),
        {{"start_min", Int64.Type}, {"completion_min", Int64.Type},
         {"due_time_min", Int64.Type}, {"tardiness_min", Int64.Type},
         {"priority_weight", Int64.Type}, {"weighted_tardiness", type number}}, "en-US"),
        "JobKey", each [dataset_id] & "|" & [job_id], type text),
    Machines = Table.TransformColumnTypes(Load("machines.csv"),
        {{"job_count", Int64.Type}, {"busy_time_min", Int64.Type},
         {"window_utilization", type number}, {"span_utilization", type number},
         {"horizon_min", Int64.Type}, {"schedule_span_min", Int64.Type}}, "en-US"),
    KPIBlanks = Table.ReplaceValue(Load("kpis.csv"), "", null, Replacer.ReplaceValue,
        {"best_bound", "relative_gap"}),
    KPITypes = Table.TransformColumnTypes(KPIBlanks,
        {{"total_jobs", Int64.Type}, {"late_jobs", Int64.Type},
         {"total_weighted_tardiness", type number}, {"makespan_min", Int64.Type},
         {"window_utilization", type number}, {"span_utilization", type number},
         {"horizon_min", Int64.Type}, {"machine_count", Int64.Type},
         {"time_limit_seconds", Int64.Type}, {"best_bound", type number},
         {"relative_gap", type number}, {"solver_runtime_seconds", type number},
         {"total_runtime_seconds", type number}}, "en-US"),
    RunKPIs = Table.TransformColumns(KPITypes, {{"proven_optimal", each
        if Text.Lower(_) = "true" then true
        else if Text.Lower(_) = "false" then false
        else error "Invalid optimality flag", type logical}})
in
    [Jobs=Jobs, Schedule=Schedule, Machines=Machines, RunKPIs=RunKPIs]
// Add four more Blank Queries (names and formulas):
// Jobs: = ExportBundle[Jobs]
// Schedule: = ExportBundle[Schedule]
// Machines: = ExportBundle[Machines]
// RunKPIs: = ExportBundle[RunKPIs]
// Disable load for ExportBundle; load the four table queries.
"""

DAX = """// Create each measure separately. RunKPIs[run_id] must select one run for cards.
Weighted Tardiness =
IF(HASONEVALUE(RunKPIs[run_id]), SUM(Schedule[weighted_tardiness]))

Late Jobs =
IF(HASONEVALUE(RunKPIs[run_id]), COUNTROWS(FILTER(Schedule, Schedule[tardiness_min] > 0)))

Makespan Minutes =
IF(HASONEVALUE(RunKPIs[run_id]), MAX(Schedule[completion_min]))

Window Utilization =
IF(HASONEVALUE(RunKPIs[run_id]), MAX(RunKPIs[window_utilization]))

Span Utilization =
IF(HASONEVALUE(RunKPIs[run_id]), MAX(RunKPIs[span_utilization]))
"""

README = """# Production Scheduling Optimization System — Power BI data package

The application provides a Web dashboard, Power BI data exports and an optional AI copilot
extension. Core scheduling and these exports work without AI credentials.

Extract this ZIP into a folder before importing. All schedules were independently validated.
jobs.csv contains one row per dataset/job; schedule.csv one row per run/job;
machines.csv one row per run/machine; kpis.csv one row per run. Each run's status,
provenance, bounds, budget and timestamps are preserved. manifest.json records the exact
selected run IDs and configuration. No new calculation is started by exporting.

## Start in Power BI Desktop

Home > Get data > Text/CSV: import each of the FOUR CSV files separately, or use
PowerBI-queries.pq as the Advanced Editor source of a Blank Query named ExportBundle.
Change ExportFolder, then add four Blank Queries Jobs, Schedule, Machines and RunKPIs
using = ExportBundle[Jobs], = ExportBundle[Schedule], = ExportBundle[Machines] and
= ExportBundle[RunKPIs]. Disable load for ExportBundle; load the four table queries.
The supplied Power Query source prepares types and JobKey. It is source text, not a
native .pbit/.pbix file; native Power BI execution is not claimed by this export.

In Model view, use these active, single-direction 1:* relationships:
Jobs[JobKey] -> Schedule[JobKey]
RunKPIs[run_id] -> Schedule[run_id]
RunKPIs[run_id] -> Machines[run_id]
For manual CSV import, add JobKey = [dataset_id] & "|" & [job_id] in Jobs and Schedule.
One-side keys must be unique. Avoid a second active Machines-to-Schedule filter path.

Create the measures in PowerBI-measures.dax separately. Add a single-select run_id slicer,
KPI cards, a machine_code utilization bar chart, and a schedule table. Format utilization
as percentages. Include machine_count, method, solver_status, result_source and
proven_optimal beside comparisons. For a method chart, filter to explicit selected run IDs;
do not add unrelated or repeated runs as if they were a single schedule.

## Refresh and interpret

Replace these CSV files with a newly extracted compatible export, then Home > Refresh.
Do not use Folder Combine on all four CSV schemas together. Keep previous packages for audit.
All times are minutes from planning zero; weights are 1-10; weighted tardiness is weighted
minutes, not currency. Utilization values are fractions (0.25 means 25%). Unknown bounds and
gaps stay blank. A zero comparison baseline gives N/A percentage reduction.
The fixed horizon is max(release)+sum(processing), not a real factory shift.
Completion does not imply proven optimality. Time-limited schedules are best-known feasible
results; additional-machine outcomes do not establish purchasing ROI. Synthetic sources
are identified in manifest.json. Input jobs are not edited by this package.
"""


def power_bi_bundle(service, run_ids: list[str]) -> bytes:
    if not 1 <= len(run_ids) <= 6 or len(set(run_ids)) != len(run_ids):
        raise HTTPException(422, "Choose between one and six distinct runs")
    results = [service.require_result(id) for id in run_ids]
    first_data = results[0][1]
    if any(
        data.job_hash != first_data.job_hash or data.horizon_min != first_data.horizon_min
        for _, data, _, _ in results
    ):
        raise HTTPException(409, "Export runs must share job data and planning horizon")

    datasets = {
        scenario["dataset_id"]: service.dataset_detail(scenario["dataset_id"])
        for _, _, _, scenario in results
    }
    manifest = {
        "application": PRODUCT_NAME,
        "format_version": "1.0",
        "exported_at_utc": now(),
        "job_hash": first_data.job_hash,
        "horizon_min": first_data.horizon_min,
        "units": {
            "times": "minutes from planning zero",
            "objective": "weighted minutes",
            "utilization": "fraction",
            "gap": "fraction",
            "runtime": "seconds",
        },
        "datasets": [
            {
                key: dataset[key]
                for key in [
                    "id",
                    "name",
                    "source_kind",
                    "seed",
                    "generator_params",
                    "job_hash",
                    "created_at",
                    "is_test",
                ]
            }
            for dataset in datasets.values()
        ],
        "runs": [
            {
                key: run[key]
                for key in [
                    "id",
                    "scenario_id",
                    "method",
                    "input_hash",
                    "model_version",
                    "solver_config",
                    "execution_state",
                    "solver_status",
                    "result_source",
                    "proven_optimal",
                    "has_valid_schedule",
                    "best_bound",
                    "relative_gap",
                    "metrics",
                    "created_at",
                    "finished_at",
                ]
            }
            for run, _, _, _ in results
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table in ["jobs", "machines", "schedule", "kpis"]:
            rows = []
            seen = set()
            columns = None
            keys = {
                "jobs": ["dataset_id", "job_id"],
                "machines": ["run_id", "machine_code"],
                "schedule": ["run_id", "job_id"],
                "kpis": ["run_id"],
            }[table]
            for id in run_ids:
                reader = csv.DictReader(io.StringIO(service.export(id, table)))
                if columns is None:
                    columns = reader.fieldnames
                elif reader.fieldnames != columns:
                    raise HTTPException(409, "Export schemas differ")
                for row in reader:
                    key = tuple(row[k] for k in keys)
                    if key not in seen:
                        rows.append(row)
                        seen.add(key)
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            archive.writestr(f"{table}.csv", output.getvalue().encode("utf-8"))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
        archive.writestr("README.md", README)
        archive.writestr("PowerBI-queries.pq", POWER_QUERY)
        archive.writestr("PowerBI-measures.dax", DAX)
    return buffer.getvalue()
