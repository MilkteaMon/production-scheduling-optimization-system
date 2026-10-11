from types import SimpleNamespace

import pulp
import pytest

from opspilot.domain.models import Job, PlanningInput
from opspilot.scheduling.milp import optimize


@pytest.mark.parametrize(
    "status,has_solution,source",
    [
        ("TimeLimit", True, "cbc_incumbent"),
        ("TimeLimit", False, "heuristic_fallback"),
        ("Infeasible", False, "heuristic_fallback"),
        ("Unbounded", False, "heuristic_fallback"),
        ("GapLimit", True, "cbc_incumbent"),
    ],
)
def test_solver_outcomes_never_claim_optimal(monkeypatch, status, has_solution, source):
    stats = SimpleNamespace(
        status_str=status,
        has_solution=has_solution,
        best_bound=None,
        time=0.01,
        solver_version="mock",
        objective=None,
    )
    monkeypatch.setattr(pulp.LpProblem, "solve", lambda *args: stats)
    monkeypatch.setattr("opspilot.scheduling.milp.solver_available", lambda: True)
    data = PlanningInput(
        jobs=[
            Job(
                job_id="A",
                processing_time_min=2,
                release_time_min=0,
                due_time_min=1,
                priority_weight=1,
            )
        ],
        machine_count=1,
    )
    result = optimize(data, 0.001)
    assert not result.proven_optimal
    assert result.result_source == source
    assert not result.validation_errors
    assert result.best_bound is None and result.relative_gap is None


def test_fractional_solver_output_is_rejected(monkeypatch):
    def fake(model, solver):
        for v in model.variables():
            if v.name.startswith("x_"):
                v.setInitialValue(0.5)
        return SimpleNamespace(
            status_str="TimeLimit",
            has_solution=True,
            best_bound=None,
            time=0,
            solver_version="mock",
            objective=None,
        )

    monkeypatch.setattr(pulp.LpProblem, "solve", fake)
    monkeypatch.setattr("opspilot.scheduling.milp.solver_available", lambda: True)
    data = PlanningInput(
        jobs=[
            Job(
                job_id="A",
                processing_time_min=2,
                release_time_min=0,
                due_time_min=1,
                priority_weight=1,
            )
        ],
        machine_count=1,
    )
    result = optimize(data)
    assert result.result_source == "heuristic_fallback" and result.solver_status == "error"
    assert any("nonintegral" in d for d in result.diagnostics)
