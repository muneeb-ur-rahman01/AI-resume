import { expect, test, type Browser, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Full vertical-slice journey through the real UI:
 * candidate + employer registration and email verification (via Mailpit), company verification by an admin,
 * job publishing, resume upload and fact review, recommendations with explanation, cover-letter drafting,
 * candidate-approved submission, employer review and status change, candidate status tracking, data export
 * and account deletion.
 *
 * Requires: E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD for an admin created with `python -m careerpilot.cli create-admin`.
 */

const MAILPIT = process.env.MAILPIT_URL ?? "http://127.0.0.1:8025";
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
const PASSWORD = "e2e correct horse battery";
const run = Date.now().toString(36);
const here = path.dirname(fileURLToPath(import.meta.url));
// Set SCREENSHOT_DIR (e.g. ../../design/screens) to save screenshots of key screens while the journey runs.
const SHOTS = process.env.SCREENSHOT_DIR;

async function snap(page: Page, name: string, mobile = false) {
  if (!SHOTS) return;
  await page.waitForLoadState("networkidle");
  if (mobile) await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(SHOTS, `${name}${mobile ? "-mobile" : ""}.png`), fullPage: true });
  if (mobile) await page.setViewportSize({ width: 1280, height: 720 });
}

async function emailLink(to: string, kind: "verify-email" | "reset-password"): Promise<string> {
  for (let i = 0; i < 30; i++) {
    const res = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
    const data = (await res.json()) as { messages: { ID: string }[] };
    for (const m of data.messages ?? []) {
      const msg = (await (await fetch(`${MAILPIT}/api/v1/message/${m.ID}`)).json()) as { Text: string };
      const match = msg.Text.match(new RegExp(`https?://[^\\s]+/${kind}\\?token=[A-Za-z0-9_-]+`));
      if (match) return match[0];
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no ${kind} email for ${to}`);
}

async function registerAndLogin(browser: Browser, role: "candidate" | "employer", email: string, name: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(`/register?role=${role}`);
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  if (role === "candidate") await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Check your email")).toBeVisible();

  const link = new URL(await emailLink(email, "verify-email"));
  await page.goto(link.pathname + link.search);
  await expect(page.getByText("Your email address is verified")).toBeVisible();
  await login(page, email, PASSWORD);
  return page;
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("candidate and employer complete the hiring loop", async ({ browser }) => {
  test.skip(!ADMIN_EMAIL || !ADMIN_PASSWORD, "E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD not set");

  // --- Employer: register, verify, create company, request verification
  const employerEmail = `hr-${run}@acme-e2e.example`;
  if (SHOTS) {
    const landing = await (await browser.newContext()).newPage();
    await landing.goto("/");
    await snap(landing, "01-landing");
    await snap(landing, "01-landing", true);
    await landing.goto("/register");
    await snap(landing, "02-register");
  }
  const employer = await registerAndLogin(browser, "employer", employerEmail, "Erin Employer");
  await expect(employer).toHaveURL(/\/employer/);
  await employer.goto("/employer/company");
  await employer.getByLabel("Company name").fill(`Acme ${run}`);
  await employer.getByLabel("Company email domain").fill("acme-e2e.example");
  await employer.getByRole("button", { name: "Create company" }).click();
  await employer.getByRole("button", { name: "Request verification" }).click();
  await expect(employer.getByText("Pending").first()).toBeVisible();
  await snap(employer, "03-employer-company-verification");

  // --- Admin: approve verification
  const admin = await (await browser.newContext()).newPage();
  await login(admin, ADMIN_EMAIL, ADMIN_PASSWORD);
  await expect(admin).toHaveURL(/\/admin/);
  await expect(admin.getByText(`Acme ${run}`)).toBeVisible();
  await snap(admin, "04-admin-console");
  const row = admin.getByRole("listitem").filter({ hasText: `Acme ${run}` });
  await row.getByRole("button", { name: "Approve" }).click();
  await expect(admin.getByText("Decision recorded.")).toBeVisible();

  // --- Employer: create and publish a job
  await employer.goto("/employer/jobs/new");
  await employer.getByLabel("Job title").fill(`Senior Python Engineer ${run}`);
  await employer.getByLabel("Description").fill("Build Python APIs with FastAPI and PostgreSQL on AWS. You will own backend services end to end.");
  await employer.getByLabel("Required skills").fill("Python, PostgreSQL, FastAPI");
  await employer.getByLabel("Preferred skills").fill("Kubernetes");
  await employer.getByLabel("Minimum years of experience").fill("3");
  await snap(employer, "05-employer-job-form");
  await employer.getByRole("button", { name: "Save draft" }).click();
  await expect(employer).toHaveURL(/\/employer\/jobs\/[0-9a-f-]{36}$/);
  await employer.getByRole("button", { name: "Publish" }).click();
  await expect(employer.getByText("Job is now Published.")).toBeVisible();
  const jobUrl = employer.url();

  // --- Candidate: register, upload resume, confirm facts
  const candidateEmail = `ada-${run}@example.org`;
  const candidate = await registerAndLogin(browser, "candidate", candidateEmail, "Ada Candidate");
  await expect(candidate).toHaveURL(/\/candidate/);
  await candidate.goto("/candidate/resumes");
  await candidate.locator("#resume-file").setInputFiles(path.join(here, "fixtures", "resume.pdf"));
  await candidate.getByRole("link", { name: "Review details" }).click();
  await expect(candidate.getByText("Stated in resume").first()).toBeVisible();
  await snap(candidate, "06-candidate-resume-review");
  await candidate.getByRole("button", { name: "Add selected to my profile" }).click();
  await expect(candidate).toHaveURL(/\/candidate\/profile/);
  await expect(candidate.getByRole("list", { name: "Your skills" })).toContainText("PostgreSQL");

  // --- Recommendations and explanation
  await candidate.goto("/candidate/recommendations");
  const jobLink = candidate.getByRole("link", { name: `Senior Python Engineer ${run}` });
  await expect(jobLink).toBeVisible();
  await snap(candidate, "07-candidate-recommendations");
  await jobLink.click();
  await expect(candidate.getByRole("heading", { name: "Why this job matches" })).toBeVisible();
  await expect(candidate.getByText("You match 3 of 3 required skills")).toBeVisible();
  await snap(candidate, "08-job-detail-match-explanation");

  // --- Prepare, review and approve the application
  await candidate.getByRole("link", { name: "Prepare application" }).click();
  await candidate.getByRole("button", { name: "Draft with AI" }).click();
  await expect(candidate.getByLabel("Letter")).toHaveValue(/Senior Python Engineer/);
  await candidate.getByLabel("I reviewed this application and confirm it is accurate.").check();
  await snap(candidate, "09-application-preview");
  await candidate.getByRole("button", { name: "Submit application" }).click();
  await candidate.getByRole("dialog").getByRole("button", { name: "Submit" }).click();
  await expect(candidate).toHaveURL(/\/candidate\/applications\/[0-9a-f-]{36}$/);
  await expect(candidate.getByText("Submitted").first()).toBeVisible();
  const applicationUrl = candidate.url();

  // --- Employer reviews and shortlists
  await employer.goto(jobUrl);
  await employer.getByRole("link", { name: "Ada Candidate" }).click();
  await expect(employer.getByText("Relevance summary (advisory)")).toBeVisible();
  await snap(employer, "10-employer-applicant-detail");
  await employer.getByRole("button", { name: "Shortlist" }).click();
  await employer.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await expect(employer.getByText("Status updated. The candidate was notified.")).toBeVisible();

  // --- Candidate sees the confirmed update
  await candidate.goto(applicationUrl);
  await expect(candidate.getByText("Shortlisted").first()).toBeVisible();
  await snap(candidate, "11-candidate-application-timeline");
  await candidate.goto("/candidate");
  await expect(candidate.getByText("Profile strength")).toBeVisible();
  await snap(candidate, "12-candidate-dashboard");
  await snap(candidate, "12-candidate-dashboard", true);

  // --- Export, then delete account
  await candidate.goto("/settings");
  const download = candidate.waitForEvent("download");
  await candidate.getByRole("button", { name: "Download my data (JSON)" }).click();
  expect((await download).suggestedFilename()).toBe("careerpilot-export.json");
  await candidate.getByRole("button", { name: "Delete my account" }).click();
  await candidate.getByRole("dialog").getByLabel("Confirm with your password").fill(PASSWORD);
  await candidate.getByRole("dialog").getByRole("button", { name: "Delete account" }).click();
  await expect(candidate).toHaveURL(/\/\?deleted=1/);
});
