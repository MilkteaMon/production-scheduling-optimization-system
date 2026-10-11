# Synthetic samples

All three CSVs contain 30 jobs for a four-machine baseline, generated with seed 42 and generator
version 1.0. JSON sidecars retain parameters and hashes. These are illustrative synthetic
workloads, not calibrated factory distributions.

NumPy's seeded `default_rng` draws processing times from lognormal(mean=3.7, sigma=0.55), rounds
them to integer minutes, and clips to 10–120. The load reference is total processing time divided
by the baseline machine count. Due = release + processing + rounded slack. Relaxed slack is
uniform from 1.1 to 1.7 times that load, tight from 0.1 to 0.55, staggered from 0.2 to 0.65.
Relaxed/tight releases are zero; staggered releases are independently selected from 0, 60, 120,
and 180. Weights are uniform integers 1–10. NumPy version is locked for reproducibility.

Regenerate with `backend/.venv/Scripts/python.exe scripts/opspilot_samples.py` on Windows
(use `backend/.venv/bin/python` on Linux). The optional extra machine is added after generation,
without redrawing jobs or due times.

CSV columns are `job_id,processing_time_min,release_time_min,due_time_min,priority_weight`.
Column order may vary, but missing/duplicate/extra columns are rejected. Input must be UTF-8
(a BOM is supported), at most 1,048,576 bytes, and contain 1–50 jobs. Job IDs are unique, 1–64
ASCII letters, digits, underscores, or hyphens. Numeric fields must be whole integers; fractions,
NaN, infinity, and missing values are rejected. Times are minutes from zero. Processing is
1–10,080, release 0–525,600, due 0–1,051,200, and weight 1–10. Those upper bounds protect the
local MVP from extreme numerical scales. Due before earliest completion is accepted with an
unavoidable-lateness warning. Machine count is selected separately, from one to five.

The two `data/fixtures/` CSVs are small hand-checkable examples, separate from the synthetic
generator. Invalid previews and imports create no records; successful creation requires explicit
confirmation and calculates FCFS/EDD automatically.
