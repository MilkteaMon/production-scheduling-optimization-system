import type { components } from "./schema";
export type Job = components["schemas"]["Job"];
export type Scenario = components["schemas"]["ScenarioRead"];
export type Dataset = components["schemas"]["DatasetRead"];
export type Method = components["schemas"]["RunRead"]["method"];
export type Placement = components["schemas"]["Placement"];
export type Metrics = components["schemas"]["KPI"];
export type Run = components["schemas"]["RunRead"];
export type Health = components["schemas"]["HealthRead"];
export type Preview = components["schemas"]["PreviewRead"];
export type Evidence = components["schemas"]["EvidenceRead"];
export type CopilotResponse = components["schemas"]["CopilotRead"];
export type RulesPreview = components["schemas"]["RulesPreviewRead"];
export type RulesApplied = components["schemas"]["RulesAppliedRead"];
export type Explanation = components["schemas"]["ExplanationRead"];
export type WorkloadDraft = components["schemas"]["WorkloadDraft"];
export type WorkloadPreview = components["schemas"]["WorkloadPreviewRead"];

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* Keep HTTP error. */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const fmt = (v: number | null | undefined, digits = 0) =>
  v == null ? "—" : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(v);
export const percent = (v: number | null | undefined) =>
  v == null ? "N/A" : `${fmt(v * 100, 1)}%`;
export const labels: Record<Method, string> = { fcfs: "FCFS", edd: "EDD", milp: "MILP" };
export const active = (run: Run) => ["queued", "running"].includes(run.execution_state);
export function latestMethods(runs: Run[]): Run[] {
  return (["fcfs", "edd", "milp"] as Method[]).flatMap((method) => {
    const r = runs.find((r) => r.method === method);
    return r ? [r] : [];
  });
}
export function percentageReduction(base: number, next: number) {
  return base > 0 ? (100 * (base - next)) / base : null;
}
