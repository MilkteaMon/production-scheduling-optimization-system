import Plotly from "plotly.js-basic-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import type { Dataset, Job, Run, Scenario } from "../api/client";
// The wrapper is CommonJS; support the namespace returned by modern ESM bundlers.
const factory =
  typeof createPlotlyComponent === "function"
    ? createPlotlyComponent
    : (createPlotlyComponent as unknown as { default: typeof createPlotlyComponent }).default;
const Plot = factory(Plotly);

export default function ScheduleChart({
  run,
  dataset,
  scenario,
  onJob,
}: {
  run: Run;
  dataset: Dataset;
  scenario: Scenario;
  onJob: (j: Job) => void;
}) {
  const jobs = new Map(dataset.jobs.map((j) => [j.job_id, j]));
  const traces = run.placements.map((p) => {
    const j = jobs.get(p.job_id)!;
    const late = p.completion_min > j.due_time_min;
    return {
      type: "bar" as const,
      orientation: "h" as const,
      x: [j.processing_time_min],
      y: [p.machine_code],
      base: [p.start_min],
      width: 0.58,
      name: p.job_id,
      marker: {
        color: late ? "#ad592b" : "#2e8069",
        line: { color: late ? "#c77443" : "#369980", width: 1 },
      },
      text: [p.job_id.replace("JOB-", "J")],
      textposition: "inside" as const,
      textangle: 0,
      textfont: { color: "#fff", size: 11 },
      customdata: [j.job_id],
      hovertemplate: `<b>${j.job_id}</b><br>${p.machine_code} · ${p.start_min}–${p.completion_min} min<br>Due: ${j.due_time_min} min<br>Weight: ${j.priority_weight}<br>Tardiness: ${Math.max(0, p.completion_min - j.due_time_min)} min<extra></extra>`,
    };
  });
  return (
    <div className="gantt" data-testid="gantt">
      <Plot
        data={traces}
        layout={{
          height: Math.max(260, scenario.machine_count * 58 + 95),
          margin: { l: 48, r: 18, t: 12, b: 48 },
          barmode: "overlay",
          showlegend: false,
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { family: "Inter, Arial, sans-serif", color: "#53685c", size: 11 },
          xaxis: {
            title: { text: "Minutes from planning time zero", font: { size: 11 } },
            gridcolor: "#edf1ee",
            zeroline: false,
            range: [0, Math.ceil((run.metrics?.makespan_min ?? 1) * 1.04)],
          },
          yaxis: {
            categoryorder: "array",
            categoryarray: scenario.machines.map((m) => m.machine_code).reverse(),
            showgrid: false,
            zeroline: false,
            fixedrange: true,
          },
          hovermode: "closest",
          dragmode: "pan",
        }}
        config={{ displayModeBar: false, responsive: true, scrollZoom: true }}
        style={{ width: "100%" }}
        useResizeHandler
        onClick={(event) => {
          const id = event.points[0]?.customdata;
          const job = jobs.get(String(id));
          if (job) onJob(job);
        }}
      />
    </div>
  );
}
