import type { Dataset } from "../api/client";

export function visibleDatasets(datasets: Dataset[], showTests: boolean) {
  return datasets.filter((d) => !d.is_archived && (showTests || !d.is_test));
}

export function datasetDescription(dataset: Dataset) {
  const profile = String(dataset.generator_params?.profile ?? "CSV");
  const machines = dataset.scenarios.find((s) => s.kind === "baseline")?.machine_count;
  const date = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(dataset.created_at));
  return `${dataset.name} · ${dataset.jobs.length} jobs / ${machines ?? "?"} machines · ${profile} · ${date} · ${dataset.id.slice(0, 6)}`;
}

export function datasetMatches(dataset: Dataset, query: string) {
  return `${datasetDescription(dataset)} ${dataset.source_kind} ${dataset.seed ?? ""}`
    .toLowerCase()
    .includes(query.trim().toLowerCase());
}
