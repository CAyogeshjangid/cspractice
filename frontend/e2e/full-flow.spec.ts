/** The charter M7 flow, end to end in a real browser:
 * register → invite → import → calendar → remind → generate.
 * Requires `python scripts/seed_e2e.py` (TEST-ONLY rules, test-stamped
 * templates, portfolio fixture) against the e2e database. */
import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const FIXTURES = fileURLToPath(new URL("./fixtures", import.meta.url));

const stamp = Date.now();
const PARTNER = `flow-partner-${stamp}@example.com`;
const MANAGER = `flow-manager-${stamp}@example.com`;
const PASSWORD = "a-strong-password-123";

test("register → invite → import → calendar → remind → generate", async ({ page }) => {
  // ---- register (first user = Partner)
  await page.goto("/login");
  await page.getByRole("button", { name: "New firm? Register" }).click();
  await page.locator('input[name="firm_name"]').fill(`Dogfood Firm ${stamp}`);
  await page.locator('input[name="email"]').fill(PARTNER);
  await page.locator('input[name="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: "Create firm" }).click();
  await expect(page.getByText("No companies yet")).toBeVisible();

  // ---- invite a manager, capture the one-time accept link
  await page.getByRole("link", { name: "Team & Settings" }).click();
  await page.locator('input[name="email"]').first().fill(MANAGER);
  // the role select defaults to "executive" — pick manager explicitly.
  // (Left on the default, the flow 403s later at the reminders PUT: the RBAC
  // matrix correctly blocks Executives from editing unassigned rows.)
  await page.locator("select").nth(1).selectOption("manager");
  await page.getByRole("button", { name: "Invite", exact: true }).click();
  const linkText = await page.locator("code").first().textContent();
  const acceptUrl = linkText!.trim();
  expect(acceptUrl).toContain("/accept?token=");

  // ---- DSC expiry reminder policy (Partner-only firm setting) — set it now
  // while logged in as the partner, then reload to prove the roundtrip.
  await page.locator('input[name="days_before"]').fill("30, 7");
  await page.locator('input[name="recipients"]').fill("compliance@firm.example");
  await page.getByRole("button", { name: "Save DSC reminder policy" }).click();
  await page.reload();
  await expect(page.locator('input[name="days_before"]')).toHaveValue("30, 7");

  // ---- accept as the manager (fresh session)
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto(acceptUrl);
  await page.locator('input[name="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: "Join firm" }).click();
  await expect(page.getByText("No companies yet")).toBeVisible();

  // ---- import the portfolio from Excel (all-or-nothing importer)
  await page
    .locator('input[type="file"]')
    .setInputFiles(`${FIXTURES}/portfolio.xlsx`);
  await expect(page.getByText(/Imported: 3 created/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "Alpha Textiles Pvt Ltd" })).toBeVisible();

  // ---- per-master import: directors from Excel on the company detail tab
  await page
    .locator("tr", { hasText: "Alpha Textiles Pvt Ltd" })
    .getByRole("link", { name: /Open/ })
    .click();
  // wait for the detail page — grabbing the file input mid-navigation can hit
  // the companies page's (detaching) input and the upload silently no-ops
  await expect(page.getByRole("heading", { name: "Alpha Textiles Pvt Ltd" })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles(`${FIXTURES}/directors.xlsx`);
  await expect(page.getByText(/Imported: 2 created, 0 already present/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "Asha Mehta" })).toBeVisible();
  // re-import of the same file is idempotent — skipped, never duplicated
  await page.locator('input[type="file"]').setInputFiles(`${FIXTURES}/directors.xlsx`);
  await expect(page.getByText(/Imported: 0 created, 2 already present/)).toBeVisible();

  // ---- disclosures: record an MBP-1 receipt for a director, per FY
  await page
    .locator("tr", { hasText: "Asha Mehta" })
    .getByRole("button", { name: "Disclosures" })
    .click();
  await page.locator('input[name="mbp1_received"]').fill("2026-04-15");
  await page.getByRole("button", { name: "Save disclosures" }).click();
  await expect(page.getByText("2026-04-15")).toBeVisible(); // history badge
  await expect(page.getByText("pending").first()).toBeVisible(); // DIR-8 / DIR-2 outstanding

  // ---- taxonomy tagging: create a professional group inline, tag the company
  await page.getByRole("button", { name: "Edit company" }).click();
  page.once("dialog", (d) => void d.accept("Audit clients"));
  await page.getByRole("button", { name: "+", exact: true }).first().click();
  await expect(page.locator('select[name="professional_group_id"]')).toHaveValue(/.+/);
  await page.getByRole("button", { name: "Save changes" }).click();
  // the tag round-trips: reopen the form and the select shows the saved group
  await page.getByRole("button", { name: "Edit company" }).click();
  await expect(
    page.locator('select[name="professional_group_id"] option:checked'),
  ).toHaveText("Audit clients");
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await page.getByRole("link", { name: "Companies" }).click();

  // ---- calendar: generate from the TEST-ONLY ruleset
  await page.locator("select").first().selectOption({ label: "Alpha Textiles Pvt Ltd" });
  await page.getByRole("link", { name: "Compliance Calendar" }).click();
  // the fixture AGM (30 Sep 2026) belongs to FY 2025-26 → select FY 2026
  await page.locator('input[type="number"]').first().fill("2026");
  await page.getByRole("button", { name: "Generate / refresh" }).click();
  await expect(page.getByText("[TEST] File within 30 days of AGM")).toBeVisible();
  await expect(page.getByRole("cell", { name: "2026-10-30" })).toBeVisible(); // AGM + 30d

  // the turnover-gated rule lands flagged — the review queue works
  await expect(page.getByText("applicability_unknown").first()).toBeVisible();
  await page.getByRole("button", { name: /Review queue \(\d+\)/ }).click();
  await expect(page.getByText("[TEST] Turnover-gated obligation")).toBeVisible();
  await page.getByRole("button", { name: "All rows" }).click();

  // ---- remind: configure days-before on the AGM row
  await page
    .locator("tr", { hasText: "[TEST] File within 30 days of AGM" })
    .getByRole("button", { name: "Edit" })
    .click();
  await page.locator('input[name="days_before"]').fill("30, 7");
  await page.locator('input[name="extra_emails"]').fill("ops@example.com");
  await page.getByRole("button", { name: "Save reminders" }).click();
  await expect(page.getByRole("button", { name: "Save reminders" })).toBeHidden();

  // ---- generate: AGM Notice through the (test-)stamped template
  await page.getByRole("link", { name: "Documents" }).click();
  await page.locator('input[name="meeting_time"]').fill("11:00 AM");
  await page.locator('input[name="venue"]').fill("Registered Office");
  await page.locator('textarea[name="ordinary_business"]').fill("Adopt the accounts.");
  await page.locator('input[name="signatory_name"]').fill("R. Sharma");
  await page.locator('input[name="signatory_designation"]').fill("CS");
  await page.locator('input[name="place"]').fill("Mumbai");
  const popup = page.waitForEvent("popup").catch(() => null); // download tab
  await page.getByRole("button", { name: "Generate .docx" }).click();
  await popup;
  await expect(
    page.locator("tr", { hasText: "AGM Notice" }).getByRole("link", { name: "Download" }),
  ).toBeVisible();

  // ---- audit trail shows the whole session (manager can view)
  await page.getByRole("link", { name: "Activity Log" }).click();
  await expect(page.getByText("import_create").first()).toBeVisible();
  await expect(page.getByText("generate").first()).toBeVisible();
});
