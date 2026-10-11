import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import type { Dataset, Run, Scenario } from "../src/api/client";

async function fixture(page: Page, name: string) {
  const response = await page.request.post("/api/v1/datasets/import", {
    multipart: {
      name,
      machine_count: "1",
      confirmed: "true",
      file: {
        name: "priority.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          "job_id,processing_time_min,release_time_min,due_time_min,priority_weight\n001,3,0,2,1\n002,2,0,2,3\n",
        ),
      },
    },
  });
  expect(response.status()).toBe(201);
  const dataset = (await response.json()) as Dataset;
  const baseline = dataset.scenarios.find((s) => s.kind === "baseline")!;
  await expect
    .poll(async () => {
      const runs = (await (
        await page.request.get(`/api/v1/scenarios/${baseline.id}/runs`)
      ).json()) as Run[];
      return runs.filter((r) => r.has_valid_schedule).length;
    })
    .toBe(2);
  return { dataset, baseline };
}

async function optimize(page: Page, scenario: Scenario, methods = ["milp"]) {
  const response = await page.request.post(`/api/v1/scenarios/${scenario.id}/runs`, {
    data: { methods, time_limit_seconds: 10 },
  });
  expect(response.status()).toBe(202);
  const { run_ids } = await response.json();
  await expect
    .poll(
      async () => {
        const runs = await Promise.all(
          run_ids.map(
            async (id: string) =>
              (await (await page.request.get(`/api/v1/runs/${id}`)).json()) as Run,
          ),
        );
        return runs.every((run) => run.has_valid_schedule && run.execution_state === "completed");
      },
      { timeout: 30000 },
    )
    .toBe(true);
  return run_ids[0] as string;
}

async function noAccessibilityErrors(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(
    result.violations.map((v) => ({ id: v.id, targets: v.nodes.map((n) => n.target) })),
  ).toEqual([]);
}

