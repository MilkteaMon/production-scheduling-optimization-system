# Archived adapter audit

These schedules validate, but this initial experiment does **not** verify the approved warm-start
configuration. The standalone Windows CBC build prepends `.\` to MIP-start filenames and did
not open the absolute filename used by adapter 1.0. The defect was discovered in final log review.
The absolute paths are visible in the original diagnostics/audit. The mathematical model and
heuristic retention remained valid; performance and optimality rates must be interpreted under
the defective adapter configuration.

Adapter 1.1 uses unique relative, space-free solver file prefixes without changing the process
working directory. A regression test requires CBC to report both reading and accepting the MIP
start. The corrected experiment is saved separately at `../full-60s/` and is the release report's
primary evidence. This archive preserves the initial results rather than concealing the defect.
