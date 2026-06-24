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

  const structureColumns = page.locator(".structure-columns");
  await structureColumns.locator(":scope > div").nth(0).getByRole("button").first().click();
  const segmentButton = structureColumns.locator(":scope > div").nth(2).getByRole("button").first();
  await segmentButton.click();

  const editor = page.getByLabel("Narration text");
  await expect(editor).toHaveValue("A browser-imported manuscript.");
  await expect(page.getByRole("button", { name: "Save revision" })).toBeDisabled();
  await editor.fill("A carefully revised browser-imported manuscript.");
  await expect(page.getByText(/Saving creates revision r\d+/)).toBeVisible();
  await page.getByRole("button", { name: "Save revision" }).click();
  await expect(page.getByText(/Revision r\d+ saved\./)).toBeVisible();
  await expect(segmentButton).toContainText("A carefully revised browser-imported manuscript.");

  const createdDirectories = readdirSync(artifactRoot).filter((name) => !before.has(name));
  expect(createdDirectories).toHaveLength(1);
  expect(existsSync(path.join(artifactRoot, createdDirectories[0], "manifests"))).toBeTruthy();
});

test("produces and exports a chapter entirely from the dashboard", async ({ page }) => {
  const title = `Production Desk ${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByLabel("Manuscript file").setInputFiles({
    name: "chapter.txt", mimeType: "text/plain", buffer: Buffer.from("Chapter 1: Arrival\n\nA complete local production test sentence.")
  });
  await page.getByRole("button", { name: "Extract structure" }).click();
  const structure = page.locator(".structure-columns");
  await structure.locator(":scope > div").first().getByRole("button").first().click();

  await page.getByPlaceholder("Profile name").fill("Mock narrator");
  await page.getByPlaceholder("Local provider voice ID").fill("mock-narrator");
  await page.getByRole("button", { name: "Add voice" }).click();
  await page.getByRole("button", { name: "Set narrator" }).click();
  await page.getByRole("button", { name: "Produce chapter" }).click();
  await expect(page.getByText("Chapter production completed. Review the active render below.")).toBeVisible({ timeout: 10_000 });
  await expect(page.locator("audio")).toHaveAttribute("src", /artifacts/);

  await page.locator(".chapter-checks input[type=checkbox]").first().check();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export WAV ZIP" }).click();
  await expect(page.getByRole("link", { name: "Download ZIP" })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("link", { name: "Download ZIP" }).click();
  expect((await download).suggestedFilename()).toBe("audiobook.zip");
});
