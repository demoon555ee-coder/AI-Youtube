import { test, expect } from "@playwright/test";

function uniqueEmail() {
  return `staging-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
}

test("full creator flow: register → channel → ideas → project → rendered video", async ({ page }) => {
  const email = uniqueEmail();
  const password = "Staging-Password-123!";

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByLabel("Name").fill("Staging Creator");
  await page.getByLabel("Organization").fill("Staging Studio");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/");
  await expect(page).toHaveURL(/\/$/);

  await page.goto("/settings");
  await page.getByLabel("Name").fill("Staging YouTube Channel");
  await page.getByLabel("Niche").fill("AI technology");
  await page.getByRole("button", { name: "Create channel workspace" }).click();
  await expect(page.getByText("Channel created.")).toBeVisible();

  await page.goto("/ideas");
  await page.getByLabel("Topic seed").fill("AI agents");
  await page.getByRole("button", { name: "Generate 10 ideas" }).click();
  await expect(page.getByText("10 new ideas generated using Channel Brain context.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Create project" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Create project" }).first().click();
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
