import { describe, expect, it } from "vitest";
import type { Dataset, Run } from "../api/client";
import { visibleDatasets, datasetDescription, datasetMatches } from "./datasets";
import { comparisonExplanation } from "./comparisons";

const dataset = (overrides: Partial<Dataset> = {}) =>
  ({
    id: "abcdef-123",
    name: "Production",
    is_test: false,
    is_archived: false,
    created_at: "2026-10-12T00:00:00Z",
    source_kind: "synthetic",
    seed: 42,
    generator_params: { profile: "tight" },
    jobs: [{ job_id: "A" }],
    scenarios: [],
    ...overrides,
  }) as Dataset;
const run = (overrides: Partial<Run> = {}) =>
  ({
    id: "base",
    method: "fcfs",
    proven_optimal: false,
    solver_status: "not_run",
    metrics: { total_weighted_tardiness: 8866, late_jobs: 15, makespan_min: 356 },
    ...overrides,
  }) as Run;

describe("workload library", () => {
  it("hides test and archived records while preserving them for management", () => {
    const normal = dataset(),
      test = dataset({ id: "test", is_test: true }),
      archived = dataset({ id: "archived", is_archived: true });
    expect(visibleDatasets([normal, test, archived], false)).toEqual([normal]);
    expect(visibleDatasets([normal, test, archived], true)).toEqual([normal, test]);
  });
  it("distinguishes same-name workloads and searches profile, seed and ID", () => {
    const first = dataset(),
      second = dataset({ id: "xyz-123" });
    expect(datasetDescription(first)).not.toBe(datasetDescription(second));
    expect(datasetMatches(first, "TIGHT")).toBe(true);
    expect(datasetMatches(first, "42")).toBe(true);
    expect(datasetMatches(first, "abcdef")).toBe(true);
    expect(datasetMatches(first, "missing")).toBe(false);
  });
});

describe("calculated comparison explanations", () => {
  it("reports objective improvement together with worse count/span and unresolved optimality", () => {
    const result = comparisonExplanation(
      run(),
      run({
        id: "next",
        method: "milp",
        solver_status: "time_limit",
        metrics: {
          total_weighted_tardiness: 6072,
          late_jobs: 18,
          makespan_min: 424,
        } as Run["metrics"],
      }),
    );
    expect(result?.objective).toContain("31.5% reduction");
    expect(result?.tradeoffs).toBe("Late-job count increases by 3; makespan increases by 68 min.");
    expect(result?.status).toContain("optimality remains unresolved");
  });
  it("preserves N/A for a zero baseline and describes deterioration", () => {
    const result = comparisonExplanation(
      run({
        metrics: { total_weighted_tardiness: 0, late_jobs: 0, makespan_min: 10 } as Run["metrics"],
      }),
      run({
        id: "next",
        method: "edd",
        metrics: { total_weighted_tardiness: 5, late_jobs: 1, makespan_min: 12 } as Run["metrics"],
      }),
    );
    expect(result?.objective).toContain("increases by 5");
    expect(result?.objective).toContain("percentage reduction N/A");
    expect(result?.objective).not.toContain("Infinity");
  });
  it("states a validated optimum only with the explicit proven flag", () => {
    const result = comparisonExplanation(
      run(),
      run({ id: "next", method: "milp", proven_optimal: true, solver_status: "optimal" }),
    );
    expect(result?.status).toBe("CBC established optimality and the schedule validates.");
    expect(comparisonExplanation(run({ metrics: null }), run())).toBeNull();
  });
});
