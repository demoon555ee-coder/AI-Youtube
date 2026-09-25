import { test, expect } from "@playwright/test";

function uniqueEmail() {
  return `staging-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
}

test("full creator flow: register → channel → ideas → project → rendered video", async ({ page }) => {
  const email = uniqueEmail();
  const password = "Staging-Password-123!";

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.locator("#auth-email").fill(email);
  await page.locator("#auth-password").fill(password);
  await page.locator("#auth-name").fill("Staging Creator");
  await page.locator("#auth-organization").fill("Staging Studio");
  await page.getByRole("button", { name: "Create account" }).click();

  await page.waitForURL(/\/onboarding\/channels/);
  await expect(page.getByRole("heading", { name: "Choose the channel we will operate." })).toBeVisible();

  await page.getByRole("button", { name: /Create a separate AI workspace/ }).click();
  await page.getByLabel("Workspace name").fill("Staging YouTube Channel");
  await page.getByLabel("Niche").fill("AI technology");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByRole("button", { name: /Staging YouTube Channel/ })).toBeVisible();

  await page.getByRole("button", { name: "Continue to Dashboard →" }).click();
  await page.waitForURL(/\/$/);

  await page.goto("/ideas");
  await page.getByLabel("Topic seed").fill("AI agents");
  await page.getByRole("button", { name: "Generate 12 ideas" }).click();
  await expect(page.getByText("12 new ideas generated using Channel Brain context.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: /Create project/ }).first()).toBeVisible();
  await page.getByRole("button", { name: /Create project/ }).first().click();
  await page.waitForURL(/\/projects\//);

  await expect(page.getByRole("heading", { name: "Workflow" })).toBeVisible();
  await page.getByRole("button", { name: "Run AI workflow" }).click();
  await expect(page.getByText("READY_TO_PUBLISH")).toBeVisible({ timeout: 90_000 });
  await expect(page.locator("video")).toBeVisible();

  const projectId = page.url().split("/projects/")[1].split("/")[0];
  const video = await page.context().request.get(`http://127.0.0.1:8001/api/v1/projects/${projectId}/video`);
  expect(video.ok()).toBeTruthy();
  expect(video.headers()["content-type"]).toContain("video/mp4");
  await expect(page.locator("img[alt='Generated thumbnail']")).toBeVisible();
});
