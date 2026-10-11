import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from opspilot.analytics.metrics import reduction
from opspilot.domain.models import Job, Placement, PlanningInput
from opspilot.scheduling.heuristics import schedule_heuristic
from opspilot.scheduling.milp import optimize
from opspilot.scheduling.validation import validate_schedule


def job(id, p, r=0, d=0, w=1):
    return Job(
        job_id=id, processing_time_min=p, release_time_min=r, due_time_min=d, priority_weight=w
    )


def exhaustive_objective(data):
    """Independent enumeration of assignments and orders; no scheduler imports."""
    best = float("inf")
    for assignment in itertools.product(range(data.machine_count), repeat=len(data.jobs)):
        groups = [
            [j for j, k in zip(data.jobs, assignment) if k == machine]
            for machine in range(data.machine_count)
        ]
        for orders in itertools.product(*(itertools.permutations(g) for g in groups)):
            total = 0
            for order in orders:
                finish = 0
                for j in order:
                    finish = max(finish, j.release_time_min) + j.processing_time_min
                    total += max(0, finish - j.due_time_min) * j.priority_weight
            best = min(best, total)
    return best


@pytest.mark.parametrize(
    "jobs,expected",
    [
        ([job("A", 3, d=2), job("B", 2, d=2, w=3)], 3),
        ([job("A", 10, d=100), job("B", 1, r=1, d=2, w=10)], 0),
    ],
)
def test_hand_verified(jobs, expected):
    data = PlanningInput(jobs=jobs, machine_count=1)
    result = optimize(data, 10)
    assert result.proven_optimal, result.diagnostics
    assert result.metrics.total_weighted_tardiness == expected
    assert not result.validation_errors


@settings(max_examples=12, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(1, 6), st.integers(0, 6), st.integers(0, 15), st.integers(1, 5)),
        min_size=1,
        max_size=6,
    ),
    st.integers(1, 2),
)
def test_exhaustive_matches_milp(rows, machines):
    data = PlanningInput(
        jobs=[job(f"J{i}", *row) for i, row in enumerate(rows)], machine_count=machines
    )
    result = optimize(data, 10)
    assert result.proven_optimal, result.diagnostics
    assert result.metrics.total_weighted_tardiness == exhaustive_objective(data)


@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(1, 120), st.integers(0, 200), st.integers(0, 600), st.integers(1, 10)
        ),
        min_size=1,
        max_size=50,
    ),
    st.integers(1, 6),
)
def test_baselines_always_feasible(rows, machines):
    data = PlanningInput(
        jobs=[job(f"J{i}", *row) for i, row in enumerate(rows)], machine_count=machines
    )
    for method in ["fcfs", "edd"]:
        result = schedule_heuristic(data, method)
        assert not validate_schedule(data, result.placements)
        assert result.placements == schedule_heuristic(data, method).placements


def test_validator_detects_overlap_release_duration_missing_machine():
    data = PlanningInput(jobs=[job("A", 3, r=2), job("B", 2)], machine_count=1)
    bad = [
        Placement(job_id="A", machine_code="M1", start_min=0, completion_min=3),
        Placement(job_id="B", machine_code="M1", start_min=1, completion_min=4),
    ]
    assert len(validate_schedule(data, bad)) >= 3
    assert validate_schedule(data, bad[:1])
    assert validate_schedule(data, [bad[0].model_copy(update={"machine_code": "M9"}), bad[1]])


def test_due_boundary_and_empty_machines():
    data = PlanningInput(jobs=[job("A", 3, r=2, d=5)], machine_count=3)
    result = schedule_heuristic(data, "edd")
    assert result.metrics.late_jobs == 0
    assert result.metrics.makespan_min == 5
    assert result.placements[0].start_min == 2


def test_window_utilization_is_invariant():
    data = PlanningInput(
        jobs=[job("A", 8, d=20), job("B", 2, d=3), job("C", 3, r=2, d=5)], machine_count=2
    )
    assert (
        schedule_heuristic(data, "fcfs").metrics.window_utilization
        == schedule_heuristic(data, "edd").metrics.window_utilization
    )
    assert reduction(0, 0)["percentage_reduction"] is None


def test_missing_solver_falls_back(monkeypatch):
    monkeypatch.setattr("opspilot.scheduling.milp.solver_available", lambda: False)
    result = optimize(PlanningInput(jobs=[job("A", 2)], machine_count=1))
    assert result.result_source == "heuristic_fallback"
    assert result.solver_status == "error"
    assert not result.proven_optimal
    assert not result.validation_errors


def test_six_job_two_machine_oracle():
    data = PlanningInput(
        jobs=[
            job("A", 3, 0, 3, 2),
            job("B", 4, 1, 6, 5),
            job("C", 2, 0, 4, 3),
            job("D", 5, 2, 7, 1),
            job("E", 1, 3, 5, 8),
            job("F", 3, 0, 6, 4),
        ],
        machine_count=2,
    )
    result = optimize(data, 10)
    assert result.proven_optimal, result.diagnostics
    assert result.metrics.total_weighted_tardiness == exhaustive_objective(data)


def test_windows_relative_warm_start_is_actually_loaded():
    from opspilot.domain.models import GenerateRequest
    from opspilot.services.data import generate_data

    result = optimize(
        generate_data(GenerateRequest(job_count=35, machine_count=3, profile="staggered", seed=0)),
        10,
    )
    assert result.proven_optimal and result.metrics.total_weighted_tardiness == 0
    assert any("MIPStart values read" in line for line in result.diagnostics)
    assert any("MIPStart provided solution" in line for line in result.diagnostics)
