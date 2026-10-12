import DialogFrame from "./components/DialogFrame";
import { lazy, Suspense, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  CircleHelp,
  ChevronDown,
  ChevronRight,
  Clock3,
  Database,
  Factory,
  FlaskConical,
  GanttChart,
  Layers3,
  LoaderCircle,
  Plus,
  Send,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  active,
  api,
  fmt,
  labels,
  latestMethods,
  percent,
  post,
  type CopilotResponse,
  type Dataset,
  type Health,
  type Job,
  type Method,
  type Run,
  type Scenario,
  type RulesPreview,
  type RulesApplied,
} from "./api/client";
import DataDialog from "./components/DataDialog";
import WorkloadDescriptionDialog from "./components/WorkloadDescriptionDialog";
import DatasetManager from "./components/DatasetManager";
import ExportDialog from "./components/ExportDialog";
import MetricHelp, { MetricLabel, type MetricTopic } from "./components/MetricHelp";
import ComparisonExplanation from "./components/ComparisonExplanation";
import RulesDialog from "./components/RulesDialog";
import RunExplanation from "./components/RunExplanation";
import ScenarioWorkbench from "./components/ScenarioWorkbench";
import { datasetDescription, visibleDatasets } from "./data/datasets";
import { PRODUCT_NAME } from "./data/branding";
import { useStoredState } from "./hooks/useStoredState";
const ScheduleChart = lazy(() => import("./components/ScheduleChart"));

type Page = "Overview" | "Production schedule" | "Comparison" | "Scenarios" | "Data explorer";
const navigation = [
  { name: "Overview" as Page, icon: Layers3 },
  { name: "Production schedule" as Page, icon: GanttChart },
  { name: "Comparison" as Page, icon: BarChart3 },
  { name: "Scenarios" as Page, icon: Factory },
  { name: "Data explorer" as Page, icon: Database },
];

function Status({ run }: { run?: Run }) {
  if (!run) return <span className="badge neutral">Not run</span>;
  if (active(run))
    return (
      <span className="badge amber">
        <LoaderCircle size={12} className="spin" />
        {run.execution_state === "queued" ? "Queued" : "Solving"}
      </span>
    );
  if (run.execution_state === "failed" || run.execution_state === "interrupted")
    return <span className="badge amber">{run.execution_state}</span>;
  if (!run.has_valid_schedule)
    return (
      <span className="badge amber">
        {run.solver_status === "infeasible" ? "Infeasible" : "No feasible result found"}
      </span>
    );
  if (run.proven_optimal)
    return (
      <span className="badge green">
        <CheckCircle2 size={12} />
        Proven optimal
      </span>
    );
  return (
    <span className={`badge ${run.method === "milp" ? "amber" : "neutral"}`}>
      {run.method === "milp"
        ? run.result_source === "heuristic_fallback"
          ? "Heuristic fallback"
          : run.solver_status === "time_limit"
            ? "Feasible · time limited"
            : run.solver_status === "gap_limit"
              ? "Feasible · gap limit"
              : "Validated feasible"
        : "Validated baseline"}
    </span>
  );
}