test("dataset library hides tests, searches, archives, restores and remembers context", async ({
  page,
}, info) => {
  const { dataset, baseline } = await fixture(page, `Library workload ${info.project.name}`);
  const hidden = await fixture(page, `Browser verification hidden ${info.project.name}`);
  const extra = (await (
    await page.request.post(`/api/v1/datasets/${dataset.id}/scenarios`)
  ).json()) as Scenario;
  await optimize(page, extra);
  await page.goto("/");
  const selection = page.getByLabel("Active dataset", { exact: true });
  await selection.selectOption(dataset.id);
  await expect(selection.locator(`option[value="${hidden.dataset.id}"]`)).toHaveCount(0);
  await page.getByLabel("Active scenario", { exact: true }).selectOption(extra.id);
  await page.getByRole("button", { name: "MILP", exact: true }).click();
  await expect(page.getByText("Proven optimal", { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(selection).toHaveValue(dataset.id);
  await expect(page.getByLabel("Active scenario", { exact: true })).toHaveValue(extra.id);
  await expect(page.getByRole("button", { name: "MILP", exact: true })).toHaveClass(/selected/);
  await page.getByRole("button", { name: "Manage datasets", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Search datasets").fill(hidden.dataset.id.slice(0, 6));
  await expect(dialog.getByText("No matching datasets.", { exact: false })).toBeVisible();
  await dialog.getByLabel("Show test data", { exact: true }).check();
  await expect(dialog.getByText(hidden.dataset.name, { exact: true })).toBeVisible();
  await dialog.getByLabel("Show test data", { exact: true }).uncheck();
  await dialog.getByLabel("Search datasets").fill(dataset.id.slice(0, 6));
  await noAccessibilityErrors(page);
  await dialog
    .getByRole("button", {
      name: `Archive dataset ${dataset.name} ${dataset.id.slice(0, 6)}`,
      exact: true,
    })
    .click();
  await expect(dialog.getByText("No matching datasets.", { exact: false })).toBeVisible();
  await dialog.getByLabel("Show archived", { exact: true }).check();
  await expect(
    dialog.getByRole("button", {
      name: `Use dataset ${dataset.name} ${dataset.id.slice(0, 6)}`,
      exact: true,
    }),
  ).toBeDisabled();
  await dialog
    .getByRole("button", {
      name: `Restore dataset ${dataset.name} ${dataset.id.slice(0, 6)}`,
      exact: true,
    })
    .click();
  await dialog
    .getByRole("button", {
      name: `Use dataset ${dataset.name} ${dataset.id.slice(0, 6)}`,
      exact: true,
    })
    .click();
  await expect(selection).toHaveValue(dataset.id);
  const saved = (await (
    await page.request.get(`/api/v1/datasets/${dataset.id}`)
  ).json()) as Dataset;
  expect(saved.jobs).toEqual(dataset.jobs);
  expect(saved.job_hash).toBe(dataset.job_hash);
  expect(saved.is_archived).toBe(false);
  expect(saved.scenarios.some((s) => s.id === baseline.id)).toBe(true);
});

test("Power BI downloads contain exactly the displayed run scope and coherent tables", async ({
  page,
}, info) => {
  const { dataset, baseline } = await fixture(page, `BI workload ${info.project.name}`);
  const milp = await optimize(page, baseline);
  const extra = (await (
    await page.request.post(`/api/v1/datasets/${dataset.id}/scenarios`)
  ).json()) as Scenario;
  await optimize(page, extra, ["fcfs", "edd", "milp"]);
  await page.goto("/");
  await page.getByLabel("Active dataset", { exact: true }).selectOption(dataset.id);
  await page.getByRole("button", { name: "MILP", exact: true }).click();
  await expect(page.getByText("Proven optimal", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await noAccessibilityErrors(page);
  const python = resolve(
    import.meta.dirname,
    "../../backend/.venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  for (const [mode, count] of [
    ["current", 1],
    ["methods", 3],
    ["scenarios", 6],
  ] as const) {
    await dialog.getByLabel("Export scope", { exact: true }).selectOption(mode);
    await expect(dialog.locator(".export-runs > div")).toHaveCount(count);
    const downloaded = page.waitForEvent("download");
    await dialog.getByRole("button", { name: "Download Power BI package", exact: true }).click();
    const download = await downloaded;
    expect(download.suggestedFilename()).toBe(
      `production-scheduling-optimization-system-power-bi-${mode}.zip`,
    );
    const path = info.outputPath(`${mode}.zip`);
    await download.saveAs(path);
    const inspection = JSON.parse(
      execFileSync(
        python,
        [
          "-c",
          [
            "import sys, zipfile, json, csv, io",
            "with zipfile.ZipFile(sys.argv[1]) as z:",
            " m=json.loads(z.read('manifest.json'))",
            " tables={t:list(csv.DictReader(io.StringIO(z.read(t+'.csv').decode('utf-8')))) for t in ['jobs','schedule','machines','kpis']}",
            " print(json.dumps({'files':z.namelist(), 'manifest':m, 'tables':tables}))",
          ].join("\n"),
          path,
        ],
        { encoding: "utf8" },
      ),
    );
    expect(inspection.files).toHaveLength(8);
    expect(inspection.manifest.job_hash).toBe(dataset.job_hash);
    expect(inspection.manifest.runs).toHaveLength(count);
    expect(inspection.tables.jobs.map((j: { job_id: string }) => j.job_id)).toEqual(["001", "002"]);
    expect(inspection.tables.schedule).toHaveLength(2 * count);
    expect(inspection.tables.kpis).toHaveLength(count);
    const ids = inspection.manifest.runs.map((r: { id: string }) => r.id) as string[];
    expect(new Set(inspection.tables.schedule.map((r: { run_id: string }) => r.run_id))).toEqual(
      new Set(ids),
    );
    if (mode === "current") expect(ids).toEqual([milp]);
    if (mode === "scenarios")
      expect(new Set(inspection.manifest.runs.map((r: Run) => r.metrics?.machine_count))).toEqual(
        new Set([1, 2]),
      );
  }
});

test("metric help explains actual denominators and comparison tradeoffs with keyboard access", async ({
  page,
}, info) => {
  const { dataset, baseline } = await fixture(page, `Metric workload ${info.project.name}`);
  await optimize(page, baseline);
  await page.goto("/");
  await page.getByLabel("Active dataset", { exact: true }).selectOption(dataset.id);
  await page.getByRole("button", { name: "MILP", exact: true }).click();
  await expect(page.getByText("Proven optimal", { exact: true }).first()).toBeVisible();
  const trigger = page.getByRole("button", { name: "Explain Weighted tardiness", exact: true });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("Σ weight × max(0, completion − due)", { exact: true }),
  ).toBeVisible();
  await expect(dialog.getByText("2 jobs · 1 late · 3 weighted min", { exact: true })).toBeVisible();
  await expect(
    dialog.getByText("Planning window H: 5 min · Makespan: 5 min", { exact: true }),
  ).toBeVisible();
  await noAccessibilityErrors(page);
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await page.getByRole("button", { name: "Comparison", exact: true }).click();
  const explanation = page
    .locator(".comparison-explanation article")
    .filter({ has: page.getByRole("heading", { name: "MILP compared with FCFS", exact: true }) });
  await expect(
    explanation.getByText("Weighted tardiness decreases by 7 weighted min (70% reduction).", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    explanation.getByText("Late-job count decreases by 1; makespan is unchanged.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Explain Fixed-window utilization", exact: true }).click();
  await expect(dialog.getByText(/same jobs on the same machines cannot change/)).toBeVisible();
  await page.keyboard.press("Escape");
  const width = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.body).toBeLessThanOrEqual(width.viewport + 1);
});
