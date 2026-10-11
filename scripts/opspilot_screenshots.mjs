// Capture existing calculated demonstration runs; this script queues no work.
import { chromium } from '../frontend/node_modules/playwright/index.mjs';
import { readFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
const receipt = JSON.parse(await readFile(join(root, 'docs/opspilot/demo-artifacts/receipt.json'), 'utf8'));
await mkdir(join(root, 'docs/opspilot/screenshots'), { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(process.env.OPSPILOT_BASE_URL ?? 'http://127.0.0.1:8000');
  if (await page.title() !== 'Production Scheduling Optimization System') throw new Error('Product title mismatch');
  await page.getByRole('link', { name: 'Production Scheduling Optimization System home', exact: true }).waitFor();
  await page.getByText('Web scheduling dashboard · Power BI data exports · Optional AI copilot extension', { exact: true }).waitFor();
  await page.getByLabel('Active dataset', { exact: true }).selectOption(receipt.dataset.id);
  await page.getByRole('button', { name: 'MILP', exact: true }).click();
  await page.getByText('Feasible · time limited', { exact: true }).first().waitFor();
  await page.getByTestId('gantt').waitFor();
  await page.screenshot({ path: join(root, 'docs/opspilot/screenshots/demo-overview.png'), fullPage: true });
  await page.getByRole('button', { name: 'Explain Weighted tardiness', exact: true }).click();
  await page.getByRole('dialog').waitFor();
  await page.screenshot({ path: join(root, 'docs/opspilot/screenshots/demo-metric-help.png'), fullPage: true });
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Manage datasets', exact: true }).click();
  await page.getByRole('dialog').getByLabel('Search datasets').fill(receipt.dataset.id.slice(0, 6));
  await page.screenshot({ path: join(root, 'docs/opspilot/screenshots/demo-dataset-library.png'), fullPage: true });
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Export', exact: true }).click();
  await page.getByLabel('Export scope', { exact: true }).selectOption('scenarios');
  await page.getByRole('dialog').locator('.export-runs > div').nth(5).waitFor();
  await page.screenshot({ path: join(root, 'docs/opspilot/screenshots/demo-power-bi-export.png'), fullPage: true });
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Comparison', exact: true }).click();
  await page.getByText(/CBC [0-9.]+:/).waitFor();
  await page.screenshot({ path: join(root, 'docs/opspilot/screenshots/demo-comparison.png'), fullPage: true });
  await page.getByRole('button', { name: 'Scenarios', exact: true }).click();
  await page.getByRole('heading', { name: '5 machines', exact: true }).waitFor();
  await page.screenshot({ path: join(root, 'docs/opspilot/screenshots/demo-scenario.png'), fullPage: true });
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('Saved actual 30-job demonstration screenshots.');
} finally {
  await browser.close();
}
