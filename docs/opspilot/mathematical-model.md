# Scheduling model and metric definitions

## Scope and feasibility

Each job executes once without interruption on one identical machine. Machines are available
from zero. Release times constrain starts; due times are soft targets except for explicitly
selected on-time commitments in an immutable scenario. Idle time is allowed.
Jobs have integer processing time p > 0, release r >= 0, due d >= 0, and priority weight w in 1–10.
There are no shifts, setups, precedence, maintenance, or multi-operation routes.

The common horizon is H = max(r) + sum(p). A serial schedule starting at max(r) proves feasibility
within H for the unconstrained workload. Hard deadlines can make a scenario infeasible. All
methods and derived scenarios use this same horizon. A heuristic makespan
does not replace H because that could exclude better weighted-tardiness schedules.

## Baselines

At every event, dispatch released unscheduled jobs to the lowest-code available machine. FCFS
sorts by release then job ID; EDD sorts by due, release, then job ID. When dispatch cannot continue,
advance to the next future release or machine completion. These are deterministic, non-delay
rules: neither reserves a machine for an unreleased job. Optimal weighted tardiness can require
intentional waiting, so neither heuristic is claimed optimal.

## MILP

For each job i and machine k, x(i,k) is binary assignment. For i < j, y(i,j) is a binary ordering
decision relevant when the jobs share a machine. Start S(i) is continuous; completion is the
expression C(i) = S(i) + p(i). T(i) >= 0 is tardiness. The implementation eliminates a separate
completion variable but uses the same mathematical constraints.

Minimize:

```text
sum_i w(i) T(i)
```

Constraints:

```text
sum_k x(i,k) = 1
r(i) <= S(i) <= H - p(i)
T(i) >= S(i) + p(i) - d(i)
0 <= T(i) <= max(0, H - d(i))
S(i) + p(i) <= d(i)  for selected hard-deadline jobs only

For all i < j and k, M = H:
S(i) + p(i) <= S(j) + M [3 - y(i,j) - x(i,k) - x(j,k)]
S(j) + p(j) <= S(i) + M [2 + y(i,j) - x(i,k) - x(j,k)]
```

When both jobs share k, y selects their order. Otherwise both expressions relax sufficiently
because starts are nonnegative and completion is at most H. At 50 jobs and five machines there
are 250 assignment binaries and 1,225 ordering binaries. The additional-machine case may use six
machines. There is no secondary makespan objective.

## Extraction, normalization, and status

CBC receives a complete warm start from the better independently valid baseline, when one
exists. If both heuristics violate hard deadlines, CBC starts without their invalid seed.
It receives a fixed seed of 42, a 60-second
default budget (API configurable from 1 to 120), and zero requested absolute/relative stopping
gap. The configured execution is serial. PuLP 4's `COIN_CMD` and structured solve statistics
provide termination and bound data; the legacy `PULP_CBC_CMD` API is not used.

Adapter 1.1 gives CBC unique relative, space-free solver filenames in the writable working directory and never changes that directory. This accommodates the Windows MIP-start loader. Native start-read/acceptance messages accompany the result, and temporary model files are ignored by Git. Solver runtime measures the PuLP solve call including adapter file I/O; total execution includes model construction and validation.

Only a reported incumbent is extracted. The independent validator checks job coverage/uniqueness,
machine membership, finite times, releases, duration, horizon, selected hard deadlines, and overlap
using tolerance 1e-5.
Assignment values must lie within that tolerance of binary values and sum to one. Invalid
candidates are rejected. For each extracted machine order, starts are left-shifted to the earliest
feasible integer times. That preserves releases and non-overlap and cannot increase tardiness.
All KPIs are recomputed. The best validated heuristic or candidate is retained, with its source.

Only an optimal termination with a valid retained solver candidate establishes optimality.
For soft-deadline inputs, infeasible/unbounded termination is unexpected and requires diagnostics.
For hard-deadline scenarios, CBC may prove infeasibility. An individual job whose release plus
processing exceeds its hard deadline is also a direct impossibility certificate. Timeout without
a feasible incumbent is not proof of infeasibility. Missing/crashed CBC and watchdog termination
never return a heuristic that violates the commitments. Runs without valid results have no KPI
snapshot or exported schedule. A contradictory bound or optimality claim is discarded.
Reported relative gap is (retained objective - lower bound) / max(abs(objective), 1), floored at
zero; it is null when no supported lower bound exists. The retained objective may be a better
heuristic than the last CBC candidate. A zero reported gap is not used to infer optimality.

## KPIs

```text
T(i) = max(0, C(i) - d(i))
Late jobs = count(T(i) > 0)
Weighted tardiness = sum_i w(i) T(i)                  [weighted minutes]
Makespan = max_i C(i)                                [minutes from zero]
Busy(k) = sum of processing time on k                [minutes]
Window utilization(k) = Busy(k) / H
Span utilization(k) = Busy(k) / makespan
Overall window utilization = sum(p) / (machines * H)
Overall span utilization = sum(p) / (machines * makespan)
```

Busy time includes processing only. Release waiting and idle gaps remain in the denominator.
Unused machines have zero busy time and utilization. Overall fixed-window utilization cannot
improve solely through reordering the same jobs on the same machines. The extra machine enlarges
the denominator, so lower utilization can accompany lower tardiness.

For lower-is-better metrics, absolute reduction is baseline minus new; percentage reduction is
100 * (baseline - new) / baseline only when baseline > 0. Otherwise it is N/A, represented as
null. Negative reductions mean deterioration. Utilization uses percentage-point changes.

## Hand-checkable evidence

1. A: p=3, r=0, d=2, w=1; B: p=2, r=0, d=2, w=3. On one machine,
   B then A costs 3; A then B costs 10. CBC establishes objective 3.
2. A: p=10, r=0, d=100, w=1; B: p=1, r=1, d=2, w=10. Non-delay dispatch costs
   90. Waiting until minute one for B then processing A costs zero. CBC establishes zero.

Tests independently enumerate machine assignments and every machine order for randomized cases
with up to six jobs and two machines. The oracle evaluates earliest starts directly and does not
reuse the model, heuristics, or validator. See the test suite and executed validation report.
