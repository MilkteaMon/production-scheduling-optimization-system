import type { Run } from "../api/client";
import { comparisonExplanation } from "../data/comparisons";

export default function ComparisonExplanation({ runs }: { runs: Run[] }) {
  const baseline = runs.find((r) => r.method === "fcfs");
  if (!baseline) return null;
  const explanations = runs
    .filter((r) => r.id !== baseline.id)
    .map((r) => comparisonExplanation(baseline, r))
    .filter((r) => r !== null);
  if (!explanations.length) return null;
  return (
    <section className="panel comparison-explanation">
      <h2>What changed?</h2>
      <p>
        Calculated from the selected compatible runs. Weighted tardiness is the optimization
        objective.
      </p>
      <div className="explanation-grid">
        {explanations.map((e) => (
          <article key={e.title}>
            <h3>{e.title}</h3>
            <p>{e.objective}</p>
            <p>{e.tradeoffs}</p>
            <p className="export-hint">{e.status}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
