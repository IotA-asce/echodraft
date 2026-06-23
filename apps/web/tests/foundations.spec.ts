import { expect, test } from "@playwright/test";
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";

test("creates a local project from the dashboard", async ({ page }) => {
  const artifactRoot = path.resolve(__dirname, "../../../.tmp/playwright/artifacts");
  const before = existsSync(artifactRoot) ? new Set(readdirSync(artifactRoot)) : new Set<string>();
  const title = `Browser Smoke ${Date.now()}`;
  await page.goto("/");
  await expect(page.getByText("Your local productions")).toBeVisible();
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByText(title)).toBeVisible();

  const createdDirectories = readdirSync(artifactRoot).filter((name) => !before.has(name));
  expect(createdDirectories).toHaveLength(1);
  expect(existsSync(path.join(artifactRoot, createdDirectories[0], "manifests"))).toBeTruthy();
});
