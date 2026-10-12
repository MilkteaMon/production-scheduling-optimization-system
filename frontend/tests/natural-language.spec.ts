import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const completeDraft = {
  machine_count: 2,
  time_basis: "minutes_from_start",
  jobs: [
    {
      label: "A",
      job_id: "A",
      processing_time_min: 40,
      release_time_min: 0,
      due_time_min: 90,
      priority_weight: null,
      must_finish_on_time: true,
    },
    {
      label: "B",
      job_id: "B",
      processing_time_min: 20,
      release_time_min: 0,
      due_time_min: 60,
      priority_weight: null,
      must_finish_on_time: false,
    },
  ],
  clarifications: [],
  unsupported_requirements: [],
};

test.beforeEach(async ({ page }) => {
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
});

test("describe, edit and explicitly confirm a new workload with actual scheduling", async ({
  page,
}, info) => {
  let calls = 0;
  await page.route("**/api/v1/natural-language/parse", async (route) => {
    calls++;
    const response = await page.request.post("/api/v1/natural-language/review", {
      data: { description: route.request().postDataJSON().description, draft: completeDraft },
    });
    await route.fulfill({ json: await response.json() });
  });
  const before = (await (await page.request.get("/api/v1/datasets")).json()).length;
  await page.goto("/");
  await page.getByRole("button", { name: "Describe workload", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await page.getByRole("button", { name: "Use complete example" }).click();
  await page.getByRole("button", { name: "Interpret description", exact: true }).click();
  await expect(dialog.getByText("Ready for your confirmation")).toBeVisible();
  expect((await (await page.request.get("/api/v1/datasets")).json()).length).toBe(before);
  await expect(page.getByRole("button", { name: "Confirm and create plan" })).toBeDisabled();
  await expect(page.getByLabel("Order 1 must finish on time")).toBeChecked();
  await page.getByLabel("Order 1 processing_time_min").fill("45");
  await expect(
    dialog.getByText("The draft changed. Check it again before confirming."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Check edited draft" }).click();
  await expect(dialog.getByText("Ready for your confirmation")).toBeVisible();
  await page.getByLabel("Described workload name").fill(`Natural description ${info.project.name}`);
  const accessibility = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(accessibility.violations.map((v) => v.id)).toEqual([]);
  await page.screenshot({
    path: `../runtime/description-review-${info.project.name}.png`,
    fullPage: true,
  });
  const width = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: innerWidth,
  }));
  expect(width.body).toBeLessThanOrEqual(width.viewport + 1);
  await page.getByLabel("Approve workload draft").check();
  await page.getByRole("button", { name: "Confirm and create plan" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("Proven optimal", { exact: true }).first()).toBeVisible({
    timeout: 60000,
  });
  const datasets = await (await page.request.get("/api/v1/datasets")).json();
  expect(datasets.length).toBe(before + 1);
  const created = datasets.find(
    (d: { name: string }) => d.name === `Natural description ${info.project.name}`,
  );
  expect(created.jobs[0].processing_time_min).toBe(45);
  expect(created.scenarios[0].must_finish_job_ids).toEqual(["A"]);
  expect(calls).toBe(1);
});

test("missing due times are followed up before confirmation without creating records", async ({
  page,
}) => {
  let calls = 0;
  await page.route("**/api/v1/natural-language/parse", async (route) => {
    calls++;
    const description = route.request().postDataJSON().description;
    const draft = description.includes("Supplement:")
      ? completeDraft
      : { ...completeDraft, jobs: completeDraft.jobs.map((j) => ({ ...j, due_time_min: null })) };
    const response = await page.request.post("/api/v1/natural-language/review", {
      data: { description, draft },
    });
    await route.fulfill({ json: await response.json() });
  });
  const before = (await (await page.request.get("/api/v1/datasets")).json()).length;
  await page.goto("/");
  await page.getByRole("button", { name: "Describe workload", exact: true }).click();
  await page.getByRole("button", { name: "Use incomplete example" }).click();
  await page.getByRole("button", { name: "Interpret description", exact: true }).click();
  await expect(page.getByText("More information is needed", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Order 1 due_time_min")).toHaveValue("");
  await expect(page.getByLabel("Approve workload draft")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Confirm and create plan" })).toBeDisabled();
  await page
    .getByLabel("Additional workload details")
    .fill("A 在 90 分钟内交付，B 在 60 分钟内交付。两个订单现在可开工。A 必须准时完成。");
  await page.getByRole("button", { name: "Add details and re-interpret" }).click();
  await expect(page.getByText("Ready for your confirmation", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Order 1 due_time_min")).toHaveValue("90");
  expect(calls).toBe(2);
  expect((await (await page.request.get("/api/v1/datasets")).json()).length).toBe(before);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
});

test("unsupported calendar and machine requirements block creation", async ({ page }) => {
  await page.route("**/api/v1/natural-language/parse", async (route) => {
    const description = route.request().postDataJSON().description;
    const draft = {
      ...completeDraft,
      time_basis: "needs_clarification",
      clarifications: ["请提供从排程起点算起的交期分钟数。"],
      unsupported_requirements: ["不同机器具有不同加工能力。"],
    };
    const response = await page.request.post("/api/v1/natural-language/review", {
      data: { description, draft },
    });
    await route.fulfill({ json: await response.json() });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Describe workload", exact: true }).click();
  await page.getByLabel("Workload description").fill("订单 A 明天下午交付，只有机器 1 能加工。");
  await page.getByRole("button", { name: "Interpret description", exact: true }).click();
  await expect(page.getByText("Requirements outside this scheduling model")).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm and create plan" })).toBeDisabled();
  await page.getByRole("button", { name: "Close description" }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Workload description")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Describe workload", exact: true })).toBeFocused();
});
