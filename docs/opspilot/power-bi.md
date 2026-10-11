# Optional Power BI workflow

The application works without Power BI or a `.pbix` file. Select **Export** in the page header,
then choose **Current displayed run**, **FCFS / EDD / MILP comparison**, or **Baseline + one additional
machine**. Comparison options become available when their validated results exist. The dialog
lists every included method, machine count and run ID; downloading starts no new optimization.

The ZIP includes `jobs.csv`, `schedule.csv`, `machines.csv`, `kpis.csv`, `manifest.json`, a README,
`PowerBI-queries.pq` and `PowerBI-measures.dax`. Jobs are deduplicated by dataset/job and other tables
by their run keys. Export accepts at most six distinct compatible validated runs. The manifest
records exact run IDs, generator provenance, common job hash/horizon, budgets, versions and status.
Different machine counts are allowed. Different job data/horizons are rejected with HTTP 409.

## Import the package

1. Extract the ZIP into a stable folder, for example `C:\SchedulingReports\current`.
2. In Power BI Desktop, create a **Blank Query**, name it `ExportBundle`, and open **Advanced Editor**.
   Paste `PowerBI-queries.pq`; change its `ExportFolder` to your extracted folder.
3. Create four more Blank Queries named **Jobs**, **Schedule**, **Machines**, **RunKPIs**.
   Their formulas are respectively `= ExportBundle[Jobs]`, `= ExportBundle[Schedule]`,
   `= ExportBundle[Machines]`, `= ExportBundle[RunKPIs]`. Disable load for the record query
   ExportBundle, enable load for the four tables, then **Close & Apply**.
4. Create the three relationships below. Create each supplied DAX measure separately.
5. Add a single-select run_id slicer, KPI cards, a method comparison chart and a schedule table.
   Show machine count, termination, provenance and optimality beside performance numbers.

Alternatively use **Get data > Text/CSV** four times, preserving IDs as text and creating JobKey
manually. Do not combine all four different schemas with a single Folder Combine operation.
The `.pq` and `.dax` files are editable source. No native `.pbit`/`.pbix` template was fabricated;
Power BI Desktop execution has not been verified on this machine. Save your own `.pbix` after
checking that cards match the exported run snapshots. Query editing and model relationships follow
[Microsoft's Power Query guide](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-common-query-tasks)
and [relationship guide](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-create-and-manage-relationships).

## Tables and relationships

| Table | Grain | Keys and purpose |
|---|---|---|
| Jobs | One dataset/job | dataset_id + job_id; processing, release, due, priority |
| Machines | One run/machine | run_id + machine_code; busy time and both utilization denominators |
| Schedule | One run/job | run_id + job_id; assignment, start/completion, tardiness, weighted tardiness |
| RunKPIs | One run | run_id; method, scenario/dataset IDs, status, provenance, bound/gap, timing, metrics |

In Power Query, construct `JobKey = dataset_id & "|" & job_id` in Jobs and Schedule and
`RunMachineKey = run_id & "|" & machine_code` in Machines and Schedule. Remove duplicate Jobs
by JobKey after combining folders. Add `ScenarioKey = scenario_id` for slicers.

Create one-to-many single-direction relationships from Jobs[JobKey] to Schedule[JobKey],
RunKPIs[run_id] to Schedule[run_id], and RunKPIs[run_id] to Machines[run_id]. Avoid a second active
Machines-to-Schedule relationship that creates an ambiguous filter path; use RunMachineKey with
an inactive relationship or use the machine dimension only on an independently filtered report.
Require a single selected run for schedule KPI measures. Comparisons should use explicit runs
with the same dataset/hash and horizon, and display machine count.

Set IDs/status/method/provenance to Text; times/weights/counts to Whole Number where integral;
utilization/gaps/runtime to Decimal; optimality to True/False. Keep blank bounds/gaps as blanks,
never replace them with zero. Parse imported boolean text deliberately if automatic inference
does not recognize it.

## Example measures

```dax
Weighted Tardiness =
IF(HASONEVALUE(RunKPIs[run_id]), SUM(Schedule[weighted_tardiness]))

Late Jobs =
IF(HASONEVALUE(RunKPIs[run_id]),
   COUNTROWS(FILTER(Schedule, Schedule[tardiness_min] > 0)))

Makespan Minutes =
IF(HASONEVALUE(RunKPIs[run_id]), MAX(Schedule[completion_min]))

Window Utilization =
IF(HASONEVALUE(RunKPIs[run_id]),
   DIVIDE(SUM(Machines[busy_time_min]),
          MAX(RunKPIs[machine_count]) * MAX(RunKPIs[horizon_min])))

Span Utilization =
IF(HASONEVALUE(RunKPIs[run_id]),
   DIVIDE(SUM(Machines[busy_time_min]),
          MAX(RunKPIs[machine_count]) * [Makespan Minutes]))

Reduction Percent =
VAR B = [Explicit Baseline Weighted Tardiness]
VAR N = [Explicit New Weighted Tardiness]
RETURN IF(B > 0, DIVIDE(B - N, B), BLANK())
```

The final measure is a pattern: create two disconnected run-selector tables and measures that
apply each chosen run ID with TREATAS. Do not infer a baseline from row order or the largest value.
Format utilization/reduction as percentages. A baseline of zero yields blank/N/A; utilization
differences are 100 * (new - baseline) percentage points. Busy/H and busy/makespan answer different
questions. Both include unused machines in overall denominators.

## Suggested report and refresh

Use run/method/scenario slicers, KPI cards, late-job details, per-machine busy/utilization bars,
and a schedule table. Include solver termination, schedule source, optimality flag, time budget,
and runtime next to objective improvements. Label profiles synthetic. Never describe a heuristic
fallback as a CBC-proven optimum or calculated lateness as a predictive risk probability.

Export again after a completed new run; replace the four CSV files in the configured folder,
then refresh Power Query. For a new folder, update ExportFolder instead.
Run IDs distinguish repeated optimizations. Preserve earlier exports for audit. Validate sample
cards against the app's stored KPI snapshot after refresh. Additional-machine comparisons measure
scheduling effects and cannot determine capital expenditure ROI.
