import { describe, it, expect } from "vitest";
import { percentageReduction, percent, fmt, latestMethods, type Run } from "./client";
describe("comparisons and formatting", () => {
  it("does not divide by a zero baseline", () => {
    expect(percentageReduction(0, 1)).toBeNull();
    expect(percent(null)).toBe("N/A");
  });
  it("calculates actual reductions and negative changes", () => {
    expect(percentageReduction(100, 70)).toBe(30);
    expect(percentageReduction(10, 20)).toBe(-100);
    expect(fmt(null)).toBe("—");
  });
  it("selects latest runs in explicit method order", () => {
    const runs = [
      { id: "new", method: "edd" },
      { id: "old", method: "edd" },
      { id: "fcfs", method: "fcfs" },
    ] as Run[];
    expect(latestMethods(runs).map((r) => r.id)).toEqual(["fcfs", "new"]);
  });
});
