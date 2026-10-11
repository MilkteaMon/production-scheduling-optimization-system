import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("planner workflow without an API key", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Production overview" })).toBeVisible();
  await page.getByRole("button", { name: "Load data", exact: true }).click();
  await page.getByLabel("Dataset name").fill(`Browser verification ${info.project.name}`);
  await page.getByLabel("Jobs", { exact: true }).fill("8");
  await page.getByLabel("Machines", { exact: true }).fill("3");
  await page.getByRole("button", { name: "Confirm and generate" }).click();
  await expect(page.getByTestId("gantt")).toBeVisible();
  await expect(page.getByText("Validated baseline", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Optimize schedule", exact: true }).click();
  await expect(page.getByText("Proven optimal", { exact: true }).first()).toBeVisible({
    timeout: 100000,
  });
  await page.getByRole("button", { name: "Comparison", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "One workload. Three scheduling methods." }),
  ).toBeVisible();
  await expect(page.getByText(/^CBC (?:[0-9.]+|version unavailable): Optimal; raw objective=/),).toBeVisible();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await page.getByRole("button", { name: "Simulate additional machine", exact: true }).click();
  await expect(page.getByRole("heading", { name: "4 machines", exact: true })).toBeVisible();
  await expect(page.getByText("Weighted tardiness reduction:", { exact: false })).toBeVisible({
    timeout: 100000,
  });
  await page.getByRole("button", { name: "AI copilot", exact: false }).click();
  await expect(page.getByRole("heading", { name: "AI is optional." })).toBeVisible();
  await page.getByRole("button", { name: "Close copilot" }).click();
  await page.getByRole("button", { name: "Data explorer", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Production jobs", exact: true })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export jobs", exact: true }).click();
  expect((await download).suggestedFilename()).toContain(
    "production-scheduling-optimization-system-jobs",
  );
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(
    accessibility.violations.map((v) => ({ id: v.id, targets: v.nodes.map((n) => n.target) })),
  ).toEqual([]);
  const screenshot = `../docs/opspilot/screenshots/${info.project.name}-overview.png`;
  await page.screenshot({ path: screenshot, fullPage: true });
  expect(errors).toEqual([]);
  const width = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.body).toBeLessThanOrEqual(width.viewport + 1);
});

test("CSV preview and explicit confirmation", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Load data", exact: true }).click();
  await page.getByRole("button", { name: "Upload CSV", exact: true }).click();
  await page.locator("input[type=file]").setInputFiles({
    name: "fixture.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "job_id,processing_time_min,release_time_min,due_time_min,priority_weight\nA,3,0,2,1\nB,2,0,2,3\n",
    ),
  });
  await expect(page.getByRole("button", { name: "Confirm import", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Validate and preview", exact: true }).click();
  await expect(
    page.getByText("2 valid jobs. Ready for your confirmation.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirm import", exact: true }).click();
  await expect(page.getByTestId("gantt")).toBeVisible();
});

test("dialogs contain keyboard focus and restore it", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Load data", exact: true });
  await trigger.click();
  await expect(page.getByRole("button", { name: "Close data dialog" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button", { name: "Confirm and generate" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Close data dialog" })).toBeFocused();
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(accessibility.violations.map((v) => v.id)).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("mocked copilot renders local evidence and deterministic completion cards", async ({
  page,
}) => {
  await page.route("**/api/v1/health", async (route) => {
    await route.fulfill({
      json: {
        status: "ok",
        database_available: true,
        solver_available: true,
        ai_available: true,
        ai_enabled: true,
        version: "0.1.0",
      },
    });
  });
  await page.route("**/api/v1/copilot/query", async (route) => {
    const context = route.request().postDataJSON();
    const run = await (await page.request.get(`/api/v1/runs/${context.run_id}`)).json();
    await route.fulfill({
      json: {
        query_id: "mock-ui",
        fallback: false,
        interpretation:
          "Lateness is calculated from the selected schedule, not a predictive probability.",
        facts: [
          {
            label: "Late jobs",
            value: String(run.metrics.late_jobs),
            unit: "jobs",
            evidence_id: "mock-E1",
          },
        ],
        tool_trace: [
          {
            evidence_id: "mock-E1",
            tool: "get_production_summary",
            data: { result: run },
            facts: [],
          },
        ],
        pending_run_ids: [run.id],
      },
    });
  });
  await page.goto("/");
  await expect(page.getByTestId("gantt")).toBeVisible();
  await page.getByRole("button", { name: "AI copilot", exact: false }).click();
  await page.getByRole("button", { name: "Which orders are late?", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Late jobs", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Weighted tardiness:", { exact: false })).toBeVisible();
  await dialog.getByRole("link", { name: "Evidence mock-E1", exact: true }).click();
  await expect(page.locator("#evidence-mock-E1")).toBeVisible();
});
