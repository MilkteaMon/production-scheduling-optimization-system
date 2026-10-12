# Commitments, What-if comparison and grounded explanation

This release extends the local application with three connected workflows. No paid AI call is
required for the manual planner workflow. The website still uses port 8000; isolated browser
tests use port 8011. Production jobs, earlier scenarios and schedules remain immutable.

## 1. Select hard deadlines

Load or select a workload, then choose **Plan commitments / What-if**. Check the exact orders
that must finish by their existing due times. Select **Preview rules**, review IDs and deadlines,
and choose **Confirm and calculate scenario**. This saves a new scenario and queues FCFS, EDD
and MILP with the selected bounded budget. Existing commitments cannot be removed from a child
scenario; select the original baseline to experiment with a different set of commitments.

The additional rule for each selected job is C_i <= d_i. Higher priority weight alone does not
guarantee timely completion. FCFS/EDD retain their non-delay dispatch rules and can violate hard
deadlines. Such runs are explicitly invalid and cannot be compared or exported as valid results.
CBC uses only valid heuristic warm starts/fallbacks; otherwise it must find its own feasible order.

Infeasible means no schedule can meet all selected requirements under these conditions.
An earliest-completion contradiction or a CBC infeasibility proof supports this statement.
Timeout without a schedule means feasibility remains unresolved. No KPI is invented for an
invalid schedule. Solver errors remain distinguishable from infeasibility.

## 2. Compare What-if scenarios

The same form can add exactly one identical machine to the current scenario, preserving its
commitments and the common horizon. Up to six machines are supported. Review and confirm each
proposal. The Scenarios page lists all saved scenarios, their machine/commitment counts, methods,
solver state and actual metrics. Identical derived inputs are reused; compatible cached runs at
the same solver budget are reused too. Re-run Optimize explicitly for a new solver attempt.

Differences in constraints or capacity are labelled. These are scheduling experiments, not
predictions or estimates of machine-purchase ROI. Original benchmark artifacts describe the
previous soft-deadline model and are not evidence of constrained-scenario performance.

## 3. Explain a selected run

Choose **Explain MILP/EDD/FCFS** on a scenario row, or use the explanation panel on Comparison.
Select an explicit baseline run to view KPI reductions and each order's completion, tardiness,
weight and contribution to objective change. Positive reductions mean improvement; percentages
are N/A when the baseline is zero. The contributions sum to the objective difference.

The panel reports observed changes and honest solver status. It does not invent a proof that a
particular order must precede another. Use another confirmed scenario to test an alternative
supported requirement. Precedence, custom deadlines, calendars and machine failures remain out
of scope. The complete explanation is available without AI.

## Optional language model interface

When configured, the single Copilot can translate requests such as "B must finish on time" into
a preview using exact job IDs in the current server-controlled context. A proposal does not
compute until the user reviews and confirms it. Unknown IDs and arbitrary constraint/code/SQL
requests cannot cross the tool boundary. At most six calls and one proposal or computation per
question are permitted. Numerical facts and explanations are rendered from calculated evidence.

OpenAI model choice remains explicit in OPENAI_MODEL; GPT-6.1 Sol uses gpt-6.1-sol. The SDK
explicitly uses low reasoning effort. Tracing remains disabled by default. DeepSeek is not yet
integrated as a provider. The original planning verification was offline; the later local
codex_subscription connection verified a real gpt-6.1-sol/low summary and combined deadline/machine
preview using the owner's ChatGPT login. Broad model quality and paid Platform API calls remain
unverified. See [Copilot activation](copilot.md) for the local-only transport and confirmation rules.

On this Windows host, a locked SQLAlchemy compiled DLL was blocked by application control.
Local verification uses the same SQLAlchemy 2.1.4 release rebuilt as its supported pure-Python
distribution with DISABLE_SQLALCHEMY_CEXT=1. Windows security settings were not changed and
dependency lock versions were not altered.

## API and exports

- POST /api/v1/scenarios/{id}/rules/preview: validate IDs and return exact proposed rules; no save.
- POST /api/v1/scenarios/{id}/rules: require confirmed=true, save/reuse scenario and return run IDs.
- GET /api/v1/runs/{id}/explanation?baseline_run_id=...: computed evidence for compatible runs.

Run responses and export manifests include must_finish_job_ids. Schedule CSV rows include
must_finish_on_time; KPI rows include hard_deadline_count and the selected IDs. The four-table
Power BI relationships and existing measures remain compatible. Refresh data types for added
columns when using them in a report. Exports reject invalid runs.

Startup applies migration 0003, adding an empty rule list to old scenarios. Existing dataset,
job, run and schedule rows are retained. Back up runtime/opspilot.db before your first startup
with the new migration if you want to preserve a rollback point. Running the application or its
checks never publishes code automatically; a separate Git commit/push is required.
