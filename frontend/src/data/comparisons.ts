import { fmt, labels, percentageReduction, type Run } from "../api/client";

export function comparisonExplanation(baseline: Run, next: Run) {
  if (!baseline.metrics || !next.metrics) return null;
  const b = baseline.metrics,
    n = next.metrics;
  const reduction = b.total_weighted_tardiness - n.total_weighted_tardiness;
  const percentage = percentageReduction(b.total_weighted_tardiness, n.total_weighted_tardiness);
  const objective =
    reduction === 0
      ? "Weighted tardiness is unchanged"
      : `Weighted tardiness ${reduction > 0 ? "decreases" : "increases"} by ${fmt(Math.abs(reduction))} weighted min`;
  const percentText =
    percentage === null
      ? "percentage reduction N/A because the baseline is zero"
      : `${fmt(Math.abs(percentage), 1)}% ${percentage >= 0 ? "reduction" : "increase"}`;
  const late = n.late_jobs - b.late_jobs;
  const span = n.makespan_min - b.makespan_min;
  const lateText =
    late === 0
      ? "Late-job count is unchanged"
      : `Late-job count ${late > 0 ? "increases" : "decreases"} by ${Math.abs(late)}`;
  const spanText =
    span === 0
      ? "makespan is unchanged"
      : `makespan ${span > 0 ? "increases" : "decreases"} by ${fmt(Math.abs(span))} min`;
  const status = next.proven_optimal
    ? "CBC established optimality and the schedule validates."
    : next.solver_status === "time_limit"
      ? "The solver reached its time limit; optimality remains unresolved."
      : "This validated result has no solver-established optimality claim.";
  return {
    title: `${labels[next.method]} compared with ${labels[baseline.method]}`,
    objective: `${objective} (${percentText}).`,
    tradeoffs: `${lateText}; ${spanText}.`,
    status,
  };
}
