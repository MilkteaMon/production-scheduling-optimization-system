# Optional AI copilot extension

Production Scheduling Optimization System provides an interactive Web dashboard, Power BI data
exports and an optional AI copilot extension. The complete planner workflow is usable with AI
disabled. Core scheduling uses deterministic heuristics and a mathematical MILP solved by CBC.

## What the copilot can do

| Natural-language request | Existing application function |
|---|---|
| Summarize this workload and selected schedule | Read job/machine totals and stored KPIs |
| Which orders are late? | Read lateness calculated for the selected validated run |
| Which machines are busiest? | Read busy time and both defined utilization measures |
| Compare FCFS, EDD and MILP | Compare existing compatible validated runs |
| Optimize the current workload | Queue one bounded MILP run, then return pending run IDs |
| Simulate one additional machine | Create/reuse that scenario and queue its schedules |
| Is this calculation finished? | Read an authorized run's execution state and results |

These seven typed business tools reuse application services. The agent adds a conversational
way to find information or invoke an existing operation; it does not add a new scheduling model.
The Web UI remains the direct interface for every core workflow. A conversational interface can
help with combined lookup requests, while routine one-button tasks need no language model.

## How answers are grounded

The model selects evidence references, factual keys and an approved interpretation category.
Application code inserts the numerical values and calculations. Approved interpretations explain
priority tradeoffs, time limits, capacity, utilization and calculated lateness. This version does
not generate unrestricted analytical narratives or editable production plans.

The server confines context to the selected workload, permits at most six business tool calls and
one new computation request per question, and deduplicates repeated computation requests. Queue
tools return pending handles; the UI polls results and renders deterministic completion cards.
Invalid evidence references fall back to application-rendered facts. Local tool traces preserve
evidence; remote SDK tracing is disabled by default.

Tools do not edit jobs, forecast delays, evaluate machine purchasing ROI, issue SQL, run shell
commands, browse the web or open arbitrary files. The import/generation controls create inputs.

## Activation and verification

AI is disabled by default. Explicit AI_ENABLED, OPENAI_API_KEY and OPENAI_MODEL configuration is
required; no model is silently substituted. All Web scheduling, comparison, scenario and export
features work without credentials. Questions and returned scheduling information are sent to the
configured AI provider only after the extension is enabled and used.

Local tests verify tool contracts, context restrictions, evidence rendering and mocked UI
behavior. They make no paid API calls. A live agent smoke test and assessment of actual model
quality remain unexecuted. Existing deterministic comparison explanations and metric help do not
use the AI extension. See [the AI development disclosure](../../AI_ASSISTANCE.md).
