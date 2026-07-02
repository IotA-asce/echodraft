import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";

async function openWorkflow(page: Page, stepName: string) {
  await workflowStep(page, stepName).click();
}

async function expectWorkflowActive(page: Page, stepName: string) {
  await expect(workflowStep(page, stepName)).toHaveAttribute("aria-current", "step");
}

function workflowStep(page: Page, stepName: string) {
  const escapedStepName = stepName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return page
    .getByRole("navigation", { name: "Production workflow" })
    .getByRole("button", { name: new RegExp(`^\\d{2}\\s+${escapedStepName}(?:\\s|$)`) });
}

async function addVoiceProfile(page: Page, name: string, providerVoiceId: string) {
  const panel = page.locator(".voice-bible-panel");
  await expect(panel.getByRole("heading", { name: "Voice Bible" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await panel.getByLabel("Voice profile name").fill(name);
  await panel.getByLabel("Local provider voice ID or preset ID").fill(providerVoiceId);
  await panel.getByRole("button", { name: "Add voice" }).click();
  await expect(panel.locator(".voice-list .voice-card").filter({ hasText: name })).toBeVisible();
}

test("creates a local project from the dashboard", async ({ page }) => {
  const artifactRoot = path.resolve(__dirname, "../../../.tmp/playwright/artifacts");
  const before = existsSync(artifactRoot) ? new Set(readdirSync(artifactRoot)) : new Set<string>();
  const title = `Browser Smoke ${Date.now()}`;
  await page.goto("/");
  await expect(page.getByText("Your local productions")).toBeVisible();
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByRole("button", { name: "Create project" }).click();
  await openWorkflow(page, "Project");
  const projectListItem = page.locator(".project-list").getByRole("listitem").filter({ hasText: title });
  await expect(projectListItem).toBeVisible();

  await openWorkflow(page, "Manuscript");
  await expect(page.getByLabel("Manuscript file")).toHaveAttribute("accept", /\.pdf/);
  await page.getByLabel("Manuscript file").setInputFiles({
    name: "smoke.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("A browser-imported manuscript.")
  });
  await expect(page.getByText("A browser-imported manuscript.")).toBeVisible();
  await page.getByRole("button", { name: "Extract structure", exact: true }).click();
  await expect(page.getByText("Story Map")).toBeVisible();

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

test("keeps manuscript intake polling until a slow import finishes", async ({ page }) => {
  let importDone = false;
  let polls = 0;

  await page.route(/\/api\/v1\/projects\/[^/]+\/source$/, async (route) => {
    if (!importDone) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "No source" }) });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "source_slow_import",
        projectId: "project_slow_import",
        originalFilename: "slow.pdf",
        status: "ready",
        parserVersion: "ingestion-0.1.0",
        canonicalPath: "/tmp/canonical.md",
        manifestPath: "/tmp/source_manifest.json",
        preview: "Long import manuscript ready.",
        warnings: []
      })
    });
  });
  await page.route(/\/api\/v1\/projects\/[^/]+\/source\/import$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ id: "job_slow_import", status: "running", progress: { phase: "normalizing", message: "Normalizing manuscript locally." } })
    });
  });
  await page.route(/\/api\/v1\/jobs\/job_slow_import$/, async (route) => {
    polls += 1;
    if (polls < 2) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ id: "job_slow_import", status: "running", progress: { phase: "normalizing", message: "Normalizing manuscript locally." } })
      });
      return;
    }
    importDone = true;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ id: "job_slow_import", status: "succeeded", progress: { phase: "completed", message: "Manuscript import completed." } })
    });
  });
  await page.route(/\/api\/v1\/sources\/source_slow_import\/(pages|cleaning-issues)$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
  });

  const title = `Slow Import ${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByRole("button", { name: "Create project" }).click();
  await openWorkflow(page, "Manuscript");
  await page.getByLabel("Manuscript file").setInputFiles({
    name: "slow.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF slow import")
  });

  await expect(page.getByText("Long import manuscript ready.")).toBeVisible({ timeout: 10_000 });
  expect(polls).toBeGreaterThanOrEqual(2);
});

test("shows workflow statuses, empty states, and keyboard project creation", async ({ page }) => {
  const title = `Keyboard Flow ${Date.now()}`;
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Production workflow" }).getByRole("button", { name: /Project/ })).toHaveAttribute("aria-current", "step");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByLabel("Title").press("Enter");
  await expect(page.getByRole("navigation", { name: "Production workflow" }).getByRole("button", { name: /Voice Engine/ })).toHaveAttribute("aria-current", "step");

  await openWorkflow(page, "Structure");
  await expect(page.getByText("No story map yet.")).toBeVisible();
  await openWorkflow(page, "Review & Patch");
  await expect(page.getByText("Nothing to review yet.")).toBeVisible();
  await openWorkflow(page, "Export");
  await expect(page.getByText("No chapters ready for export.")).toBeVisible();
});

test("produces and exports a chapter entirely from the dashboard", async ({ page }) => {
  const title = `Production Desk ${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("combobox", { name: "Voice engine" }).selectOption("mock");
  await page.getByRole("button", { name: "Start with mock voice engine" }).click();
  await expect(page.getByText("Local voice engine settings saved and validated.")).toBeVisible();
  await openWorkflow(page, "Manuscript");
  await page.getByLabel("Manuscript file").setInputFiles({
    name: "chapter.txt", mimeType: "text/plain", buffer: Buffer.from("Chapter 1: Arrival\n\nA complete local production test sentence.")
  });
  await page.getByRole("button", { name: "Extract structure", exact: true }).click();
  await expect(page.getByText("Story Map")).toBeVisible({ timeout: 10_000 });
  const structure = page.locator(".structure-columns");
  await expect(structure.locator(":scope > div").first().getByRole("button").first()).toBeVisible();
  await structure.locator(":scope > div").first().getByRole("button").first().click();
  await expectWorkflowActive(page, "Produce");
  const productionPlayer = page.locator(".structure-view .chapter-audio-player");
  await expect(productionPlayer.getByText("Active chapter audio")).toBeVisible();
  await expect(productionPlayer.getByText("Produce this chapter to create playable audio.")).toBeVisible();
  await expect(productionPlayer.locator("audio")).toHaveCount(0);

  await openWorkflow(page, "Voices & Cast");
  await addVoiceProfile(page, "Mock narrator", "mock-narrator");
  await page.locator(".voice-list .voice-card").filter({ hasText: "Mock narrator" }).getByRole("button", { name: "Set narrator" }).click();
  await openWorkflow(page, "Produce");
  await page.getByRole("button", { name: "Produce chapter audio", exact: true }).click();
  await expect(page.getByText("Chapter production completed. Review the active render below.")).toBeVisible({ timeout: 10_000 });
  const reviewPlayer = page.locator(".review .chapter-audio-player");
  await expect(reviewPlayer.getByText("Active chapter audio")).toBeVisible();
  await expect(reviewPlayer.locator("audio")).toHaveAttribute("src", /artifacts/);
  await expect(reviewPlayer.getByText("Mock voice engine creates silent workflow audio.")).toBeVisible();

  await openWorkflow(page, "Export");
  await page.locator(".chapter-checks input[type=checkbox]").first().check();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export WAV ZIP" }).click();
  await expect(page.getByRole("link", { name: "Download ZIP" })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("link", { name: "Download ZIP" }).click();
  expect((await download).suggestedFilename()).toBe("audiobook.zip");
});

