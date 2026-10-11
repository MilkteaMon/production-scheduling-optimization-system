# Demonstration walkthrough

Start the built app and backend using `PRODUCTION_SCHEDULING_README.md`. No AI key is needed. The walkthrough
uses actual generated data and calculated results; it does not promise a particular percentage
improvement or optimality within 60 seconds.

1. Open **Load data**. Keep 30 jobs, four machines, Tight deadlines, seed 42; choose a descriptive
   name. Confirm generation. Inspect the Synthetic label and the automatically calculated FCFS/EDD
   baselines. Alternatively preview `data/samples/tight-30-jobs.csv` and explicitly confirm its import.
2. Select EDD. Explain weighted tardiness and the selected run displayed alongside the KPIs.
   Hover or select a job in the Gantt, then open **Production schedule** for the accessible table.
   Jobs ending exactly at due time have zero tardiness; a due date is not a hard deadline constraint.
3. Select **Optimize schedule**. The request returns immediately with queued/running state. The UI
   polls every two seconds. On completion, show solver termination, provenance, runtime, gap, and
   the independent-validation label. A completed time-limited run is a validated best-known
   schedule. Only the explicit **Proven optimal** label means CBC established optimality.
4. Open **Comparison**. Compare the actual weighted-tardiness objective against both baselines,
   and inspect late-job/makespan tradeoffs. Percentage reduction is N/A for a zero baseline.
   Explain why fixed-window utilization cannot change solely through rescheduling these jobs.
5. Open **Scenarios**, then simulate exactly one additional machine. Original jobs and results
   remain stored. Compare the best known schedules and machine counts under the same horizon.
   Lower window utilization can accompany less tardiness because capacity enlarged the denominator.
6. Select **Export** and choose the current run, three methods, or baseline/extra-machine results.
   Download the ZIP and inspect its four CSV tables and matching manifest run IDs. Use the included
   Power Query source and DAX with the Power BI guide. Individual CSV links remain available.
7. Open **AI copilot** to show that AI is optional. If explicitly configured later, ask for late
   orders or utilization; show evidence cards and local tool activity. For optimization, queued
   completion cards render application-calculated numbers. Do not claim a live evaluation from
   the mocked tests.

For a quick proof-focused demo, import `data/fixtures/priority-tradeoff.csv` on one machine.
FCFS/EDD produce weighted tardiness 10; MILP establishes 3 by processing B before A. The intentional
waiting fixture demonstrates why non-delay dispatch can cost 90 while the optimum is zero.

The saved screenshots are captured from the running application. Desktop/mobile verification
screenshots use an eight-job browser fixture so the small optimum can be checked quickly.
The separately saved default-demo receipt records the actual 30-job, four-machine experiment and
five-machine scenario, with CSV exports. Their outcomes are evidence for that seed, not population
or commercial claims.

The owner should review model assumptions, planner/KPI presentation, and final portfolio claims
before public release. Public hosting and paid live AI tests require separate decisions.

For the workflow improvements, open **Manage datasets** to search by name/profile/seed/ID,
archive and restore a workload, or reveal hidden test data. The selector includes job/machine counts,
profile, date and ID; it remembers the chosen dataset, scenario and method after refresh.
Select a metric's question-mark button for its formula, example and selected-run values. In
Comparison, **What changed?** derives its objective and tradeoff statements from calculated KPIs.
