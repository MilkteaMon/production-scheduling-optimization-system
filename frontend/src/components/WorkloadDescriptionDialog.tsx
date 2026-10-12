import { useState } from "react";
import { Sparkles, X } from "lucide-react";
import DialogFrame from "./DialogFrame";
import { post, type Dataset, type WorkloadDraft, type WorkloadPreview } from "../api/client";

const completeExample =
  "我有两台相同的机器。订单 A 加工需要 40 分钟，90 分钟内交付；订单 B 需要 20 分钟，60 分钟内交付。两个订单现在都可以开工，A 必须准时完成。";
const partialExample = "我有两台相同的机器。订单 A 需要 40 分钟，订单 B 需要 20 分钟。";
type DraftJob = WorkloadDraft["jobs"][number];
const columns = [
  ["processing_time_min", "Processing (min)", "Required"],
  ["release_time_min", "Available (min)", "Default 0"],
  ["due_time_min", "Due (min)", "Required"],
  ["priority_weight", "Weight (1–10)", "Default 1"],
] as const;

export default function WorkloadDescriptionDialog({
  available,
  budget,
  onClose,
  onCreated,
}: {
  available: boolean;
  budget: number;
  onClose: () => void;
  onCreated: (dataset: Dataset) => void;
}) {
  const [description, setDescription] = useState("");
  const [supplement, setSupplement] = useState("");
  const [draft, setDraft] = useState<WorkloadDraft | null>(null);
  const [preview, setPreview] = useState<WorkloadPreview | null>(null);
  const [name, setName] = useState("Described production workload");
  const [acknowledged, setAcknowledged] = useState(false);
  const [confirmationId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState<"parse" | "review" | "confirm" | null>(null);
  const [error, setError] = useState("");
  const close = () => {
    if (busy !== "confirm") onClose();
  };
  function replaceDescription(value: string) {
    setDescription(value);
    setDraft(null);
    setPreview(null);
    setAcknowledged(false);
    setSupplement("");
  }
  function updateDraft(next: WorkloadDraft) {
    setDraft(next);
    setPreview(null);
    setAcknowledged(false);
  }
  function updateJob(
    index: number,
    field: keyof DraftJob,
    value: string | number | boolean | null,
  ) {
    if (!draft) return;
    updateDraft({
      ...draft,
      jobs: draft.jobs.map((job, i) => (i === index ? { ...job, [field]: value } : job)),
    });
  }
  async function parse(addDetails = false) {
    const text = addDetails ? `${description}\n补充 / Supplement: ${supplement}` : description;
    setBusy("parse");
    setError("");
    setAcknowledged(false);
    try {
      const result = await post<WorkloadPreview>("/natural-language/parse", { description: text });
      setDescription(text);
      setDraft(result.draft);
      setPreview(result);
      setSupplement("");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }
  async function review() {
    if (!draft) return;
    setBusy("review");
    setError("");
    try {
      setPreview(await post<WorkloadPreview>("/natural-language/review", { description, draft }));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }
  async function confirm() {
    if (!draft || !preview?.ready || !acknowledged) return;
    setBusy("confirm");
    setError("");
    try {
      const dataset = await post<Dataset>("/natural-language/confirm", {
        description,
        draft,
        name,
        confirmation_id: confirmationId,
        confirmed: true,
        time_limit_seconds: budget,
      });
      onCreated(dataset);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }
  return (
    <DialogFrame
      onClose={close}
      labelledBy="description-title"
      className="modal description-dialog"
    >
      <div className="panel-heading">
        <h2 id="description-title">Create a plan from your description</h2>
        <button
          className="icon-button"
          aria-label="Close description"
          disabled={busy === "confirm"}
          onClick={close}
        >
          <X size={18} />
        </button>
      </div>
      <p>
        Describe your machines, orders and deadlines in Chinese or English. Review an editable draft
        before creating any data or calculating a schedule.
      </p>
      <p className="muted">
        Times are whole minutes from one common planning start. Supports 1–5 identical machines and
        up to 50 single-operation orders.
      </p>
      {!available && (
        <p className="notice">
          Connect AI to interpret a description. CSV imports and the existing data generator remain
          available.
        </p>
      )}
      <label className="description-field">
        Workload description
        <textarea
          aria-label="Workload description"
          rows={5}
          maxLength={8000}
          value={description}
          disabled={!!busy}
          onChange={(e) => replaceDescription(e.target.value)}
          placeholder={completeExample}
        />
      </label>
      <div className="rule-actions">
        <button
          className="button secondary"
          disabled={!!busy}
          onClick={() => replaceDescription(completeExample)}
        >
          Use complete example
        </button>
        <button
          className="button secondary"
          disabled={!!busy}
          onClick={() => replaceDescription(partialExample)}
        >
          Use incomplete example
        </button>
        <button
          className="button primary"
          disabled={!!busy || !available || !description.trim()}
          onClick={() => parse()}
        >
          <Sparkles size={15} /> {busy === "parse" ? "Interpreting…" : "Interpret description"}
        </button>
      </div>
      <p className="muted">
        Interpreting sends this description to your connected AI account. Each interpretation uses
        one model request; editing and checking the draft use local validation.
      </p>
      {draft && (
        <section aria-label="Editable workload draft" className="description-draft">
          <h3>Review your workload</h3>
          <div className="description-settings">
            <label className="description-field">
              Workload name
              <input
                aria-label="Described workload name"
                value={name}
                maxLength={100}
                disabled={!!busy}
                onChange={(e) => {
                  setName(e.target.value);
                  setAcknowledged(false);
                }}
              />
            </label>
            <label className="description-field">
              Identical machines
              <input
                aria-label="Described machine count"
                type="number"
                min={1}
                max={5}
                step={1}
                value={draft.machine_count ?? ""}
                disabled={!!busy}
                onChange={(e) =>
                  updateDraft({
                    ...draft,
                    machine_count: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
          <p className="muted">
            Due times are soft targets. Select “Must finish on time” for a hard deadline. Unstated
            available times default to 0 and priorities to equal weight 1; all applied defaults are
            listed below.
          </p>
          <div className="table-scroll">
            <table className="description-table">
              <caption>Draft orders — missing required values must be supplied</caption>
              <thead>
                <tr>
                  <th scope="col">Order ID</th>
                  <th scope="col">Source name</th>
                  {columns.map(([key, title]) => (
                    <th scope="col" key={key}>
                      {title}
                    </th>
                  ))}
                  <th scope="col">Must finish on time</th>
                </tr>
              </thead>
              <tbody>
                {draft.jobs.map((row, index) => (
                  <tr key={index}>
                    <td>
                      <input
                        aria-label={`Order ${index + 1} ID`}
                        value={row.job_id ?? ""}
                        disabled={!!busy}
                        maxLength={64}
                        placeholder="Suggested below"
                        onChange={(e) => updateJob(index, "job_id", e.target.value || null)}
                      />
                    </td>
                    <td>{row.label || "—"}</td>
                    {columns.map(([key, , placeholder]) => (
                      <td key={key}>
                        <input
                          aria-label={`Order ${index + 1} ${key}`}
                          type="number"
                          step={1}
                          value={row[key] ?? ""}
                          placeholder={placeholder}
                          disabled={!!busy}
                          onChange={(e) =>
                            updateJob(
                              index,
                              key,
                              e.target.value === "" ? null : Number(e.target.value),
                            )
                          }
                        />
                      </td>
                    ))}
                    <td>
                      <input
                        aria-label={`Order ${index + 1} must finish on time`}
                        type="checkbox"
                        checked={row.must_finish_on_time}
                        disabled={!!busy}
                        onChange={(e) => updateJob(index, "must_finish_on_time", e.target.checked)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button className="button secondary" disabled={!!busy} onClick={review}>
            {busy === "review" ? "Checking…" : "Check edited draft"}
          </button>
          {!preview && (
            <p className="notice">The draft changed. Check it again before confirming.</p>
          )}
          {preview && (
            <section
              aria-label="Workload review result"
              className="notice description-review"
              aria-live="polite"
            >
              <h3>
                {preview.ready ? "Ready for your confirmation" : "More information is needed"}
              </h3>
              {preview.questions.length > 0 && (
                <ul>
                  {preview.questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              )}
              {preview.errors.length > 0 && (
                <ul className="error-message">
                  {preview.errors.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              )}
              {preview.unsupported_requirements.length > 0 && (
                <>
                  <h4>Requirements outside this scheduling model</h4>
                  <ul>
                    {preview.unsupported_requirements.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </>
              )}
              {preview.assumptions.length > 0 && (
                <>
                  <h4>Defaults and suggested IDs to approve</h4>
                  <ul>
                    {preview.assumptions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </>
              )}
              {preview.warnings.map((q, i) => (
                <p key={i}>{q}</p>
              ))}
              {preview.planning_input && (
                <p>
                  {preview.planning_input.jobs.length} orders ·{" "}
                  {preview.planning_input.machine_count} machines ·{" "}
                  {preview.planning_input.must_finish_job_ids?.length ?? 0} hard deadlines ·
                  planning horizon {preview.planning_input.horizon_min} min.
                </p>
              )}
            </section>
          )}
          {preview && !preview.ready && (
            <div className="description-supplement">
              <label className="description-field">
                Add details in your own words
                <textarea
                  aria-label="Additional workload details"
                  rows={2}
                  value={supplement}
                  disabled={!!busy}
                  maxLength={Math.max(0, 8000 - description.length - 24)}
                  onChange={(e) => setSupplement(e.target.value)}
                  placeholder="例如：A 在 90 分钟内交付，B 在 60 分钟内交付。"
                />
              </label>
              <button
                className="button secondary"
                disabled={!!busy || !available || !supplement.trim()}
                onClick={() => parse(true)}
              >
                Add details and re-interpret
              </button>
            </div>
          )}
          <label className="rule-job">
            <input
              type="checkbox"
              aria-label="Approve workload draft"
              checked={acknowledged}
              disabled={!!busy || !preview?.ready}
              onChange={(e) => setAcknowledged(e.target.checked)}
            />
            I reviewed the orders, machine count, deadlines and listed defaults.
          </label>
          <p className="muted">
            Confirmation creates a new workload and calculates FCFS, EDD and MILP with a {budget}
            -second solver budget. Existing workloads stay available. Hard deadlines may be
            infeasible.
          </p>
        </section>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      <div className="modal-footer">
        <button className="button secondary" disabled={busy === "confirm"} onClick={close}>
          Cancel
        </button>
        <button
          className="button primary"
          disabled={!!busy || !preview?.ready || !acknowledged || !name.trim()}
          onClick={confirm}
        >
          {busy === "confirm" ? "Creating…" : "Confirm and create plan"}
        </button>
      </div>
    </DialogFrame>
  );
}
