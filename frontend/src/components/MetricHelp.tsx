import { CircleHelp, X } from "lucide-react";
import type { Dataset, Run } from "../api/client";
import { fmt, percent } from "../api/client";
import DialogFrame from "./DialogFrame";

export const metricTopics = {
  total_jobs: {
    title: "Total production jobs",
    description:
      "The number of jobs in the selected workload. Each job must be processed exactly once on one machine.",
    formula: "Count of input jobs",
    example: "30 orders create 30 processing tasks; adding a machine keeps the same 30 jobs.",
  },
  late_jobs: {
    title: "Late jobs",
    description:
      "Jobs finishing after their due time under this calculated schedule. Due times are soft targets; completion exactly at the due time counts as on time.",
    formula: "Count of jobs with completion > due",
    example: "A job late by 1 minute and a job late by 100 minutes each count as one late job.",
  },
  total_weighted_tardiness: {
    title: "Weighted tardiness",
    description:
      "Delay multiplied by each job's priority weight, summed across all jobs. This is the only optimization objective. Weights express importance; the result is not a monetary cost.",
    formula: "Σ weight × max(0, completion − due)",
    example:
      "A: 10 min late × weight 1 = 10. B: 5 min late × weight 4 = 20. Total = 30 weighted minutes; actual delays sum to 15 min.",
  },
  makespan_min: {
    title: "Makespan",
    description:
      "Time from planning zero until the last job finishes. Release waiting and idle gaps are included. Minimizing weighted tardiness can produce a longer makespan.",
    formula: "max(job completion time)",
    example: "Jobs finishing at minutes 25, 40 and 60 give a makespan of 60 minutes.",
  },
  window_utilization: {
    title: "Fixed-window utilization",
    description:
      "Processing time divided by the common fixed planning window and machine count. The window is a mathematical comparison horizon, not a real factory shift. Reordering the same jobs on the same machines cannot change overall window utilization.",
    formula: "Σ processing / (machine count × H); H = max(release) + Σ processing",
    example:
      "Two machines, 120 processing minutes, H=120: overall utilization = 120 / (2×120) = 50%. Adding capacity increases the denominator.",
  },
  span_utilization: {
    title: "Schedule-span utilization",
    description:
      "Processing time divided by the actual schedule makespan and machine count. Earlier overall completion can raise this measure. Unused machines are included in the overall denominator.",
    formula: "Σ processing / (machine count × makespan)",
    example:
      "Two machines, 120 processing minutes, makespan=80: overall utilization = 120 / (2×80) = 75%.",
  },
  status: {
    title: "Result status",
    description:
      "Execution state, solver termination and optimality are separate. Completed means execution ended. Proven optimal requires CBC's optimal termination and successful independent validation.",
    formula: "Validated baseline / Feasible · time limited / Proven optimal",
    example:
      "A completed time-limited run can have a valid schedule while its optimality remains unresolved. A zero reported gap alone is not an optimality proof.",
  },
  source: {
    title: "Result source",
    description:
      "The actual origin of the displayed schedule. A heuristic fallback is labelled even when optimization was requested.",
    formula:
      "heuristic = FCFS/EDD; cbc_incumbent = CBC feasible solution; heuristic_fallback = retained baseline",
    example:
      "cbc_incumbent with time_limit means CBC found a feasible schedule but did not finish proving optimality.",
  },
  gap: {
    title: "Optimality gap",
    description:
      "Distance between the retained objective and a supported solver lower bound. Unknown bounds or gaps are shown as N/A. A weak bound can produce a large gap even when the schedule is useful.",
    formula: "(objective − lower bound) / max(|objective|, 1)",
    example:
      "Objective 100 and bound 80 give a 20% relative gap. The optimality flag is determined separately.",
  },
} as const;
export type MetricTopic = keyof typeof metricTopics;

export function MetricLabel({
  topic,
  children,
  onHelp,
}: {
  topic: MetricTopic;
  children: React.ReactNode;
  onHelp: (topic: MetricTopic) => void;
}) {
  return (
    <span className="metric-label">
      {children}
      <button
        type="button"
        className="metric-help-button"
        aria-label={`Explain ${metricTopics[topic].title}`}
        onClick={() => onHelp(topic)}
      >
        <CircleHelp size={14} />
      </button>
    </span>
  );
}

export default function MetricHelp({
  topic,
  run,
  dataset,
  onClose,
}: {
  topic: MetricTopic;
  run?: Run;
  dataset?: Dataset;
  onClose: () => void;
}) {
  const content = metricTopics[topic];
  const current = run?.metrics;
  return (
    <DialogFrame onClose={onClose} labelledBy="metric-help-title">
      <div className="modal-title">
        <div>
          <span className="eyebrow">METRIC GUIDE</span>
          <h2 id="metric-help-title">{content.title}</h2>
        </div>
        <button className="icon-button" aria-label="Close metric help" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <p className="dialog-intro">{content.description}</p>
      <div className="formula-box">{content.formula}</div>
      <div className="help-example">
        <strong>Example</strong>
        <p>{content.example}</p>
      </div>
      {current && (
        <div className="help-context">
          <strong>Current displayed run</strong>
          <p>
            {run.method.toUpperCase()} · {current.machine_count} machines · {run.id.slice(0, 8)}
          </p>
          <p>
            {fmt(current.total_jobs)} jobs · {fmt(current.late_jobs)} late ·{" "}
            {fmt(current.total_weighted_tardiness)} weighted min
          </p>
          <p>
            Planning window H: {fmt(current.horizon_min)} min · Makespan:{" "}
            {fmt(current.makespan_min)} min
          </p>
          <p>
            Window: {percent(current.window_utilization)} · Span:{" "}
            {percent(current.span_utilization)}
          </p>
          <p>
            Solver: {run.solver_status.replaceAll("_", " ")} · Source:{" "}
            {run.result_source?.replaceAll("_", " ")}
          </p>
        </div>
      )}
      {!current && (
        <p className="export-hint">
          No calculated run selected.{" "}
          {dataset
            ? `This workload has ${dataset.jobs.length} jobs.`
            : "Load a workload to view its calculated metrics."}
        </p>
      )}
      <p className="export-hint">
        Calculated lateness describes this schedule, not a predictive probability. Improving the
        objective can leave other KPIs unchanged or worse.
      </p>
    </DialogFrame>
  );
}
