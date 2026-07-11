/** E2E smoke (charter M7 flow, first segment): register → add company →
 * working-company selection → calendar empty state. Runs against the real
 * stack: vite dev server → FastAPI → Postgres + Redis. */
import { expect, test } from "@playwright/test";

const stamp = Date.now();
const FIRM_EMAIL = `e2e-${stamp}@example.com`;
const COMPANY_NAME = `E2E Fixture ${stamp} Pvt Ltd`;
const CIN = `U74999MH2020PTC${String(stamp).slice(-6)}`;

test("register firm, add company, see calendar shell", async ({ page }) => {
  await page.goto("/login");

  // register a fresh firm (first user = Partner)
  await page.getByRole("button", { name: "New firm? Register" }).click();
  await page.locator('input[name="firm_name"]').fill("E2E Test Firm");
  await page.locator('input[name="email"]').fill(FIRM_EMAIL);
  await page.locator('input[name="password"]').fill("a-strong-password-123");
  await page.getByRole("button", { name: "Create firm" }).click();

  // lands on companies, empty state
  await expect(page.getByText("No companies yet")).toBeVisible();

  // add a company inline
  await page.getByRole("button", { name: "Add company" }).click();
  await page.locator('input[name="cin"]').fill(CIN);
  await page.locator('input[name="name"]').fill(COMPANY_NAME);
  await page.locator('input[name="agm_date"]').fill("2026-09-30");
  await page.getByRole("button", { name: "Save company" }).click();
  await expect(page.getByRole("cell", { name: COMPANY_NAME })).toBeVisible();

  // working-company selector scopes the calendar (PRD §3)
  await page.locator("select").first().selectOption({ label: COMPANY_NAME });
  await page.getByRole("link", { name: "Compliance Calendar" }).click();
  await expect(page.getByText(`Compliance calendar — ${COMPANY_NAME}`)).toBeVisible();

  // generate: empty until a signed rules dataset is loaded — honest empty state
  await page.getByRole("button", { name: "Generate / refresh" }).click();
  await expect(page.getByText("rows appear once the signed rules dataset is loaded")).toBeVisible();

  // documents page shows the unstamped template registry
  await page.getByRole("link", { name: "Documents" }).click();
  await expect(page.getByText("validation stamps are enforced", { exact: false })).toBeVisible();
});
