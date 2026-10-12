import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { Dataset, Run } from "../src/api/client";

async function workload(page: import("@playwright/test").Page, name: string, impossible = false) {
  const csv =
    "job_id,processing_time_min,release_time_min,due_time_min,priority_weight\n" +
    (impossible ? "A,2,0,2,1\nB,2,0,2,1\n" : "A,10,0,100,1\nB,1,1,2,10\n");
  const response = await page.request.post("/api/v1/datasets/import", {
    multipart: {
      name,
      machine_count: "1",
      confirmed: "true",
      file: { name: "rules.csv", mimeType: "text/csv", buffer: Buffer.from(csv) },
    },
  });
  expect(response.status()).toBe(201);
  const dataset = (await response.json()) as Dataset;
  const base = dataset.scenarios[0];
  await expect
    .poll(
      async () =>
        (
          (await (await page.request.get(`/api/v1/scenarios/${base.id}/runs`)).json()) as Run[]
        ).filter((r) => r.has_valid_schedule).length,
    )
    .toBe(2);
  await page.goto("/");
  await page.getByLabel("Active dataset", { exact: true }).selectOption(dataset.id);
  return dataset;
}

test("hard deadlines preview, confirmed scenario and order-level explanation without AI", async ({
  page,
}, info) => {
  const dataset = await workload(page, `Hard deadline UI ${info.project.name}`);
  const base = dataset.scenarios[0];
  const initial = (await (
    await page.request.get(`/api/v1/scenarios/${base.id}/runs`)
  ).json()) as Run[];
  await page.getByRole("button", { name: "Plan commitments / What-if", exact: true }).click();
  await page.getByLabel("Require B on time", { exact: true }).check();
  await page.getByRole("button", { name: "Preview rules", exact: true }).click();
  await expect(
    page.getByText("B: must complete by 2 min; earliest possible completion 2 min.", {
      exact: true,
    }),
  ).toBeVisible();
  const unchanged = (await (
    await page.request.get(`/api/v1/datasets/${dataset.id}`)
  ).json()) as Dataset;
  expect(unchanged.scenarios).toHaveLength(1);
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(accessibility.violations.map((v) => v.id)).toEqual([]);
  await page.getByRole("button", { name: "Confirm and calculate scenario", exact: true }).click();
  const row = page
    .locator(".scenario-workbench")
    .getByRole("row")
    .filter({ hasText: "1 machines · 1 hard deadlines" })
    .filter({ hasText: "MILP" });
  await expect(row.getByText("Proven optimal", { exact: true })).toBeVisible({ timeout: 30000 });
  await row.getByRole("button", { name: "Explain MILP", exact: true }).click();
  await page
    .getByLabel("Explanation baseline", { exact: true })
    .selectOption(initial.find((r) => r.method === "fcfs")!.id);
  await expect(page.getByText(/Weighted tardiness reduction: 90 weighted min/)).toBeVisible();
  await expect(
    page.locator(".run-explanation").getByRole("row").filter({ hasText: "B · hard" }),
  ).toContainText("90");
  await page.getByRole("button", { name: "Plan commitments / What-if", exact: true }).click();
  await expect(page.getByLabel("Require B on time", { exact: true })).toBeChecked();
  await expect(page.getByLabel("Require B on time", { exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: /Add one identical machine/ }).check();
  await page.getByRole("button", { name: "Preview rules", exact: true }).click();
  await page.getByRole("button", { name: "Confirm and calculate scenario", exact: true }).click();
  await expect(
    page
      .locator(".scenario-workbench")
      .getByRole("row")
      .filter({ hasText: "2 machines · 1 hard deadlines" })
      .filter({ hasText: "MILP" })
      .getByText("Proven optimal", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.locator(".scenario-workbench .table-scroll").evaluate((element) => {
    element.scrollLeft = 0;
  });
  await page.screenshot({
    path: `../runtime/planning-proof-${info.project.name}.png`,
    fullPage: true,
  });
  const width = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.body).toBeLessThanOrEqual(width.viewport + 1);
});

test("infeasible hard deadline scenario is labelled and never displays a fake optimum", async ({
  page,
}, info) => {
  await workload(page, `Impossible UI ${info.project.name}`, true);
  await page.getByRole("button", { name: "Plan commitments / What-if", exact: true }).click();
  await page.getByLabel("Require A on time", { exact: true }).check();
  await page.getByLabel("Require B on time", { exact: true }).check();
  await page.getByRole("button", { name: "Preview rules", exact: true }).click();
  await page.getByRole("button", { name: "Confirm and calculate scenario", exact: true }).click();
  const row = page
    .locator(".scenario-workbench")
    .getByRole("row")
    .filter({ hasText: "1 machines · 2 hard deadlines" })
    .filter({ hasText: "MILP" });
  await expect(row.getByText("Infeasible", { exact: true })).toBeVisible({ timeout: 30000 });
  await row.getByRole("button", { name: "Explain MILP", exact: true }).click();
  await expect(
    page.getByText("No schedule can meet all selected hard deadlines under these conditions.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(row.getByText("Proven optimal", { exact: true })).toHaveCount(0);
});

test("mocked copilot proposes exact deadlines and waits for human confirmation", async ({
  page,
}, info) => {
  const dataset = await workload(page, `Copilot rule UI ${info.project.name}`);
  const scenario = dataset.scenarios[0];
  await page.route("**/api/v1/health", (route) =>
    route.fulfill({
      json: {
        status: "ok",
        database_available: true,
        solver_available: true,
        ai_available: true,
        ai_enabled: true,
        ai_provider: "codex_subscription",
        ai_model: "gpt-6.1-sol",
        ai_reasoning_effort: "low",
        version: "0.1.0",
      },
    }),
  );
  await page.route("**/api/v1/copilot/query", async (route) => {
    const proposal = await (
      await page.request.post(`/api/v1/scenarios/${scenario.id}/rules/preview`, {
        data: { job_ids: ["B"] },
      })
    ).json();
    await route.fulfill({
      json: {
        query_id: "mock-rule",
        facts: [],
        interpretation: "Review the proposed hard deadlines.",
        tool_trace: [],
        pending_run_ids: [],
        fallback: false,
        proposal,
      },
    });
  });
  await page.reload();
  await page
    .getByRole("button", { name: /AI copilot/ })
    .first()
    .click();
  await page.getByLabel("Ask operations copilot").fill("B必须按时完成");
  await expect(page.getByText("GPT-6.1 Sol · Low reasoning")).toBeVisible();
  await expect(page.getByText("Connected through your local ChatGPT subscription.")).toBeVisible();
  await page.getByRole("button", { name: "Send question", exact: true }).click();
  await expect(page.getByText("Scenario proposal — awaiting confirmation")).toBeVisible();
  expect(
    ((await (await page.request.get(`/api/v1/datasets/${dataset.id}`)).json()) as Dataset)
      .scenarios,
  ).toHaveLength(1);
  await page.getByRole("button", { name: "Review proposed scenario", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(page.getByLabel("Require B on time", { exact: true })).toBeChecked();
  await page.getByRole("button", { name: "Confirm and calculate scenario", exact: true }).click();
  await expect(
    page
      .locator(".scenario-workbench")
      .getByRole("row")
      .filter({ hasText: "1 machines · 1 hard deadlines" })
      .filter({ hasText: "MILP" })
      .getByText("Proven optimal", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
});
