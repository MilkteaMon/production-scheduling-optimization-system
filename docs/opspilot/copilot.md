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
| Simulate one additional machine | Preview current commitments plus one machine; wait for confirmation |
| Is this calculation finished? | Read an authorized run's execution state and results |
| Orders A and B must finish on time | Preview exact existing due times in a new immutable scenario |
| Explain this result against a saved run | Read KPI differences and order-level weighted contributions |

These nine typed business tools reuse application services. The agent adds a conversational
way to find information, propose supported hard deadlines or invoke an existing operation.
The scheduling model, not the language model, enforces the constraints.
The Web UI remains the direct interface for every core workflow. A conversational interface can
help with combined lookup requests, while routine one-button tasks need no language model.

New workload descriptions use the separate **Describe workload** entry. Its extractor has no
tools and only returns an editable draft; explicit approval creates the workload and starts
scheduling. It does not give the analyst permission to edit existing jobs. See
[natural-language workloads](natural-language-workloads.md).

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

Scenario proposals never create or calculate a scenario until the user confirms in the Web UI.
The manual commitments form uses the same preview and application endpoints without an API key.
Existing commitments are inherited when adding a machine. See [AI planning workflow](ai-planning.md).

Tools do not edit original jobs, forecast delays, evaluate machine purchasing ROI, issue SQL, run shell
commands, browse the web or open arbitrary files. The import/generation controls create inputs.

## Activation and verification

AI is disabled by default. Set AI_ENABLED and OPENAI_MODEL, then choose an explicit AI_PROVIDER.
The default openai_api provider requires OPENAI_API_KEY and uses Platform API billing. The local
codex_subscription provider uses the official Codex CLI's existing ChatGPT login; it does not
read, copy or expose auth.json or tokens. All Web scheduling, comparison, scenario and export
features work without credentials. Questions and returned scheduling information are sent to
OpenAI only after the extension is enabled and used. No model is silently substituted.

The copilot explicitly sends `reasoning.effort = "low"` through the Agents SDK's Responses
model settings. Select a model that supports this effort; for GPT-6.1 Sol, set
`OPENAI_MODEL=gpt-6.1-sol`. Restart the backend after changing code or configuration.

For the owner's local subscription workflow, first run `codex login status` and verify that it
reports a ChatGPT login. Use these values in the ignored root .env, then restart the server:

```dotenv
AI_ENABLED=true
AI_PROVIDER=codex_subscription
OPENAI_MODEL=gpt-6.1-sol
OPENAI_AGENTS_DISABLE_TRACING=true
# CODEX_PATH=C:/path/to/the/official/codex.exe
```

The CLI must support --ignore-user-config and --ephemeral. Requests pin the model and low effort,
force ChatGPT authentication, remove API-key variables from the child environment, disable shell,
apps, plugins and delegation, and run stateless structured decisions in a temporary read-only
directory. The existing Agents SDK executes only the nine validated business tools. No native
Codex command/file/app activity is accepted. Each child has a 40-second timeout and is killed on
cancellation; the complete question has a 120-second budget. Remote SDK tracing is always off for
this provider. Login status is cached for the server lifetime; restart after changing accounts.

This mode is for the signed-in owner's local application on 127.0.0.1:8000. Remote clients,
non-local Host headers and cross-origin requests are rejected. Do not enable an owner's Codex
subscription on a publicly accessible deployment or CI runner. The public source defaults to
AI disabled and contains no account credentials. Subscription limits still apply.

The implementation follows [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk),
[non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) and
[official authentication](https://learn.chatgpt.com/docs/auth) guidance.

Local automated tests verify tool contracts, context restrictions, evidence rendering, transport
cancellation and mocked UI behavior without remote model calls. On 13 October 2026 (Singapore),
live subscription smoke checks verified gpt-6.1-sol/low connectivity, a grounded workload summary,
and a combined hard-deadline/additional-machine preview without computing a new scenario. These
are smoke checks, not a broad assessment of model quality. Paid Platform API calls remain untested.
Existing deterministic explanations and metric help do not use AI. See
[the AI development disclosure](../../AI_ASSISTANCE.md).