test("drafts cast from upload and produces with an assigned character voice", async ({ page }) => {
  const title = `Cast Draft ${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("combobox", { name: "Voice engine" }).selectOption("mock");
  await page.getByRole("button", { name: "Start with mock voice engine" }).click();
  await openWorkflow(page, "Manuscript");
  await page.getByLabel("Manuscript file").setInputFiles({
    name: "cast-draft.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Chapter 1\n\nMara: We leave now.")
  });

  await page.getByRole("button", { name: "Extract structure", exact: true }).click();
  await expect(page.getByText("Story Map")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("03 / Structure & Cast Draft")).toBeVisible();
  await openWorkflow(page, "Voices & Cast");
  const maraCard = page.locator(".character-card").filter({ hasText: "Mara" });
  await expect(maraCard).toBeVisible();
  await expect(page.locator(".cast-card").filter({ hasText: "Mara" })).toContainText("approved");

  await openWorkflow(page, "Structure");
  const structure = page.locator(".structure-columns");
  await structure.locator(":scope > div").first().getByRole("button").first().click();
  await expectWorkflowActive(page, "Produce");
  await openWorkflow(page, "Voices & Cast");
  await addVoiceProfile(page, "Mock narrator", "mock-narrator");
  await page.locator(".voice-list .voice-card").filter({ hasText: "Mock narrator" }).getByRole("button", { name: "Set narrator" }).click();
  await addVoiceProfile(page, "Mock Mara", "mock-mara");
  await maraCard.getByLabel("Voice").selectOption({ label: "Mock Mara" });

  await openWorkflow(page, "Produce");
  await page.getByRole("button", { name: "Produce chapter audio", exact: true }).click();
  await expect(page.getByText("Chapter production completed. Review the active render below.")).toBeVisible({ timeout: 10_000 });
});

test("keeps the chapter map bounded and shows production progress", async ({ page }) => {
  await page.route(/\/api\/v1\/projects$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([{ id: "proj_progress", title: "Progress UX", author: null, status: "draft", artifactPath: "/tmp/progress", createdAt: new Date().toISOString() }])
    });
  });
  await page.route(/\/api\/v1\/settings\/tts$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ provider: "mock", ready: true, message: null, availableVoices: ["mock-narrator"] }) });
  });
  await page.route(/\/api\/v1\/settings\/tts\/kokoro\/setup$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ platform: "Darwin", state: "not_started", setupMode: "managed_onnx", runtimeRoot: "/tmp/kokoro", pythonPath: "/tmp/kokoro/venv/bin/python", executable: "/tmp/kokoro/wrapper.py", modelPath: "/tmp/kokoro/kokoro-v1.0.onnx", voicesDataPath: "/tmp/kokoro/voices-v1.0.bin", voiceRegistryPath: "/tmp/kokoro/voices.txt", ready: false, nextAction: "Set up Kokoro when you are ready.", availableVoices: [], steps: [] }) });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/source$/, async (route) => {
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "No source" }) });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/chapters$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([{ id: "chap_progress", title: "Chapter 1", status: "draft", confidence: 0.96 }]) });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/structure-warnings$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "warn_possible_scene",
          projectId: "proj_progress",
          sourceDocumentId: "source_progress",
          scopeType: "scene",
          scopeId: "scene_progress",
          severity: "warning",
          message: "Possible inferred scene break needs review.",
          evidence: { code: "scene.possible_break_detected", reviewAction: "confirm_scene_break" },
          confidence: 0.62,
          resolved: false,
          createdAt: new Date().toISOString()
        }
      ])
    });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/structure\/quality$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        chapterCount: 1,
        sceneCount: 1,
        segmentCount: 24,
        dialogueSegmentCount: 2,
        unresolvedDialogueCount: 1,
        averageSegmentChars: 148.4,
        longSegmentCount: 1,
        mixedSegmentWarningCount: 0,
        castCandidateCount: 1,
        lowConfidenceCastCandidateCount: 1,
        possibleSceneBreakCount: 1,
        warningsNeedingReviewCount: 1,
        llmRefinementUsed: true,
        llmAcceptedBatchCount: 1,
        llmRejectedBatchCount: 1
      })
    });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/voices$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([{ id: "voice_progress", projectId: "proj_progress", name: "Mock narrator", backend: "mock", providerVoiceId: "mock-narrator", stylePrompt: null }]) });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/production-settings$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ projectId: "proj_progress", narratorVoiceProfileId: "voice_progress", defaultDirection: null }) });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/(issues|exports|characters|pronunciations)$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/(speaker-attributions|segment-directions|sound-assets)$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
  });
  await page.route(/\/api\/v1\/chapters\/chap_progress\/scenes$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([{ id: "scene_progress", status: "unresolved", confidence: 0.4 }]) });
  });
  await page.route(/\/api\/v1\/scenes\/scene_progress\/segments$/, async (route) => {
    const segments = Array.from({ length: 24 }, (_, index) => ({
      id: `seg_${index}`,
      sceneId: "scene_progress",
      textContent: index === 0
        ? "Unresolved quoted line."
        : index === 1
          ? "Mara said this low-confidence line."
          : index === 2
            ? `Long segment ${"word ".repeat(190)}`
            : `Scrollable segment ${index + 1}`,
      revision: 1,
      status: index < 2 ? "needs_review" : "ready",
      speakerCandidate: index === 1 ? "Mara" : null,
      speakerConfidence: index === 1 ? 0.62 : 0,
      segmentType: index < 2 ? "dialogue" : "narration",
      parserEvidence: {
        productionType: index === 1 ? "dialogue_with_tag" : index < 2 ? "dialogue" : "narration",
        speakerRule: index === 0 ? "unresolved_quote" : index === 1 ? "action_beat_before_quote" : undefined,
        sources: ["block_map", "quote_aware_atomization"]
      },
      userLocked: false,
      lockReason: null
    }));
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(segments)
    });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/chapters\/chap_progress\/production-status$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ chapterId: "chap_progress", ready: true, reason: null, totalSegments: 24, currentSegments: 0, activeRender: null }) });
  });
  await page.route(/\/api\/v1\/projects\/proj_progress\/chapters\/chap_progress\/produce\?force=false$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ id: "job_progress", status: "running", progress: { phase: "rendering", current: 2, total: 5 } }) });
  });
  await page.route(/\/api\/v1\/jobs\/job_progress$/, async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ id: "job_progress", status: "running", progress: { phase: "rendering", current: 3, total: 5 } }) });
  });

  await page.goto("/");
  await page.getByRole("listitem").filter({ hasText: "Progress UX" }).getByRole("button", { name: "Open" }).click();
  await openWorkflow(page, "Structure");
  await page.getByRole("button", { name: "Chapter 1" }).click();
  await expect(page.getByRole("button", { name: /Scene 1/ })).toContainText("Needs review · auto-structure confidence 40%");
  await expect(page.locator(".structure-quality")).toContainText("Segments");
  await expect(page.locator(".structure-quality")).toContainText("24");
  await expect(page.locator(".structure-quality")).toContainText("LLM");
  await expect(page.locator(".segment-evidence").first()).toContainText("speaker unresolved");
  await expect(page.locator(".segment-evidence").first()).toContainText("quote aware atomization");
  const filters = page.locator(".structure-filters");
  await filters.getByRole("button", { name: /Unresolved dialogue/ }).click();
  await expect(page.locator(".segment-entry")).toHaveCount(1);
  await expect(page.locator(".segment-entry").first()).toContainText("Unresolved quoted line.");
  await filters.getByRole("button", { name: /Long segment/ }).click();
  await expect(page.locator(".segment-entry")).toHaveCount(1);
  await expect(page.locator(".segment-entry").first()).toContainText("Long segment");
  await filters.getByRole("button", { name: /All/ }).click();
  const structure = page.locator(".structure-columns");
  const structureStyles = await structure.evaluate((element) => {
    const styles = window.getComputedStyle(element);
    return { height: styles.height, overflowY: styles.overflowY };
  });
  expect(Number.parseFloat(structureStyles.height)).toBeGreaterThanOrEqual(800);
  expect(structureStyles.overflowY).toBe("hidden");
  await expect.poll(async () => structure.locator(":scope > div").first().evaluate((element) => window.getComputedStyle(element).overflowY)).toBe("auto");
  await expect.poll(async () => structure.locator(":scope > div").nth(2).evaluate((element) => window.getComputedStyle(element).overflowY)).toBe("auto");
  const segmentScroll = await structure.locator(":scope > div").nth(2).evaluate((element) => {
    element.scrollTop = 200;
    return { clientHeight: element.clientHeight, scrollHeight: element.scrollHeight, scrollTop: element.scrollTop };
  });
  expect(segmentScroll.scrollHeight).toBeGreaterThan(segmentScroll.clientHeight);
  expect(segmentScroll.scrollTop).toBeGreaterThan(0);
  const structureGap = await page.locator(".structure-view").evaluate((section) => {
    const columns = section.querySelector(".structure-columns")?.getBoundingClientRect();
    const production = section.querySelector(".production-bar")?.getBoundingClientRect();
    return columns && production ? production.top - columns.bottom : Number.NaN;
  });
  expect(structureGap).toBeGreaterThanOrEqual(18);
  expect(structureGap).toBeLessThan(48);

  await page.getByRole("button", { name: "Rebuild all audio" }).click();
  await expect(page.getByText("This creates fresh segment audio for the whole selected chapter.")).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("This creates fresh segment audio for the whole selected chapter.")).toBeHidden();

  await page.getByRole("button", { name: "Produce chapter audio", exact: true }).click();
  const productionPlayer = page.locator(".structure-view .chapter-audio-player");
  await expect(productionPlayer.getByText("Rendering segment 2/5")).toBeVisible();
  await expect(productionPlayer.getByText("40%")).toBeVisible();
  await expect(productionPlayer.getByRole("progressbar", { name: "Chapter production progress" })).toBeVisible();
});

test("guides managed Kokoro setup and narrator selection", async ({ page }) => {
  let kokoroReady = false;
  let jobPolls = 0;
  const setupSteps = [
    "checking_python",
    "creating_runtime",
    "installing_packages",
    "downloading_model",
    "downloading_voice_data",
    "building_voice_registry",
    "validating_preview",
    "saving_settings",
    "completed"
  ];

  await page.route(/\/api\/v1\/settings\/tts$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(kokoroReady ? {
        provider: "kokoro",
        setupMode: "managed_onnx",
        executable: "/tmp/echodraft-kokoro",
        runtimeRoot: "/tmp/echodraft-kokoro-runtime",
        pythonPath: "/tmp/echodraft-kokoro-runtime/venv/bin/python",
        modelPath: "/tmp/echodraft-kokoro-runtime/kokoro-v1.0.onnx",
        voicesDataPath: "/tmp/echodraft-kokoro-runtime/voices-v1.0.bin",
        voiceRegistryPath: "/tmp/echodraft-kokoro-runtime/voices.txt",
        ready: true,
        message: "Kokoro voice system is ready.",
        availableVoices: ["af_heart", "af_sarah"]
      } : {
        provider: "mock",
        ready: true,
        message: null,
        availableVoices: ["mock-narrator", "mock-character"]
      })
    });
  });
  await page.route(/\/api\/v1\/settings\/tts\/kokoro\/setup$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        platform: "Darwin",
        state: kokoroReady ? "active" : "not_started",
        setupMode: "managed_onnx",
        runtimeRoot: "/tmp/echodraft-kokoro-runtime",
        pythonPath: "/tmp/echodraft-kokoro-runtime/venv/bin/python",
        executable: "/tmp/echodraft-kokoro-runtime/echodraft_kokoro_onnx.py",
        modelPath: "/tmp/echodraft-kokoro-runtime/kokoro-v1.0.onnx",
        voicesDataPath: "/tmp/echodraft-kokoro-runtime/voices-v1.0.bin",
        voiceRegistryPath: "/tmp/echodraft-kokoro-runtime/voices.txt",
        ready: kokoroReady,
        message: kokoroReady ? "Kokoro voice system is ready." : "Kokoro has not been set up on this machine yet.",
        nextAction: kokoroReady ? "Create a narrator from one of the available Kokoro voices." : "Select Set up Kokoro voice system to install local Kokoro ONNX assets.",
        availableVoices: kokoroReady ? ["af_heart", "af_sarah"] : [],
        steps: setupSteps.map((phase) => ({ phase, label: phase.replaceAll("_", " "), status: kokoroReady ? "done" : "pending" }))
      })
    });
  });
  await page.route(/\/api\/v1\/settings\/tts\/kokoro\/setup\/install$/, async (route) => {
    jobPolls = 0;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ id: "job_kokoro_setup", status: "queued", progress: { phase: "checking_python", step: 1, total: 9 } })
    });
  });
  await page.route(/\/api\/v1\/jobs\/job_kokoro_setup$/, async (route) => {
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ id: "job_kokoro_setup", status: "running", progress: { phase: "installing_packages", message: "Installing Kokoro ONNX into the local runtime.", step: 3, total: 9 } })
      });
      return;
    }
    kokoroReady = true;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ id: "job_kokoro_setup", status: "succeeded", progress: { phase: "completed", message: "Kokoro voice system is ready.", step: 9, total: 9 } })
    });
  });
  await page.route(/\/api\/v1\/projects\/[^/]+\/voices\/preview$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ assetPath: "/tmp/preview.wav", audioUrl: "/api/v1/projects/test/artifacts/audio/previews/kokoro.wav" })
    });
  });
  await page.route(/\/api\/v1\/projects\/test\/artifacts\/audio\/previews\/kokoro\.wav$/, async (route) => {
    await route.fulfill({ contentType: "audio/wav", body: silentWav() });
  });

  const title = `Kokoro Setup ${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByRole("button", { name: "Create project" }).click();

  await page.getByRole("combobox", { name: "Voice engine" }).selectOption("kokoro");
  await expect(page.getByText("Set up Kokoro preset voices", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Download and install Kokoro locally" }).click();
  await expect(page.getByText(/Installing Kokoro ONNX/)).toBeVisible();
  await expect(page.getByText("Kokoro voice system is ready. Choose a voice and set your narrator.")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("af_heart")).toBeVisible();

  await page.getByRole("button", { name: "Preview" }).first().click();
  await page.getByRole("button", { name: "Set narrator" }).first().click();
  await expect(page.getByRole("button", { name: "Narrator", exact: true }).first()).toBeVisible();
});

test("keeps Kokoro selected when managed repair fails", async ({ page }) => {
  let setupFailed = false;

  await page.route(/\/api\/v1\/settings\/tts$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        provider: "mock",
        ready: true,
        message: null,
        availableVoices: ["mock-narrator"]
      })
    });
  });
  await page.route(/\/api\/v1\/settings\/tts\/kokoro\/setup$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        platform: "Darwin",
        state: setupFailed ? "failed" : "incomplete",
        setupMode: "managed_onnx",
        runtimeRoot: "/tmp/echodraft-kokoro-runtime",
        pythonPath: "/tmp/echodraft-kokoro-runtime/venv/bin/python",
        executable: "/tmp/echodraft-kokoro-runtime/echodraft_kokoro_onnx.py",
        modelPath: "/tmp/echodraft-kokoro-runtime/kokoro-v1.0.onnx",
        voicesDataPath: "/tmp/echodraft-kokoro-runtime/voices-v1.0.bin",
        voiceRegistryPath: "/tmp/echodraft-kokoro-runtime/voices.txt",
        ready: false,
        message: setupFailed ? "Kokoro setup failed while validating the preview." : "Kokoro model is missing. Run Repair setup from Voice setup.",
        nextAction: "Run Repair setup from Voice setup.",
        availableVoices: [],
        steps: [
          { phase: "checking_python", label: "checking python", status: "done" },
          { phase: "downloading_model", label: "downloading model", status: setupFailed ? "failed" : "pending" }
        ]
      })
    });
  });
  await page.route(/\/api\/v1\/settings\/tts\/kokoro\/setup\/install$/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ id: "job_kokoro_setup_failed", status: "queued", progress: { phase: "checking_python", step: 1, total: 9 } })
    });
  });
  await page.route(/\/api\/v1\/jobs\/job_kokoro_setup_failed$/, async (route) => {
    setupFailed = true;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ id: "job_kokoro_setup_failed", status: "failed", errorMessage: "Kokoro setup failed while validating the preview.", progress: { phase: "validating_preview", step: 7, total: 9 } })
    });
  });

  const title = `Kokoro Failed Repair ${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel(/I confirm I have the rights/).check();
  await page.getByRole("button", { name: "Create project" }).click();

  await page.getByRole("combobox", { name: "Voice engine" }).selectOption("kokoro");
  await expect(page.getByText("Kokoro model is missing. Run Repair setup from Voice setup.")).toBeVisible();
  await page.getByRole("button", { name: "Repair setup" }).click();
  await expect(page.locator(".notice.error").getByText("Kokoro setup failed while validating the preview.")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("combobox", { name: "Voice engine" })).toHaveValue("kokoro");
  await expect(page.getByText("Set up Kokoro preset voices", { exact: true })).toBeVisible();
  await expect(page.getByText("Start with mock voice engine")).toBeHidden();
});

function silentWav() {
  const sampleRate = 16_000;
  const samples = sampleRate / 5;
  const dataSize = samples * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  return buffer;
}
