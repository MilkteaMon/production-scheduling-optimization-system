# Workload library, reporting and metric help

Implemented after the initial local release verification. These changes preserve the scheduling
formulation, solver adapter, benchmark results and immutable job/run data.

## Workload library

The selector displays name, job/machine counts, profile/source, creation date and a short ID.
**Manage datasets** searches name/profile/seed/ID, shows creation time, and offers reversible
archive/restore. Archived data is excluded from the default selector but remains accessible by
ID and export. The separate `is_test` flag hides verification workloads by default.

Migration 0002 adds only visibility metadata. Existing `Browser verification` workloads are
classified as tests. A narrow name/source/data-hash/time match identifies the two original CSV
browser fixtures. Later user imports are preserved. New workloads using the reserved
`Browser verification` name prefix are classified as tests. No test history was deleted.

Browser local storage retains dataset, scenario, method and the show-test preference. Invalid or
inaccessible dataset/scenario selections fall back to an available workload/baseline. It stores
no credentials or production data. Browser tests start their own port-8011 backend with a fresh
ignored database; the personal application's database is never their default target.

## Power BI package

The header's **Export** dialog shows the exact included runs and allows the current run, three
methods, or baseline plus additional-machine scenarios. API validation requires 1–6 unique,
validated runs with the same job hash and horizon. Four CSV tables have consistent run keys;
jobs are deduplicated and string IDs such as `001` are preserved. The manifest retains budgets,
versions, provenance, solver state, optimality, supported bounds, timings and synthetic provenance.

The package supplies import instructions, editable Power Query M and DAX source. Relationships
are created explicitly using the included guide. It is not a native `.pbit`/`.pbix`; Power BI
Desktop execution remains unverified. Individual CSV endpoints remain available.

## Metric help and calculated interpretation

Nine help topics cover job counts, late jobs, weighted tardiness, makespan, both utilization
denominators, solver status, result source and gap. Each dialog includes a definition, formula,
example and current-run context. Keyboard focus is contained and restored after closing.

**What changed?** computes objective reduction, percentages and late-job/makespan tradeoffs from
the selected compatible runs. A zero baseline yields N/A. Optimality follows the recorded proof
flag; a time limit remains unresolved. These explanations require no AI or API key.

## Executed verification

- 52 backend tests: scheduling/oracle/failure checks plus archive integrity, strict requests,
  ZIP compatibility, table/KPI readback and migration classification.
- 8 frontend unit tests: existing API utilities plus filtering/search and grounded comparisons.
- 14 browser tests: complete desktop and Pixel 7 workflows, real CBC fixtures, all three ZIP
  download scopes and contents, archive/restore, persisted context, keyboard access, accessibility
  scans and layout checks. No paid AI calls.
- Ruff, ESLint, generated API contract/types and production TypeScript/Vite build passed.

The real application was backed up and restarted with no active runs. Migration readback
confirmed unchanged row counts for datasets, jobs, scenarios, machines, runs, schedule items and
copilot queries, and unchanged dataset hashes. Its 33 workloads remain stored; 30 verification
workloads are hidden by default and three normal workloads remain visible. This count describes
the local snapshot, not future user imports.

See [the current verification receipt](product-checks.json) and the checks linked inside it.
Initial release checks are retained separately. No new benchmark improvement claims are made.
Docker/Linux/GitHub CI and native Power BI execution were not run here.

## Manual GitHub handoff

The source bundle uses an explicit scheduling-system allowlist, verifies ZIP contents and SHA-256 values,
and supplies an scheduling-system README and blank AI configuration. Portfolio files, coursework, Git
history, databases, runtime and installed dependencies are excluded. The bundle is a snapshot,
not a second live working tree. No Git initialization, staging, commit, remote creation or push
was performed. [The manual guide](github-manual.md) explains extraction outside the mixed
workspace and each owner-operated Git/GitHub step.
