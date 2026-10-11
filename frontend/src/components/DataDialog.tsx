import { useState } from "react";
import DialogFrame from "./DialogFrame";
import { X, Upload, FlaskConical, CheckCircle2, AlertCircle } from "lucide-react";
import { api, post, type Dataset, type Preview } from "../api/client";

export default function DataDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (d: Dataset) => void;
}) {
  const [mode, setMode] = useState<"generate" | "upload">("generate");
  const [jobs, setJobs] = useState(30),
    [machines, setMachines] = useState(4),
    [seed, setSeed] = useState(42),
    [profile, setProfile] = useState("tight");
  const [name, setName] = useState("Synthetic production demo");
  const [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  function form() {
    const body = new FormData();
    body.append("file", file!);
    body.append("machine_count", String(machines));
    body.append("name", name);
    body.append("confirmed", "true");
    return body;
  }
  async function inspect() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setPreview(await api<Preview>("/datasets/validate-csv", { method: "POST", body: form() }));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function create() {
    setBusy(true);
    setError("");
    try {
      const d =
        mode === "generate"
          ? await post<Dataset>("/datasets/generate", {
              name,
              job_count: jobs,
              machine_count: machines,
              seed,
              profile,
              confirmed: true,
            })
          : await api<Dataset>("/datasets/import", { method: "POST", body: form() });
      onCreated(d);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <DialogFrame onClose={onClose} labelledBy="data-title">
      <div className="modal-title">
        <div>
          <span className="eyebrow">PRODUCTION DATA</span>
          <h2 id="data-title">Start with your workload</h2>
        </div>
        <button className="icon-button" aria-label="Close data dialog" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <div className="segmented">
        <button
          className={mode === "generate" ? "selected" : ""}
          onClick={() => setMode("generate")}
        >
          <FlaskConical size={16} />
          Generate synthetic data
        </button>
        <button className={mode === "upload" ? "selected" : ""} onClick={() => setMode("upload")}>
          <Upload size={16} />
          Upload CSV
        </button>
      </div>
      <label>
        Dataset name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
      </label>
      <div className="form-grid">
        <label>
          Machines
          <input
            type="number"
            min={1}
            max={5}
            value={machines}
            onChange={(e) => {
              setMachines(Number(e.target.value));
              setPreview(null);
            }}
          />
        </label>
        {mode === "generate" && (
          <>
            <label>
              Jobs
              <input
                type="number"
                min={1}
                max={50}
                value={jobs}
                onChange={(e) => setJobs(Number(e.target.value))}
              />
            </label>
            <label>
              Random seed
              <input
                type="number"
                min={0}
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
              />
            </label>
            <label>
              Workload profile
              <select value={profile} onChange={(e) => setProfile(e.target.value)}>
                <option value="tight">Tight deadlines</option>
                <option value="relaxed">Relaxed deadlines</option>
                <option value="staggered">Staggered releases</option>
              </select>
            </label>
          </>
        )}
      </div>
      {mode === "generate" ? (
        <div className="notice">
          <FlaskConical size={18} />
          <p>
            Clearly labelled synthetic data. The seed reproduces the same workload; no company data
            is used. Confirming creates a new dataset and calculates both baselines.
          </p>
        </div>
      ) : (
        <>
          <label className="upload-zone">
            <Upload size={25} />
            <strong>{file?.name ?? "Choose a production CSV"}</strong>
            <span>UTF-8 · up to 50 jobs · maximum 1 MB</span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setPreview(null);
              }}
            />
          </label>
          <p className="muted csv-columns">
            Required columns: job_id, processing_time_min, release_time_min, due_time_min,
            priority_weight
          </p>
          <button className="button secondary" disabled={!file || busy} onClick={inspect}>
            Validate and preview
          </button>
          {preview && (
            <div className={`notice ${preview.valid ? "" : "error"}`}>
              {preview.valid ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
              <div>
                <strong>
                  {preview.valid
                    ? `${preview.total_jobs} valid jobs. Ready for your confirmation.`
                    : "Please fix the CSV errors."}
                </strong>
                {preview.errors.map((e, i) => (
                  <p key={i}>
                    Row {e.row ?? "—"} · {e.field}: {e.message}
                  </p>
                ))}
                {preview.warnings?.slice(0, 5).map((w) => (
                  <p key={w}>{w}</p>
                ))}
              </div>
            </div>
          )}
          {preview?.valid && (
            <div className="table-scroll csv-preview">
              <table aria-label="CSV preview">
                <caption>
                  First {Math.min(5, preview.jobs.length)} jobs of {preview.total_jobs}
                </caption>
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Process min</th>
                    <th>Release min</th>
                    <th>Due min</th>
                    <th>Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.jobs.slice(0, 5).map((job) => (
                    <tr key={job.job_id}>
                      <th scope="row">{job.job_id}</th>
                      <td>{job.processing_time_min}</td>
                      <td>{job.release_time_min}</td>
                      <td>{job.due_time_min}</td>
                      <td>{job.priority_weight}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <div className="modal-footer">
        <button className="button secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          className="button primary"
          disabled={busy || !name.trim() || (mode === "upload" && !preview?.valid)}
          onClick={create}
        >
          {busy ? "Creating…" : mode === "generate" ? "Confirm and generate" : "Confirm import"}
        </button>
      </div>
    </DialogFrame>
  );
}