export default function App() {
  const client = useQueryClient();
  const [page, setPage] = useState<Page>("Overview"),
    [datasetId, setDatasetId] = useStoredState<string | null>("dataset", null),
    [scenarioId, setScenarioId] = useStoredState<string | null>("scenario", null),
    [method, setMethod] = useStoredState<Method>("method", "edd");
  const [showTests, setShowTests] = useStoredState<boolean>("show-tests", false);
  const [managerOpen, setManagerOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [helpTopic, setHelpTopic] = useState<MetricTopic | null>(null);
  const [dataOpen, setDataOpen] = useState(false),
    [copilotOpen, setCopilotOpen] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [job, setJob] = useState<Job | null>(null);
  const [descriptionOpen, setDescriptionOpen] = useState(false);
  const [question, setQuestion] = useState(""),
    [answers, setAnswers] = useState<{ question: string; response: CopilotResponse }[]>([]),
    [thinking, setThinking] = useState(false);
  const [solverBudget, setSolverBudget] = useState(60);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [rulesProposal, setRulesProposal] = useState<RulesPreview | null>(null);
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<Health>("/health") });
  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Dataset[]>("/datasets"),
    refetchInterval: 5000,
  });
  const availableDatasets = visibleDatasets(datasets.data ?? [], showTests);
  const dataset = availableDatasets.find((d) => d.id === datasetId) ?? availableDatasets[0];
  function selectDataset(d: Dataset) {
    if (d.is_test) setShowTests(true);
    setDatasetId(d.id);
    setScenarioId(null);
    setMethod("edd");
    setAnswers([]);
  }
  function changeTestVisibility(show: boolean) {
    setShowTests(show);
    if (!show && dataset?.is_test) {
      setDatasetId(visibleDatasets(datasets.data ?? [], false)[0]?.id ?? null);
      setScenarioId(null);
      setMethod("edd");
      setAnswers([]);
    }
  }
  const scenario =
    dataset?.scenarios.find((s) => s.id === scenarioId) ??
    dataset?.scenarios.find((s) => s.kind === "baseline");
  const runs = useQuery({
    queryKey: ["runs", scenario?.id],
    queryFn: () => api<Run[]>(`/scenarios/${scenario!.id}/runs`),
    enabled: !!scenario,
    refetchInterval: 2000,
  });
  const methods = latestMethods(runs.data ?? []);
  const selected = methods.find((r) => r.method === method);
  const run = selected?.has_valid_schedule
    ? selected
    : (methods.find((r) => r.method === "edd" && r.has_valid_schedule) ??
      methods.find((r) => r.has_valid_schedule));
  const ready = methods.filter((r) => r.has_valid_schedule);
  const comparison = useQuery({
    queryKey: ["comparison", ready.map((r) => r.id).join(",")],
    queryFn: () =>
      post<{
        runs: (Run & {
          changes: Record<
            string,
            { absolute_reduction: number; percentage_reduction: number | null }
          >;
        })[];
      }>("/comparisons", { run_ids: ready.map((r) => r.id) }),
    enabled: ready.length >= 2,
  });
  const utilization = useQuery({
    queryKey: ["utilization", run?.id],
    queryFn: () =>
      api<{
        rows: {
          machine_code: string;
          busy_time_min: number;
          span_utilization: number;
          window_utilization: number;
          job_count: number;
        }[];
      }>(`/runs/${run!.id}/machine-utilization`),
    enabled: !!run,
  });
  const late = useQuery({
    queryKey: ["late", run?.id],
    queryFn: () =>
      api<{
        rows: {
          job_id: string;
          machine_code: string;
          tardiness_min: number;
          weighted_tardiness: number;
          due_time_min: number;
        }[];
      }>(`/runs/${run!.id}/late-jobs`),
    enabled: !!run,
  });
  const extra = dataset?.scenarios.find((s) => s.kind === "additional_machine");
  const extraRuns = useQuery({
    queryKey: ["runs", extra?.id],
    queryFn: () => api<Run[]>(`/scenarios/${extra!.id}/runs`),
    enabled: !!extra,
    refetchInterval: 2000,
  });
  const baseline = dataset?.scenarios.find((s) => s.kind === "baseline");
  const baseRuns = useQuery({
    queryKey: ["runs", baseline?.id],
    queryFn: () => api<Run[]>(`/scenarios/${baseline!.id}/runs`),
    enabled: !!baseline,
    refetchInterval: 2000,
  });
  const baseBest = latestMethods(baseRuns.data ?? [])
    .filter((r) => r.has_valid_schedule)
    .sort((a, b) => a.metrics!.total_weighted_tardiness - b.metrics!.total_weighted_tardiness)[0];
  const extraBest = latestMethods(extraRuns.data ?? [])
    .filter((r) => r.has_valid_schedule)
    .sort((a, b) => a.metrics!.total_weighted_tardiness - b.metrics!.total_weighted_tardiness)[0];
  const scenarioComparison = useQuery({
    queryKey: ["scenario-compare", baseBest?.id, extraBest?.id],
    queryFn: () =>
      post<{
        runs: (Run & {
          changes: Record<
            string,
            { absolute_reduction: number; percentage_reduction: number | null }
          >;
        })[];
      }>("/comparisons", { run_ids: [baseBest!.id, extraBest!.id] }),
    enabled: !!baseBest && !!extraBest,
  });

  async function optimize() {
    if (!scenario) return;
    setBusy(true);
    setError("");
    try {
      await post(`/scenarios/${scenario.id}/runs`, {
        methods: ["milp"],
        time_limit_seconds: solverBudget,
      });
      setMethod("milp");
      await client.invalidateQueries({ queryKey: ["runs"] });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function simulate() {
    if (!dataset) return;
    setBusy(true);
    setError("");
    try {
      if (scenario?.must_finish_job_ids?.length) {
        const proposal = await post<RulesPreview>(`/scenarios/${scenario.id}/rules/preview`, {
          job_ids: [],
          add_machine: true,
        });
        setRulesProposal(proposal);
        setRulesOpen(true);
        return;
      }
      const s = await post<Scenario>(`/datasets/${dataset.id}/scenarios`, {});
      await post(`/scenarios/${s.id}/runs`, {
        methods: ["fcfs", "edd", "milp"],
        time_limit_seconds: solverBudget,
      });
      await client.invalidateQueries({ queryKey: ["datasets"] });
      await client.invalidateQueries({ queryKey: ["runs"] });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function ask(text = question) {
    if (!scenario || !text.trim()) return;
    setThinking(true);
    setError("");
    try {
      const response = await post<CopilotResponse>("/copilot/query", {
        scenario_id: scenario.id,
        run_id: run?.id ?? null,
        question: text,
      });
      setAnswers((a) => [...a, { question: text, response }]);
      setQuestion("");
      await client.invalidateQueries({ queryKey: ["runs"] });
      await client.invalidateQueries({ queryKey: ["datasets"] });
    } catch (e) {
      setError(String(e));
    } finally {
      setThinking(false);
    }
  }
  const metrics = run?.metrics;
  async function rulesCreated(result: RulesApplied) {
    await client.invalidateQueries({ queryKey: ["datasets"] });
    await client.invalidateQueries({ queryKey: ["runs"] });
    setScenarioId(result.scenario.id);
    setMethod("milp");
    setRulesOpen(false);
    setRulesProposal(null);
    setPage("Scenarios");
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label={`${PRODUCT_NAME} home`}>
          <span className="brand-icon">
            <BarChart3 size={22} />
          </span>
          <span className="brand-copy">
            <strong>Production Scheduling</strong>
            <span>Optimization System</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-avatar">
            <Factory size={18} />
          </span>
          <div>
            <strong>Production workspace</strong>
            <span>Local demonstration</span>
          </div>
          <ChevronDown size={15} />
        </div>
        <span className="nav-caption">WORKSPACE</span>
        <nav aria-label="Main navigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={`nav-item ${page === name ? "current" : ""}`}
              onClick={() => setPage(name)}
            >
              <Icon size={19} />
              {name}
              {page === name && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-divider" />
        <span className="nav-caption">INTELLIGENCE</span>
        <button className="nav-item" onClick={() => setCopilotOpen(true)}>
          <Sparkles size={19} />
          AI copilot<span className="tiny-pill">BETA</span>
        </button>
        <div className="sidebar-bottom">
          <div className="method-note">
            <span className="mini-icon">
              <CheckCircle2 size={17} />
            </span>
            <strong>Decisions backed by data</strong>
            <p>Every schedule is independently checked against the model.</p>
            <button onClick={() => setPage("Comparison")}>
              Explore the methods <ArrowRight size={13} />
            </button>
          </div>
          <div className="local-mode">
            <span className="status-dot" />
            <span>Local mode</span>
            <span className="version">v0.1.0</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>Production planning</strong>
          </div>
          <div className="topbar-right">
            <button
              className="icon-button mobile-copilot"
              aria-label="AI copilot"
              onClick={() => setCopilotOpen(true)}
            >
              <Sparkles size={19} />
            </button>
            <span className="badge neutral">
              <FlaskConical size={13} />
              Synthetic demo available
            </span>
            <span className="avatar" aria-hidden="true">
              PS
            </span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">OPERATIONS INTELLIGENCE</div>
              <h1>{page === "Overview" ? "Production overview" : page}</h1>
              <p className="page-subtitle">
                {page === "Overview"
                  ? "Web scheduling dashboard · Power BI data exports · Optional AI copilot extension"
                  : page === "Production schedule"
                    ? "Inspect assignments, timing, and the orders that need attention."
                    : page === "Comparison"
                      ? "Compare calculated results from the same workload and constraints."
                      : page === "Scenarios"
                        ? "Explore capacity changes while preserving your original plan."
                        : "Inspect the inputs behind every scheduling decision."}
              </p>
            </div>
            <div className="heading-actions">
              <label className="solver-budget">
                <span className="sr-only">Solver time limit</span>
                <select
                  aria-label="Solver time limit"
                  value={solverBudget}
                  onChange={(e) => setSolverBudget(Number(e.target.value))}
                >
                  {[15, 30, 60, 120].map((seconds) => (
                    <option key={seconds} value={seconds}>
                      {seconds}s limit
                    </option>
                  ))}
                </select>
              </label>
              <button className="button secondary" onClick={() => setDataOpen(true)}>
                <Plus size={16} />
                Load data
              </button>
              <button className="button secondary" onClick={() => setDescriptionOpen(true)}>
                <Sparkles size={16} /> Describe workload
              </button>
              <button className="button secondary" onClick={() => setManagerOpen(true)}>
                <Database size={16} /> Manage datasets
              </button>
              <button
                className="button secondary"
                disabled={!run}
                onClick={() => setExportOpen(true)}
              >
                <ArrowDownToLine size={16} /> Export
              </button>
              <button
                className="button primary"
                disabled={
                  !scenario || busy || methods.some((r) => r.method === "milp" && active(r))
                }
                onClick={optimize}
              >
                {busy ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}
                Optimize schedule
              </button>
              <button
                className="button secondary"
                disabled={!dataset || !scenario}
                onClick={() => {
                  setRulesProposal(null);
                  setRulesOpen(true);
                }}
              >
                Plan commitments / What-if
              </button>
            </div>
          </div>
          {(error || datasets.error || runs.error) && (
            <div className="error-banner" role="alert">
              <TriangleAlert size={17} />
              {error || String(datasets.error || runs.error)}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {scenario && !!scenario.must_finish_job_ids?.length && (
            <div className="notice">
              Hard deadlines: {scenario.must_finish_job_ids.join(", ")}. Other due times remain soft
              targets.
            </div>
          )}
          {selected && !active(selected) && !selected.has_valid_schedule && (
            <div className="notice" role="status">
              <strong>
                {labels[selected.method]}:{" "}
                {selected.solver_status === "infeasible"
                  ? "No feasible schedule under these commitments"
                  : "No validated result"}
              </strong>
              <p>{selected.validation_errors.concat(selected.diagnostics).join(" · ")}</p>
            </div>
          )}
          {!dataset ? (
            <section className="empty-workspace">
              <div className="empty-illustration">
                <Factory size={48} />
                <span>
                  <Activity size={24} />
                </span>
              </div>
              <span className="eyebrow">YOUR FIRST PRODUCTION PLAN</span>
              <h2>Bring your workload into focus.</h2>
              <p>
                Generate a reproducible manufacturing dataset or upload a CSV. Compare two
                baselines, solve the scheduling model, and explore another machine.
              </p>
              <button className="button primary" onClick={() => setDataOpen(true)}>
                <FlaskConical size={17} />
                Create a demonstration dataset
              </button>
              <div className="empty-features">
                <span>
                  <CheckCircle2 size={15} />
                  No API key required
                </span>
                <span>
                  <GanttChart size={15} />
                  Interactive schedules
                </span>
                <span>
                  <BarChart3 size={15} />
                  Verified calculations
                </span>
              </div>
            </section>
          ) : (
            <>
              <div className="context-bar">
                <div className="dataset-select">
                  <Database size={17} />
                  <label className="sr-only" htmlFor="dataset-select">
                    Active dataset
                  </label>
                  <select
                    id="dataset-select"
                    value={dataset.id}
                    onChange={(e) =>
                      selectDataset(availableDatasets.find((d) => d.id === e.target.value)!)
                    }
                  >
                    {availableDatasets.map((d) => (
                      <option key={d.id} value={d.id}>
                        {datasetDescription(d)}
                      </option>
                    ))}
                  </select>
                  <span className="badge neutral">
                    {dataset.source_kind === "synthetic" ? "Synthetic" : "CSV import"}
                  </span>
                </div>
                <div className="context-meta">
                  <span>{dataset.jobs.length} jobs</span>
                  <span>·</span>
                  <span>{scenario?.machine_count} machines</span>
                  <span>·</span>
                  <span>Minutes · T₀</span>
                  <label className="sr-only" htmlFor="scenario-select">
                    Active scenario
                  </label>
                  <select
                    id="scenario-select"
                    value={scenario?.id}
                    onChange={(e) => {
                      setScenarioId(e.target.value);
                      setAnswers([]);
                    }}
                  >
                    {dataset.scenarios.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="context-controls">
                <label>
                  <input
                    type="checkbox"
                    checked={showTests}
                    onChange={(e) => changeTestVisibility(e.target.checked)}
                  />
                  Show test data
                </label>
                <span>
                  {availableDatasets.length} available workloads · archived datasets are in Manage
                  datasets
                </span>
              </div>
              {(page === "Overview" || page === "Production schedule") && (
                <>
                  <div className="kpi-grid">
                    <KPICard
                      label="Total production jobs"
                      onHelp={() => setHelpTopic("total_jobs")}
                      value={fmt(metrics?.total_jobs ?? dataset.jobs.length)}
                      icon={<Layers3 size={18} />}
                      detail={`${scenario?.machine_count ?? 0} identical parallel machines`}
                    />
                    <KPICard
                      label="Late jobs"
                      onHelp={() => setHelpTopic("late_jobs")}
                      value={fmt(metrics?.late_jobs)}
                      icon={<Clock3 size={18} />}
                      detail={
                        metrics
                          ? `${fmt(metrics.total_jobs - metrics.late_jobs)} jobs finish on time`
                          : "Waiting for baseline results"
                      }
                      accent="amber"
                    />
                    <KPICard
                      label="Weighted tardiness"
                      onHelp={() => setHelpTopic("total_weighted_tardiness")}
                      value={fmt(metrics?.total_weighted_tardiness)}
                      unit="weighted min"
                      icon={<Activity size={18} />}
                      detail="Primary optimization objective"
                    />
                    <KPICard
                      label="Window utilization"
                      onHelp={() => setHelpTopic("window_utilization")}
                      value={metrics ? percent(metrics.window_utilization) : "—"}
                      icon={<BarChart3 size={18} />}
                      detail={`Fixed planning window · ${fmt(dataset.horizon_min)} min`}
                    />
                  </div>
                  <div className="dashboard-grid">
                    <section className="panel schedule-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Production schedule</h2>
                          <p>One operation per job. Every assignment verified.</p>
                        </div>
                        <button
                          className="icon-button"
                          aria-label="Export schedule CSV"
                          disabled={!run}
                          onClick={() => {
                            if (run)
                              window.location.href = `/api/v1/runs/${run.id}/exports/schedule.csv`;
                          }}
                        >
                          <ArrowDownToLine size={18} />
                        </button>
                      </div>
                      <div className="schedule-toolbar">
                        <div className="method-tabs">
                          {(["fcfs", "edd", "milp"] as Method[]).map((m) => (
                            <button
                              key={m}
                              className={method === m ? "selected" : ""}
                              onClick={() => setMethod(m)}
                            >
                              {labels[m]}
                              {m === "milp" && <Sparkles size={12} />}
                            </button>
                          ))}
                        </div>
                        <Status run={selected} />
                      </div>
                      {selected && active(selected) && (
                        <div className="inline-notice">
                          <LoaderCircle size={14} className="spin" />{" "}
                          {selected.execution_state === "queued"
                            ? "Queued for execution."
                            : "CBC is searching for a better schedule."}{" "}
                          Displaying the latest validated {run ? labels[run.method] : "baseline"}{" "}
                          result.
                        </div>
                      )}
                      {!selected && method === "milp" && (
                        <div className="inline-notice">
                          Select Optimize schedule to run CBC. The chart currently shows{" "}
                          {run ? labels[run.method] : "a pending baseline"}.
                        </div>
                      )}
                      {run && scenario ? (
                        <Suspense
                          fallback={<div className="chart-loading">Loading schedule chart…</div>}
                        >
                          <ScheduleChart
                            run={run}
                            dataset={dataset}
                            scenario={scenario}
                            onJob={setJob}
                          />
                        </Suspense>
                      ) : (
                        <div className="chart-loading">
                          <LoaderCircle className="spin" size={24} />
                          <span>Calculating baseline schedules…</span>
                        </div>
                      )}
                      <div className="chart-footer">
                        <div className="legend">
                          <span>
                            <i className="legend-dot green" />
                            On time
                          </span>
                          <span>
                            <i className="legend-dot amber" />
                            Late
                          </span>
                        </div>
                        <span>
                          Makespan <strong>{fmt(metrics?.makespan_min)} min</strong>
                        </span>
                        <span>Scroll to zoom · select a job</span>
                      </div>
                    </section>
                    <section className="panel utilization-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Machine utilization</h2>
                          <p>Busy time / schedule span</p>
                        </div>
                        <span className="badge neutral">{run ? labels[run.method] : "—"}</span>
                      </div>
                      <div className="utilization-list">
                        {utilization.data?.rows.map((m) => (
                          <div className="machine-row" key={m.machine_code}>
                            <div>
                              <span className="machine-name">
                                <Factory size={15} />
                                {m.machine_code}
                              </span>
                              <strong>{percent(m.span_utilization)}</strong>
                            </div>
                            <div className="progress-track">
                              <span style={{ width: `${m.span_utilization * 100}%` }} />
                            </div>
                            <small>
                              {fmt(m.busy_time_min)} busy min <span>{m.job_count} jobs</span>
                            </small>
                          </div>
                        ))}
                      </div>
                      <div className="panel-note">
                        <MetricLabel topic="span_utilization" onHelp={setHelpTopic}>
                          Span utilization
                        </MetricLabel>{" "}
                        <strong>{metrics ? percent(metrics.span_utilization) : "—"}</strong>
                        <p>
                          Fixed-window utilization is unchanged by reordering the same workload.
                        </p>
                      </div>
                    </section>
                    <section className="panel comparison-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Scheduling performance</h2>
                          <p>Total weighted tardiness · lower is better</p>
                        </div>
                        <button className="text-button" onClick={() => setPage("Comparison")}>
                          View comparison <ArrowRight size={14} />
                        </button>
                      </div>
                      <div className="comparison-bars">
                        {(["fcfs", "edd", "milp"] as Method[]).map((m) => {
                          const r = methods.find((r) => r.method === m);
                          const max = Math.max(
                            1,
                            ...ready.map((r) => r.metrics!.total_weighted_tardiness),
                          );
                          return (
                            <div className="comparison-bar-row" key={m}>
                              <span>{labels[m]}</span>
                              <div className="comparison-bar-track">
                                {r?.metrics && (
                                  <div
                                    className={
                                      m === "milp" ? "optimized" : m === "edd" ? "edd" : ""
                                    }
                                    style={{
                                      width: `${Math.max(2, (r.metrics.total_weighted_tardiness / max) * 100)}%`,
                                    }}
                                  />
                                )}
                              </div>
                              <strong>{fmt(r?.metrics?.total_weighted_tardiness)}</strong>
                            </div>
                          );
                        })}
                      </div>
                      <div className="comparison-footnote">
                        <CheckCircle2 size={14} />
                        {methods.find((r) => r.method === "milp") ? (
                          <>
                            <Status run={methods.find((r) => r.method === "milp")} /> Results from
                            actual execution.
                          </>
                        ) : (
                          "Run optimization to complete the comparison."
                        )}
                      </div>
                    </section>
                    <section className="panel late-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Orders needing attention</h2>
                          <p>Late under the displayed schedule</p>
                        </div>
                        <span className="count-badge">{fmt(metrics?.late_jobs ?? 0)}</span>
                      </div>
                      <div className="late-list">
                        {late.data?.rows.slice(0, 4).map((j) => (
                          <button
                            key={j.job_id}
                            onClick={() => setJob(dataset.jobs.find((x) => x.job_id === j.job_id)!)}
                          >
                            <span className="job-alert">
                              <Clock3 size={15} />
                            </span>
                            <span>
                              <strong>{j.job_id}</strong>
                              <small>
                                {j.machine_code} · weight-adjusted {fmt(j.weighted_tardiness)} min
                              </small>
                            </span>
                            <span className="late-amount">+{fmt(j.tardiness_min)} min</span>
                          </button>
                        ))}
                        {late.data && late.data.rows.length === 0 && (
                          <p className="no-late">
                            <CheckCircle2 size={18} />
                            All jobs finish on time.
                          </p>
                        )}
                      </div>
                    </section>
                  </div>
                  <div className="run-detail">
                    <span>
                      <CheckCircle2 size={14} /> Independently validated
                    </span>
                    <span>
                      Displayed method: <strong>{run ? labels[run.method] : "Pending"}</strong>
                    </span>
                    <span>
                      <MetricLabel topic="source" onHelp={setHelpTopic}>
                        Source
                      </MetricLabel>
                      : <strong>{run?.result_source?.replaceAll("_", " ") ?? "—"}</strong>
                    </span>
                    <span>
                      <MetricLabel topic="status" onHelp={setHelpTopic}>
                        Solver
                      </MetricLabel>
                      : <strong>{run?.solver_status.replaceAll("_", " ") ?? "—"}</strong>
                    </span>
                    {run?.method === "milp" && (
                      <>
                        <span>
                          Runtime: <strong>{fmt(run.solver_runtime_seconds, 2)} s</strong>
                        </span>
                        <span>
                          <MetricLabel topic="gap" onHelp={setHelpTopic}>
                            Gap
                          </MetricLabel>
                          : <strong>{percent(run.relative_gap)}</strong>
                        </span>
                      </>
                    )}
                  </div>
                  {page === "Production schedule" && run && (
                    <ScheduleTable run={run} dataset={dataset} />
                  )}
                </>
              )}
              {page === "Comparison" && (
                <>
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h2>One workload. Three scheduling methods.</h2>
                        <p>Identical jobs, release constraints, machines, and planning horizon.</p>
                      </div>
                    </div>
                    <div className="comparison-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Metric</th>
                            {(["fcfs", "edd", "milp"] as Method[]).map((m) => (
                              <th key={m}>{labels[m]}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            ["late_jobs", "Late jobs"],
                            ["total_weighted_tardiness", "Weighted tardiness (weighted min)"],
                            ["makespan_min", "Makespan (min)"],
                            ["window_utilization", "Fixed-window utilization"],
                            ["span_utilization", "Schedule-span utilization"],
                          ].map(([key, label]) => (
                            <tr key={key}>
                              <th>
                                <MetricLabel topic={key as MetricTopic} onHelp={setHelpTopic}>
                                  {label}
                                </MetricLabel>
                              </th>
                              {(["fcfs", "edd", "milp"] as Method[]).map((m) => {
                                const r = methods.find((r) => r.method === m);
                                const value =
                                  r?.metrics?.[key as keyof NonNullable<Run["metrics"]>];
                                return (
                                  <td key={m}>
                                    {key.includes("utilization") ? percent(value) : fmt(value)}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                          <tr>
                            <th>
                              <MetricLabel topic="status" onHelp={setHelpTopic}>
                                Result status
                              </MetricLabel>
                            </th>
                            {(["fcfs", "edd", "milp"] as Method[]).map((m) => (
                              <td key={m}>
                                <Status run={methods.find((r) => r.method === m)} />
                              </td>
                            ))}
                          </tr>
                          <tr>
                            <th>
                              <MetricLabel topic="source" onHelp={setHelpTopic}>
                                Result source
                              </MetricLabel>
                            </th>
                            {(["fcfs", "edd", "milp"] as Method[]).map((m) => (
                              <td key={m}>
                                {methods
                                  .find((r) => r.method === m)
                                  ?.result_source?.replaceAll("_", " ") ?? "—"}
                              </td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </section>
                  {comparison.data && (
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Changes relative to FCFS</h2>
                          <p>Calculated reductions; zero baselines have no percentage change.</p>
                        </div>
                      </div>
                      <div className="delta-grid">
                        {comparison.data.runs
                          .filter((r) => r.method !== "fcfs")
                          .map((r) => (
                            <div className="delta-card" key={r.id}>
                              <span className="eyebrow">{labels[r.method]} VS FCFS</span>
                              <h3>
                                {fmt(r.changes.total_weighted_tardiness.absolute_reduction)}{" "}
                                <small>weighted min reduction</small>
                              </h3>
                              <p>
                                {r.changes.total_weighted_tardiness.percentage_reduction == null
                                  ? "Percentage reduction: N/A"
                                  : `${fmt(r.changes.total_weighted_tardiness.percentage_reduction, 1)}% reduction`}
                              </p>
                              <Status run={r} />
                            </div>
                          ))}
                      </div>
                    </section>
                  )}
                  <ComparisonExplanation runs={ready} />
                  {selected && !active(selected) && (
                    <RunExplanation
                      key={selected.id}
                      run={selected}
                      choices={ready.map((r) => ({ run: r, label: labels[r.method] }))}
                    />
                  )}
                  <MethodNotes />
                  {methods.find((r) => r.method === "milp") && (
                    <section className="panel diagnostics">
                      <h2>Solver evidence</h2>
                      <p>
                        Best bound: {fmt(methods.find((r) => r.method === "milp")?.best_bound, 2)} ·
                        Relative gap:{" "}
                        {percent(methods.find((r) => r.method === "milp")?.relative_gap)}
                      </p>
                      {methods
                        .find((r) => r.method === "milp")
                        ?.diagnostics.map((d, i) => (
                          <code key={i}>{d}</code>
                        ))}
                    </section>
                  )}
                </>
              )}
              {page === "Scenarios" && (
                <>
                  <ScenarioWorkbench
                    dataset={dataset}
                    onSelect={(s) => {
                      setScenarioId(s.id);
                      setMethod("milp");
                    }}
                  />
                  {!scenario?.kind.startsWith("what_if:") && (
                    <>
                      <section className="scenario-hero panel">
                        <div className="scenario-icon">
                          <Factory size={35} />
                        </div>
                        <div>
                          <span className="eyebrow">CAPACITY EXPLORATION</span>
                          <h2>What changes with one more machine?</h2>
                          <p>
                            Use the same jobs and planning horizon. Keep all original data and
                            results.
                          </p>
                        </div>
                        <button
                          className="button primary"
                          disabled={busy || extraRuns.data?.some(active)}
                          onClick={simulate}
                        >
                          <Plus size={16} />
                          {extra ? "Rerun scenario" : "Simulate additional machine"}
                        </button>
                      </section>
                      <div className="scenario-grid">
                        {[
                          { name: "Current capacity", s: baseline, r: baseBest },
                          { name: "One additional machine", s: extra, r: extraBest },
                        ].map(({ name, s, r }) => (
                          <section className="panel scenario-card" key={name}>
                            <span className="eyebrow">{name.toUpperCase()}</span>
                            <h2>{s ? `${s.machine_count} machines` : "Not simulated"}</h2>
                            <Status run={r} />
                            {r?.metrics ? (
                              <>
                                <div className="scenario-metric">
                                  <strong>{fmt(r.metrics.total_weighted_tardiness)}</strong>
                                  <span>weighted minutes of tardiness</span>
                                </div>
                                <div className="scenario-mini">
                                  <span>
                                    Late jobs <strong>{r.metrics.late_jobs}</strong>
                                  </span>
                                  <span>
                                    Makespan <strong>{r.metrics.makespan_min} min</strong>
                                  </span>
                                  <span>
                                    Window utilization{" "}
                                    <strong>{percent(r.metrics.window_utilization)}</strong>
                                  </span>
                                </div>
                                <p className="muted">
                                  Best known of latest method runs · {labels[r.method]} ·{" "}
                                  {r.result_source?.replaceAll("_", " ")}
                                </p>
                              </>
                            ) : (
                              <p className="muted">
                                {extraRuns.data?.some(active) && name === "One additional machine"
                                  ? "Calculating scenario schedules…"
                                  : "Run the scenario to view calculated results."}
                              </p>
                            )}
                          </section>
                        ))}
                      </div>
                      {scenarioComparison.data && (
                        <div className="notice">
                          <CheckCircle2 size={18} />
                          <p>
                            Weighted tardiness reduction:{" "}
                            <strong>
                              {fmt(
                                scenarioComparison.data.runs[1].changes.total_weighted_tardiness
                                  .absolute_reduction,
                              )}{" "}
                              weighted min
                            </strong>
                            . This compares the best known schedules, not necessarily proven optima.
                            Capacity effects do not establish purchasing ROI.
                          </p>
                        </div>
                      )}
                      <p className="muted scenario-caveat">
                        An extra machine can reduce the true optimal tardiness. Time-limited
                        searches may return different incumbent quality; the displayed changes are
                        measured outcomes.
                      </p>
                    </>
                  )}
                </>
              )}
              {page === "Data explorer" && (
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Production jobs</h2>
                      <p>
                        {dataset.source_kind === "synthetic"
                          ? `Synthetic dataset · seed ${dataset.seed}`
                          : "Imported CSV dataset"}{" "}
                        · immutable after creation
                      </p>
                    </div>
                    {run && (
                      <a
                        className="button secondary"
                        href={`/api/v1/runs/${run.id}/exports/jobs.csv`}
                      >
                        <ArrowDownToLine size={15} />
                        Export jobs
                      </a>
                    )}
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Job ID</th>
                          <th>Processing (min)</th>
                          <th>Release (min)</th>
                          <th>Due (min)</th>
                          <th>Weight</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.jobs.map((j) => (
                          <tr key={j.job_id}>
                            <td>
                              <button className="text-button" onClick={() => setJob(j)}>
                                {j.job_id}
                              </button>
                            </td>
                            <td>{j.processing_time_min}</td>
                            <td>{j.release_time_min}</td>
                            <td>{j.due_time_min}</td>
                            <td>
                              <span className="weight-chip">{j.priority_weight}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="data-hash">
                    Job-data hash <code>{dataset.job_hash}</code>
                  </div>
                </section>
              )}
            </>
          )}
          <footer className="main-footer">
            <span>{PRODUCT_NAME}</span>
            <span>
              <CheckCircle2 size={13} />
              Calculated results. Transparent assumptions.
            </span>
          </footer>
        </main>
      </div>
      {dataOpen && (
        <DataDialog
          onClose={() => setDataOpen(false)}
          onCreated={(d) => {
            client.invalidateQueries({ queryKey: ["datasets"] });
            selectDataset(d);
            setScenarioId(null);
            setMethod("edd");
            setPage("Overview");
            setAnswers([]);
          }}
        />
      )}
      {descriptionOpen && (
        <WorkloadDescriptionDialog
          available={health.data?.ai_available ?? false}
          budget={solverBudget}
          onClose={() => setDescriptionOpen(false)}
          onCreated={(d) => {
            client.invalidateQueries({ queryKey: ["datasets"] });
            client.invalidateQueries({ queryKey: ["runs"] });
            selectDataset(d);
            setScenarioId(d.scenarios[0].id);
            setMethod("milp");
            setPage("Overview");
            setAnswers([]);
            setDescriptionOpen(false);
          }}
        />
      )}
      {managerOpen && (
        <DatasetManager
          datasets={datasets.data ?? []}
          showTests={showTests}
          onShowTests={changeTestVisibility}
          onSelect={selectDataset}
          onClose={() => setManagerOpen(false)}
          onChanged={(changed) => {
            client.setQueryData<Dataset[]>(["datasets"], (previous) =>
              previous?.map((d) => (d.id === changed.id ? changed : d)),
            );
            if (changed.is_archived && changed.id === dataset?.id) {
              const next = visibleDatasets(
                (datasets.data ?? []).filter((d) => d.id !== changed.id),
                showTests,
              )[0];
              setDatasetId(next?.id ?? null);
              setScenarioId(null);
              setMethod("edd");
              setAnswers([]);
            }
            client.invalidateQueries({ queryKey: ["datasets"] });
          }}
        />
      )}
      {exportOpen && (
        <ExportDialog
          run={run}
          methods={ready}
          baseline={latestMethods(baseRuns.data ?? []).filter((r) => r.has_valid_schedule)}
          additional={latestMethods(extraRuns.data ?? []).filter((r) => r.has_valid_schedule)}
          onClose={() => setExportOpen(false)}
        />
      )}
      {helpTopic && (
        <MetricHelp
          topic={helpTopic}
          run={run}
          dataset={dataset}
          onClose={() => setHelpTopic(null)}
        />
      )}
      {job && (
        <DialogFrame
          onClose={() => setJob(null)}
          labelledBy="job-title"
          className="modal job-modal"
        >
          <div className="modal-title">
            <div>
              <span className="eyebrow">PRODUCTION ORDER</span>
              <h2 id="job-title">{job.job_id}</h2>
            </div>
            <button
              className="icon-button"
              aria-label="Close job details"
              onClick={() => setJob(null)}
            >
              <X size={20} />
            </button>
          </div>
          <dl className="job-details">
            <div>
              <dt>Processing time</dt>
              <dd>{job.processing_time_min} min</dd>
            </div>
            <div>
              <dt>Release time</dt>
              <dd>{job.release_time_min} min</dd>
            </div>
            <div>
              <dt>Due time</dt>
              <dd>{job.due_time_min} min</dd>
            </div>
            <div>
              <dt>Priority weight</dt>
              <dd>{job.priority_weight}</dd>
            </div>
            {run?.placements
              .filter((p) => p.job_id === job.job_id)
              .map((p) => (
                <div key={p.job_id}>
                  <dt>{labels[run.method]} assignment</dt>
                  <dd>
                    {p.machine_code} · {p.start_min}–{p.completion_min} min
                  </dd>
                </div>
              ))}
          </dl>
          <p className="muted">Due times are soft targets. Jobs remain schedulable when late.</p>
        </DialogFrame>
      )}
      {rulesOpen && dataset && scenario && (
        <RulesDialog
          dataset={dataset}
          scenario={scenario}
          budget={solverBudget}
          proposal={rulesProposal}
          onClose={() => setRulesOpen(false)}
          onCreated={rulesCreated}
        />
      )}
      {copilotOpen && (
        <DialogFrame
          onClose={() => setCopilotOpen(false)}
          labelledBy="copilot-title"
          className="copilot-panel"
          backdropClass="copilot-backdrop"
        >
          <div className="copilot-header">
            <span className="brand-icon">
              <Sparkles size={21} />
            </span>
            <div>
              <h2 id="copilot-title">Operations copilot</h2>
              <p>
                {health.data?.ai_available && health.data.ai_model === "gpt-6.1-sol"
                  ? "GPT-6.1 Sol · Low reasoning"
                  : "Grounded in your actual schedule"}
              </p>
            </div>
            <button
              className="icon-button"
              aria-label="Close copilot"
              onClick={() => setCopilotOpen(false)}
            >
              <X size={20} />
            </button>
          </div>
          <div className="copilot-content">
            {error && (
              <p role="alert" className="error-message">
                {error}
              </p>
            )}
            {!health.data?.ai_available ? (
              <div className="copilot-disabled">
                <Sparkles size={32} />
                <h3>AI is optional.</h3>
                <p>
                  Your scheduling engine, analytics, scenarios, and exports work without an API key.
                </p>
                <div className="notice">
                  <p>
                    Connect an OpenAI API account or a local ChatGPT Codex login to enable the
                    copilot.
                  </p>
                </div>
                <button
                  className="button secondary"
                  onClick={() => {
                    setCopilotOpen(false);
                    setPage("Comparison");
                  }}
                >
                  Explore scheduling results <ArrowRight size={15} />
                </button>
              </div>
            ) : (
              <>
                <p className="muted">
                  Context: {dataset?.name ?? "No dataset selected"} ·{" "}
                  {run ? labels[run.method] : "No schedule yet"}
                </p>
                {health.data?.ai_provider === "codex_subscription" && (
                  <p className="muted">Connected through your local ChatGPT subscription.</p>
                )}
                <div className="suggested-questions">
                  {[
                    "Which orders are late?",
                    "Show machine utilization",
                    "Optimize the production schedule",
                    "What changes with another machine?",
                    "Explain the weighted tardiness tradeoffs",
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => {
                        setQuestion(q);
                        ask(q);
                      }}
                      disabled={!scenario || thinking}
                    >
                      {q}
                      <ArrowRight size={13} />
                    </button>
                  ))}
                </div>
                {answers.map((a, i) => (
                  <div className="conversation" key={i}>
                    <p className="user-question">{a.question}</p>
                    <div className="answer-facts">
                      {a.response.facts.map((f, n) => (
                        <div key={n}>
                          <span>{f.label}</span>
                          <strong>
                            {f.value} <small>{f.unit}</small>
                          </strong>
                          <a
                            href={`#evidence-${f.evidence_id}`}
                            onClick={(event) => {
                              event.preventDefault();
                              const target = document.getElementById(`evidence-${f.evidence_id}`);
                              const details = target?.closest("details");
                              if (details) details.open = true;
                              target?.scrollIntoView({ block: "nearest" });
                              target?.focus();
                            }}
                          >
                            Evidence {f.evidence_id}
                          </a>
                        </div>
                      ))}
                    </div>
                    {a.response.interpretation && (
                      <p className="muted">Interpretation: {a.response.interpretation}</p>
                    )}
                    {a.response.proposal && (
                      <div className="notice">
                        <h3>Scenario proposal — awaiting confirmation</h3>
                        <p>
                          {a.response.proposal.job_ids.join(", ") || "No additional hard deadlines"}{" "}
                          · {a.response.proposal.machine_count} machines
                        </p>
                        <button
                          className="button primary"
                          disabled={a.response.proposal.scenario_id !== scenario?.id}
                          onClick={() => {
                            setRulesProposal(a.response.proposal!);
                            setCopilotOpen(false);
                            setRulesOpen(true);
                          }}
                        >
                          Review proposed scenario
                        </button>
                      </div>
                    )}
                    {a.response.fallback && (
                      <p className="muted">
                        Showing the available calculated facts from this context.
                      </p>
                    )}
                    {a.response.pending_run_ids.map((id) => (
                      <PendingRun key={id} id={id} />
                    ))}
                    <details>
                      <summary>{a.response.tool_trace.length} tool activity events</summary>
                      {a.response.tool_trace.map((t) => (
                        <div
                          id={`evidence-${t.evidence_id}`}
                          tabIndex={-1}
                          className="tool-evidence"
                          key={t.evidence_id}
                        >
                          <strong>{t.tool}</strong>
                          <pre>{JSON.stringify(t.data, null, 2)}</pre>
                        </div>
                      ))}
                    </details>
                  </div>
                ))}
              </>
            )}
          </div>
          {health.data?.ai_available && (
            <form
              className="copilot-input"
              onSubmit={(e) => {
                e.preventDefault();
                ask();
              }}
            >
              <input
                aria-label="Ask operations copilot"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask about your production plan…"
                disabled={!scenario || thinking}
              />
              <button
                className="button primary"
                aria-label="Send question"
                disabled={!question.trim() || thinking || !scenario}
              >
                {thinking ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}
              </button>
            </form>
          )}
        </DialogFrame>
      )}
    </div>
  );
}

function KPICard({
  label,
  value,
  unit,
  icon,
  detail,
  onHelp,
  accent = "green",
}: {
  label: string;
  value: string;
  unit?: string;
  icon: React.ReactNode;
  detail: string;
  onHelp?: () => void;
  accent?: string;
}) {
  return (
    <section className="kpi-card">
      <div className="kpi-label">
        <span className="metric-label">
          {label}
          {onHelp && (
            <button className="metric-help-button" aria-label={`Explain ${label}`} onClick={onHelp}>
              <CircleHelp size={14} />
            </button>
          )}
        </span>
        <span className={`kpi-icon ${accent}`}>{icon}</span>
      </div>
      <div className="kpi-value">
        {value}
        {unit && <span>{unit}</span>}
      </div>
      <p>{detail}</p>
    </section>
  );
}
function MethodNotes() {
  return (
    <section className="panel method-notes">
      <h2>How the methods work</h2>
      <div>
        <article>
          <span className="number-label">01</span>
          <h3>First come, first served</h3>
          <p>
            Dispatch released jobs by release time, then job ID. Never reserve a machine for an
            unreleased order.
          </p>
        </article>
        <article>
          <span className="number-label">02</span>
          <h3>Earliest due date</h3>
          <p>
            Dispatch available jobs by due time. Release time and job ID provide deterministic
            tie-breaking.
          </p>
        </article>
        <article>
          <span className="number-label">03</span>
          <h3>Mathematical optimization</h3>
          <p>
            CBC solves a mixed integer model minimizing weighted tardiness. It may wait
            intentionally; a time limit is not proof of optimality.
          </p>
        </article>
      </div>
    </section>
  );
}
function ScheduleTable({ run, dataset }: { run: Run; dataset: Dataset }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Schedule details</h2>
          <p>Accessible tabular view of the displayed schedule</p>
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Machine</th>
              <th>Start</th>
              <th>Completion</th>
              <th>Due</th>
              <th>Tardiness</th>
            </tr>
          </thead>
          <tbody>
            {run.placements.map((p) => {
              const j = dataset.jobs.find((j) => j.job_id === p.job_id)!;
              return (
                <tr key={p.job_id}>
                  <td>{p.job_id}</td>
                  <td>{p.machine_code}</td>
                  <td>{p.start_min}</td>
                  <td>{p.completion_min}</td>
                  <td>{j.due_time_min}</td>
                  <td>{Math.max(0, p.completion_min - j.due_time_min)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
function PendingRun({ id }: { id: string }) {
  const run = useQuery({
    queryKey: ["run", id],
    queryFn: () => api<Run>(`/runs/${id}`),
    refetchInterval: (q) => (q.state.data && !active(q.state.data) ? false : 2000),
  });
  return (
    <div className="notice">
      <Clock3 size={16} />
      <div>
        <strong>{run.data ? labels[run.data.method] : "Scheduling"} run</strong>
        <Status run={run.data} />
        {run.data?.metrics && (
          <p>
            {run.data.metrics.machine_count} machines · Weighted tardiness:{" "}
            {fmt(run.data.metrics.total_weighted_tardiness)} weighted min · Late jobs:{" "}
            {run.data.metrics.late_jobs}
          </p>
        )}
      </div>
    </div>
  );
}
