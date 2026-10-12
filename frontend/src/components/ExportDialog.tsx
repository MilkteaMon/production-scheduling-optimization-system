import { useState } from "react";
import { Download, LoaderCircle, X } from "lucide-react";
import { labels, type Run } from "../api/client";
import DialogFrame from "./DialogFrame";
import { FILE_PREFIX } from "../data/branding";

export default function ExportDialog({
  run,
  methods,
  baseline,
  additional,
  onClose,
}: {
  run?: Run;
  methods: Run[];
  baseline: Run[];
  additional: Run[];
  onClose: () => void;
}) {
  const [mode, setMode] = useState("current");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const comparisonReady = ["fcfs", "edd", "milp"].every((m) => methods.some((r) => r.method === m));
  const scenarioReady = baseline.length > 0 && additional.length > 0;
  const selected =
    mode === "current"
      ? run
        ? [run]
        : []
      : mode === "methods"
        ? methods
        : [...baseline, ...additional];
  async function download() {
    if (!selected.length) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/v1/exports/power-bi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_ids: selected.map((r) => r.id) }),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(typeof body.detail === "string" ? body.detail : "Export failed");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `${FILE_PREFIX}-power-bi-${mode}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <DialogFrame onClose={onClose} labelledBy="export-title">
      <div className="modal-title">
        <div>
          <span className="eyebrow">REPORTING</span>
          <h2 id="export-title">Export to Power BI</h2>
        </div>
        <button className="icon-button" aria-label="Close export dialog" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <p className="dialog-intro">
        Download compatible calculated results in one ZIP. Exporting starts no new optimization.
      </p>
      <label htmlFor="export-scope">Export scope</label>
      <select
        id="export-scope"
        value={mode}
        onChange={(e) => setMode(e.target.value)}
        disabled={busy}
      >
        <option value="current" disabled={!run}>
          Current displayed run
        </option>
        <option value="methods" disabled={!comparisonReady}>
          FCFS / EDD / MILP comparison
        </option>
        <option value="scenarios" disabled={!scenarioReady}>
          Baseline + one additional machine
        </option>
      </select>
      {!comparisonReady && (
        <p className="export-hint">
          Complete all three methods to enable the method-comparison package.
        </p>
      )}
      {!scenarioReady && (
        <p className="export-hint">
          Calculate the additional-machine scenario to enable the scenario package.
        </p>
      )}
      <div className="export-runs" aria-label="Runs included in export">
        {selected.map((r) => (
          <div key={r.id}>
            <strong>
              {labels[r.method]} · {r.metrics?.machine_count} machines
            </strong>
            <span>
              {r.must_finish_job_ids?.length ?? 0} hard deadlines
              {r.must_finish_job_ids?.length ? `: ${r.must_finish_job_ids.join(", ")}` : ""}
            </span>
            <span>
              {r.method === "milp" ? r.solver_status.replaceAll("_", " ") : "validated baseline"} ·{" "}
              {r.id.slice(0, 8)}
            </span>
          </div>
        ))}
      </div>
      <p className="export-hint">
        Includes Jobs, Schedule, Machines, RunKPIs, exact run metadata, import instructions, Power
        Query source and DAX measures. The query source prepares tables; model relationships are
        described in the README.
      </p>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        <button className="button primary" onClick={download} disabled={busy || !selected.length}>
          {busy ? <LoaderCircle className="spin" size={17} /> : <Download size={17} />}
          {busy ? "Preparing package…" : "Download Power BI package"}
        </button>
      </div>
    </DialogFrame>
  );
}
