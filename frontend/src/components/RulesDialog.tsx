import { useState } from "react";
import { X } from "lucide-react";
import DialogFrame from "./DialogFrame";
import {
  post,
  type Dataset,
  type Scenario,
  type RulesApplied,
  type RulesPreview,
} from "../api/client";

export default function RulesDialog({
  dataset,
  scenario,
  budget,
  proposal,
  onClose,
  onCreated,
}: {
  dataset: Dataset;
  scenario: Scenario;
  budget: number;
  proposal?: RulesPreview | null;
  onClose: () => void;
  onCreated: (result: RulesApplied) => void;
}) {
  const [ids, setIds] = useState<string[]>(proposal?.job_ids ?? scenario.must_finish_job_ids ?? []);
  const [addMachine, setAddMachine] = useState(proposal?.add_machine ?? false);
  const [preview, setPreview] = useState<RulesPreview | null>(proposal ?? null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const inherited = new Set(scenario.must_finish_job_ids ?? []);
  async function submit(confirm: boolean) {
    setBusy(true);
    setError("");
    try {
      const body = {
        job_ids: ids,
        add_machine: addMachine,
        confirmed: confirm,
        time_limit_seconds: budget,
      };
      if (confirm) {
        if (!preview || preview.scenario_id !== scenario.id)
          throw new Error("Preview these rules in the selected scenario first.");
        onCreated(await post<RulesApplied>(`/scenarios/${scenario.id}/rules`, body));
      } else setPreview(await post<RulesPreview>(`/scenarios/${scenario.id}/rules/preview`, body));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <DialogFrame onClose={onClose} labelledBy="rules-title" className="modal rules-dialog">
      <div className="panel-heading">
        <h2 id="rules-title">On-time commitments & What-if</h2>
        <button className="icon-button" aria-label="Close rules" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
      <p>
        Select orders that must finish by their existing due time. A new scenario preserves the
        original jobs and runs.
      </p>
      <p className="muted">
        Current scenario: {scenario.name}. Inherited commitments remain selected. Solver budget:{" "}
        {budget} seconds.
      </p>
      <fieldset className="rule-jobs">
        <legend>Required on-time orders</legend>
        {dataset.jobs.map((j) => (
          <label key={j.job_id} className="rule-job">
            <input
              type="checkbox"
              aria-label={`Require ${j.job_id} on time`}
              checked={ids.includes(j.job_id)}
              disabled={busy || inherited.has(j.job_id)}
              onChange={(e) => {
                setIds(e.target.checked ? [...ids, j.job_id] : ids.filter((id) => id !== j.job_id));
                setPreview(null);
              }}
            />
            <span>
              <strong>{j.job_id}</strong> · due {j.due_time_min} min · processing{" "}
              {j.processing_time_min} min · release {j.release_time_min} min
            </span>
          </label>
        ))}
      </fieldset>
      <label className="rule-job">
        <input
          type="checkbox"
          checked={addMachine}
          disabled={busy || scenario.machine_count >= 6}
          onChange={(e) => {
            setAddMachine(e.target.checked);
            setPreview(null);
          }}
        />
        Add one identical machine ({scenario.machine_count} → {scenario.machine_count + 1})
      </label>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {preview && (
        <section className="notice" aria-label="Scenario rule preview">
          <h3>Review before calculating</h3>
          <p>
            {preview.base_machine_count} → {preview.machine_count} machines ·{" "}
            {preview.job_ids.length} hard deadlines · unchanged horizon {preview.horizon_min} min
          </p>
          <ul>
            {preview.deadlines.map((d) => (
              <li key={d.job_id}>
                {d.job_id}: must complete by {d.due_time_min} min; earliest possible completion{" "}
                {d.earliest_completion_min} min.
              </li>
            ))}
          </ul>
          {preview.warnings.map((w) => (
            <p key={w}>{w}. This scenario is impossible under the selected deadline.</p>
          ))}
          <p>
            FCFS and EDD may violate these rules. Only independently validated schedules can be
            compared or exported.
          </p>
        </section>
      )}
      <div className="rule-actions">
        <button
          className="button secondary"
          disabled={busy || (!ids.length && !addMachine)}
          onClick={() => submit(false)}
        >
          Preview rules
        </button>
        <button className="button primary" disabled={busy || !preview} onClick={() => submit(true)}>
          {busy ? "Working…" : "Confirm and calculate scenario"}
        </button>
      </div>
    </DialogFrame>
  );
}
