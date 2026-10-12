import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { api, fmt, latestMethods, type Dataset, type Run, type Scenario } from "../api/client";
import RunExplanation from "./RunExplanation";

export default function ScenarioWorkbench({
  dataset,
  onSelect,
}: {
  dataset: Dataset;
  onSelect: (s: Scenario) => void;
}) {
  const [explainId, setExplainId] = useState("");
  const queries = useQueries({
    queries: dataset.scenarios.map((s) => ({
      queryKey: ["runs", s.id],
      queryFn: () => api<Run[]>(`/scenarios/${s.id}/runs`),
      refetchInterval: 2000,
    })),
  });
  const choices = dataset.scenarios.flatMap((s, i) =>
    (queries[i].data ?? []).map((run) => ({
      run,
      label: `${s.name} · ${run.method.toUpperCase()}`,
    })),
  );
  const explain = choices.find((c) => c.run.id === explainId)?.run;
  return (
    <>
      <section className="panel scenario-workbench">
        <div className="panel-heading">
          <div>
            <h2>What-if scenario results</h2>
            <p>
              Same jobs and horizon. Capacity and hard deadlines are labelled for each scenario.
            </p>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Machines / hard deadlines</th>
                <th>Method</th>
                <th>Status / source</th>
                <th>Weighted tardiness</th>
                <th>Late jobs</th>
                <th>Makespan</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {dataset.scenarios.flatMap((s, i) =>
                latestMethods(queries[i].data ?? []).map((r) => (
                  <tr key={r.id}>
                    <td>
                      <button className="text-button" onClick={() => onSelect(s)}>
                        {s.name}
                      </button>
                    </td>
                    <td>
                      {s.machine_count} / {(s.must_finish_job_ids ?? []).length}
                    </td>
                    <td>{r.method.toUpperCase()}</td>
                    <td>
                      <span>
                        {["queued", "running"].includes(r.execution_state)
                          ? r.execution_state
                          : r.has_valid_schedule
                            ? r.proven_optimal
                              ? "Proven optimal"
                              : `Validated · ${r.solver_status}`
                            : r.solver_status === "infeasible"
                              ? "Infeasible"
                              : r.execution_state === "failed"
                                ? "Invalid / failed"
                                : "No feasible result found"}
                      </span>
                      <br />
                      <small>{r.result_source ?? "No schedule"}</small>
                    </td>
                    <td>{fmt(r.metrics?.total_weighted_tardiness)}</td>
                    <td>{fmt(r.metrics?.late_jobs)}</td>
                    <td>{fmt(r.metrics?.makespan_min)}</td>
                    <td>
                      <button
                        className="button secondary"
                        disabled={["queued", "running"].includes(r.execution_state)}
                        onClick={() => setExplainId(r.id)}
                      >
                        Explain {r.method.toUpperCase()}
                      </button>
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      </section>
      {explain && <RunExplanation key={explain.id} run={explain} choices={choices} />}
    </>
  );
}
