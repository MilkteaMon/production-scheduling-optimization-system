# Verification and owner checkpoints

## Executed locally

The automated checks run on Windows 11 with Python 3.13.15, Node.js 24, PuLP 4.0.0, and official
CBC 2.10.13. The backend test suite covers:

- Both hand-checkable optima (weighted tardiness 3 and 0), due-date equality, one job, unused machines,
  deterministic ties, and accepted unavoidable lateness.
- Independent enumeration of assignments/orders for randomized cases up to six jobs/two machines,
  plus an explicit six-job case. One hundred property examples check both heuristics across varying
  releases, priorities, and sizes up to 50 jobs/six machines.
- CSV BOM/UTF-8, malformed rows, duplicate IDs/columns, fractional/nonfinite values, size limits,
  invalid weights, immutable scenarios, exports, compatible comparisons, and zero denominators.
- Mocked solver time limits with/without incumbents, gap termination, infeasible/unbounded statuses,
  fractional assignments, and missing CBC. No fallback is treated as solver-established optimum.
- Restart interruption while completed schedules remain intact, bounded queue saturation and atomic
  dataset creation, watchdog tree termination, and explicit worker-crash failure with usable baselines.
- Copilot tool allowlist, cross-dataset rejection, one computation per question, deduplication, six-call
  maximum, invalid evidence fallback, backend-supplied numerical values, and a persisted mocked-agent
  response. No remote model call is made by these tests.

Frontend unit tests cover status/method selection and zero-baseline percentage handling. TypeScript,
ESLint, Ruff, and the production build pass. Plotly is loaded in a separate lazy chunk; Vite still warns
about its chart bundle size. The warning describes a performance opportunity, not a failed build.

Eight Playwright checks exercise desktop and Pixel 7 viewports: generate→baseline→MILP→comparison→extra
machine→disabled copilot→CSV export; CSV validation followed by explicit confirmation; and keyboard
focus trapping/restoration/Escape. A fourth mocked-copilot check exercises evidence links and deterministic completion cards, without contacting a model provider. The real CBC solver runs during the scheduling workflow. Automated axe scans
of overview and the data dialog have no WCAG 2 A/AA violations. Both viewports have no horizontal body
overflow or uncaught page errors in the tested workflow. Screenshots are saved under `screenshots/`.
Automated scans are not a complete manual accessibility assessment.

A final solver audit caught an absolute-path warm-start defect in the initial adapter. Adapter 1.1 uses unique relative paths; a regression requires native CBC log confirmation that the start was read and accepted. The initial schedules remain archived with the defect disclosed.

The corrected complete fixed benchmark and the default 30-job demonstration are stored as actual artifacts;
see `experiments.md`, `experiments/results/full-60s/`, and `demo-artifacts/receipt.json` for outcomes.
Final run counts and fresh-install evidence are recorded in `release-checks.json`.

## Platform and release limits

Windows packaged CBC initially failed because Smart App Control blocked DLLs. The official standalone
distribution passed solver smoke checks without altering security policy. Pandas 3.0.6 also hit a
blocked native module, and the working 2.3.3 release is pinned. Source/archive provenance is recorded
locally; those downloaded binaries and all application databases stay outside version control.

Docker Desktop and a Linux distribution are absent. Multi-stage Docker/Compose packaging and
Windows/Linux CI checks are prepared, but no local Linux/container execution or remote CI success is
claimed. GitHub publication, public hosting, paid live API tests, and production UAT were not performed.

An isolated fresh source copy installs dependencies from `uv.lock` and `package-lock.json`, builds the
frontend, and runs backend verification. This is a clean-install check, not a literal remote clean
clone: no new public/private GitHub repository has been created for this application.

## Owner review

The plan's M2, M3, and pre-release checkpoints remain available for owner review; automated tests do
not replace those decisions. Review the hand fixtures/model assumptions and status interpretation,
the planner workflow and utilization denominators, then portfolio screenshots/experimental claims
and `AI_ASSISTANCE.md`. There is no fabricated human review log or customer validation.

Before presenting a full platform-verified release, execute CI on the intended repository and check
the Linux/Docker smoke results. A live AI smoke test is optional and requires the owner's explicit
authorization to use paid credentials. Public release remains a separate decision.
