# AI assistance disclosure — Production Scheduling Optimization System

This application was implemented with substantial AI assistance from Codex. AI generated and
revised the scheduling model implementation, backend, frontend, tests, packaging, and technical
documentation. The owner supplied and approved the implementation plan and its MVP assumptions.

Automated validation was executed locally: hand-verifiable mathematical fixtures, an independent
enumeration oracle, property tests, API and worker failure checks, mocked copilot tests, browser
workflows, accessibility scans, and reproducible synthetic benchmarks. These checks provide
evidence about software behavior; they do not establish that a human reviewed every line or
validated suitability for a particular factory.

Human review of the model, planner workflow, and portfolio claims remains an owner checkpoint.
No human code-review session, production trial, customer feedback, commercial benefit, or live
AI evaluation is claimed. See [validation](docs/opspilot/validation.md) and the actual experiment
artifacts before presenting results.

The optional product copilot is distinct from AI assistance during development. It uses one
OpenAI agent with seven business tools. The model chooses evidence references and approved
interpretation categories; application code renders facts and numerical values. It cannot edit
jobs, issue SQL, execute shell commands, access arbitrary files, or browse the web. API requests
send the user's question and tool-returned scheduling information to the configured provider;
enable it only for data you intend to send. Remote SDK tracing is disabled by default.

The system's outputs include an interactive Web dashboard and Power BI-compatible CSV data
packages with Power Query and DAX source. AI is an optional extension: the core scheduling,
comparisons, scenarios and reporting workflow runs without credentials. Native Power BI Desktop
import and a live paid AI evaluation have not been verified locally.

Local mock tests do not make paid requests. No paid live API tests, public hosting, or repository
publication were performed as part of this implementation.
