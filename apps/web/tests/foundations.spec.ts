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

  await page.getByRole("listitem").filter({ hasText: title }).getByRole("button", { name: "Open" }).click();
  await page.getByLabel("Manuscript file").setInputFiles({
    name: "smoke.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("A browser-imported manuscript.")
  });
  await expect(page.getByText("A browser-imported manuscript.")).toBeVisible();
  await page.getByRole("button", { name: "Extract structure" }).click();
  await expect(page.getByText("Editable story map")).toBeVisible();

  const createdDirectories = readdirSync(artifactRoot).filter((name) => !before.has(name));
  expect(createdDirectories).toHaveLength(1);
  expect(existsSync(path.join(artifactRoot, createdDirectories[0], "manifests"))).toBeTruthy();
});
