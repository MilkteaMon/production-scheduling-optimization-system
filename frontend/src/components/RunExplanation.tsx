import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, fmt, type Explanation, type Run } from "../api/client";

export default function RunExplanation({
  run,
  choices = [],
}: {
  run: Run;
  choices?: { run: Run; label: string }[];
}) {
  const [baseline, setBaseline] = useState("");
  const explanation = useQuery({
    queryKey: ["explanation", run.id, baseline],
    queryFn: () =>
      api<Explanation>(
        `/runs/${run.id}/explanation${baseline ? `?baseline_run_id=${encodeURIComponent(baseline)}` : ""}`,
      ),
    enabled: !["queued", "running"].includes(run.execution_state),
  });
  return (
    <section className="panel run-explanation">
      <div className="panel-heading">
        <div>
          <h2>Explain this result</h2>
          <p>
            Calculated evidence · run {run.id.slice(0, 8)} · {run.method.toUpperCase()}
          </p>
        </div>
      </div>
      {run.has_valid_schedule && (
        <label>
          Compare with a specific run
          <select
            aria-label="Explanation baseline"
            value={baseline}
            onChange={(e) => setBaseline(e.target.value)}
          >
            <option value="">No comparison</option>
            {choices
              .filter((c) => c.run.has_valid_schedule && c.run.id !== run.id)
              .map((c) => (
                <option key={c.run.id} value={c.run.id}>
                  {c.label} · {c.run.id.slice(0, 8)}
                </option>
              ))}
          </select>
        </label>
      )}
      {explanation.isPending && <p>Loading evidence…</p>}
      {explanation.error && <p role="alert">{String(explanation.error)}</p>}
      {explanation.data && (
        <>
          <p className="muted">
            {explanation.data.machine_count} machines ·{" "}
            {explanation.data.must_finish_job_ids.length} hard deadlines ·{" "}
            {explanation.data.result_source ?? "no validated result"}
          </p>
          {explanation.data.summary.map((s, i) => (
            <p key={i}>{s}</p>
          ))}
          {!!explanation.data.job_changes.length && (
            <div className="table-scroll">
              <table>
                <caption>Order-level contributions — positive reductions mean improvement</caption>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Weight</th>
                    <th>Due</th>
                    <th>Before completion</th>
                    <th>After completion</th>
                    <th>Before late</th>
                    <th>After late</th>
                    <th>Weighted reduction</th>
                  </tr>
                </thead>
                <tbody>
                  {explanation.data.job_changes.map((j) => (
                    <tr key={j.job_id}>
                      <td>
                        {j.job_id}
                        {j.must_finish_on_time ? " · hard" : ""}
                      </td>
                      <td>{j.priority_weight}</td>
                      <td>{j.due_time_min}</td>
                      <td>{fmt(j.baseline_completion_min)}</td>
                      <td>{fmt(j.completion_min)}</td>
                      <td>{fmt(j.baseline_tardiness_min)}</td>
                      <td>{fmt(j.tardiness_min)}</td>
                      <td>{fmt(j.weighted_tardiness_reduction)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
