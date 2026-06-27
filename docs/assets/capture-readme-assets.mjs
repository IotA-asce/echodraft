import { chromium } from "@playwright/test";
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../..");
const outputDir = __dirname;
const frameDir = path.join(outputDir, ".frames");
const port = process.env.ECHODRAFT_CAPTURE_PORT ?? "3100";
const baseUrl = process.env.ECHODRAFT_CAPTURE_BASE_URL ?? `http://127.0.0.1:${port}`;

const now = "2026-06-27T00:00:00.000Z";
const project = {
  id: "proj_readme",
  title: "The Clockwork Harbor",
  author: "Mira Vale",
  status: "structured",
  artifactPath: "/demo/clockwork-harbor",
  createdAt: now,
};
const voices = [
  { id: "voice_narrator", projectId: project.id, name: "Warm narrator", backend: "kokoro", providerVoiceId: "af_heart", stylePrompt: null },
  { id: "voice_keeper", projectId: project.id, name: "Harbor keeper", backend: "kokoro", providerVoiceId: "am_adam", stylePrompt: null },
];
const chapters = [
  { id: "chap_1", title: "Chapter 1: The Harbor Clock", status: "structured", confidence: 0.97 },
  { id: "chap_2", title: "Chapter 2: Lantern Weather", status: "draft", confidence: 0.86 },
];
const scenes = [
  { id: "scene_1", status: "structured", confidence: 0.96 },
  { id: "scene_2", status: "unresolved", confidence: 0.68 },
];
const segments = [
  { id: "seg_1", textContent: "The harbor clock struck six, and every gull on the quay went silent.", revision: 2, status: "current", speakerCandidate: "narration" },
  { id: "seg_2", textContent: "Mara tucked the brass key into her coat before the tide bells could answer.", revision: 1, status: "draft", speakerCandidate: "Mara" },
  { id: "seg_3", textContent: "\"No one winds that clock after dusk,\" said the keeper, softer than the rain.", revision: 1, status: "draft", speakerCandidate: "Harbor keeper" },
  { id: "seg_4", textContent: "The manuscript note marks this line for a calmer second pass.", revision: 3, status: "stale", speakerCandidate: "narration" },
];
const issues = [
  {
    id: "issue_1",
    projectId: project.id,
    chapterId: "chap_1",
    segmentId: "seg_4",
    severity: "medium",
    category: "delivery",
    title: "Line reads too brightly",
    description: "Patch this segment with a quieter direction before exporting the review cut.",
    status: "open",
  },
];
const exports = [
  {
    id: "export_1",
    projectId: project.id,
    format: "wav",
    status: "complete",
    outputPath: "/demo/exports/clockwork-harbor.wav.zip",
    manifestPath: "/demo/exports/manifest.json",
    archivePath: "/demo/exports/clockwork-harbor.wav.zip",
    downloadUrl: "/api/v1/projects/proj_readme/artifacts/exports/clockwork-harbor.wav.zip",
  },
];

function startWebServer() {
  if (process.env.ECHODRAFT_CAPTURE_BASE_URL) return null;
  const child = spawn(
    "npm",
    ["--workspace", "@echodraft/web", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", port],
    {
      cwd: repoRoot,
      env: { ...process.env, NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  child.stdout.on("data", (data) => process.stdout.write(data));
  child.stderr.on("data", (data) => process.stderr.write(data));
  return child;
}

async function waitForServer(child) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (child?.exitCode !== null && child?.exitCode !== undefined) throw new Error(`Next dev server exited with code ${child.exitCode}`);
    try {
      const response = await fetch(baseUrl);
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  throw new Error(`Timed out waiting for ${baseUrl}`);
}

async function json(route, body, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

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

async function installRoutes(page) {
  await page.route(/\/api\/v1\//, (route) => {
    console.warn(`No capture route for ${route.request().method()} ${route.request().url()}`);
    return json(route, { detail: "Unused capture route" }, 404);
  });
  await page.route(/\/api\/v1\/projects\/?$/, async (route) => {
    if (route.request().method() === "POST") return json(route, project);
    return json(route, [
      project,
      { ...project, id: "proj_second", title: "Northbound Letters", author: "Jon Bell", status: "draft" },
    ]);
  });
  await page.route(/\/api\/v1\/settings\/tts\/?$/, (route) => json(route, {
    provider: "kokoro",
    setupMode: "managed_onnx",
    executable: "/demo/kokoro/echodraft_kokoro_onnx.py",
    runtimeRoot: "/demo/kokoro/managed-onnx-v1",
    pythonPath: "/demo/kokoro/venv/bin/python",
    modelPath: "/demo/kokoro/kokoro-v1.0.onnx",
    voicesDataPath: "/demo/kokoro/voices-v1.0.bin",
    voiceRegistryPath: "/demo/kokoro/voices.txt",
    ready: true,
    message: "Kokoro voice system is ready.",
    availableVoices: ["af_heart", "af_sarah", "am_adam"],
  }));
  await page.route(/\/api\/v1\/settings\/tts\/kokoro\/setup\/?$/, (route) => json(route, {
    platform: "Darwin",
    state: "active",
    setupMode: "managed_onnx",
    runtimeRoot: "/demo/kokoro/managed-onnx-v1",
    pythonPath: "/demo/kokoro/venv/bin/python",
    executable: "/demo/kokoro/echodraft_kokoro_onnx.py",
    modelPath: "/demo/kokoro/kokoro-v1.0.onnx",
    voicesDataPath: "/demo/kokoro/voices-v1.0.bin",
    voiceRegistryPath: "/demo/kokoro/voices.txt",
    ready: true,
    message: "Kokoro voice system is ready.",
    nextAction: "Create a narrator from one of the available Kokoro voices.",
    availableVoices: ["af_heart", "af_sarah", "am_adam"],
    steps: [
      "checking_python",
      "creating_runtime",
      "installing_packages",
      "downloading_model",
      "downloading_voice_data",
      "building_voice_registry",
      "validating_preview",
      "saving_settings",
      "completed",
    ].map((phase) => ({ phase, label: phase.replaceAll("_", " "), status: "done" })),
  }));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/source/?$`), (route) => json(route, {
    originalFilename: "clockwork-harbor.md",
    status: "normalized",
    parserVersion: "ingestion-0.1.0",
    preview: "Chapter 1: The Harbor Clock\n\nThe harbor clock struck six, and every gull on the quay went silent.\n\nMara tucked the brass key into her coat before the tide bells could answer.",
    warnings: [],
  }));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/chapters/?$`), (route) => json(route, chapters));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/voices/?$`), async (route) => {
    if (route.request().method() === "POST") return json(route, voices[0]);
    return json(route, voices);
  });
  await page.route(new RegExp(`/api/v1/projects/${project.id}/production-settings/?$`), (route) => json(route, {
    projectId: project.id,
    narratorVoiceProfileId: "voice_narrator",
    defaultDirection: null,
  }));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/issues/?$`), (route) => json(route, issues));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/exports/?$`), async (route) => {
    if (route.request().method() === "POST") return json(route, exports[0]);
    return json(route, exports);
  });
  await page.route(new RegExp(`/api/v1/projects/${project.id}/characters/?$`), (route) => json(route, [
    { id: "char_mara", projectId: project.id, displayName: "Mara", roleType: "protagonist", notes: null },
  ]));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/pronunciations/?$`), (route) => json(route, [
    { id: "pron_quay", term: "quay", phonetic: null, replacementText: "key" },
  ]));
  await page.route(/\/api\/v1\/chapters\/chap_1\/scenes\/?$/, (route) => json(route, scenes));
  await page.route(/\/api\/v1\/scenes\/scene_1\/segments\/?$/, (route) => json(route, segments));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/chapters/chap_1/production-status/?$`), (route) => json(route, {
    chapterId: "chap_1",
    ready: true,
    reason: "3/4 segments current",
    totalSegments: 4,
    currentSegments: 3,
    activeRender: {
      id: "render_1",
      chapterId: "chap_1",
      status: "complete",
      speechPath: "/demo/renders/chapter-1.wav",
      audioUrl: "/api/v1/projects/proj_readme/artifacts/renders/chapter-1.wav",
      durationMs: 184000,
      renderMode: "speech_only",
    },
  }));
  await page.route(/\/api\/v1\/issues\/issue_1\/comments\/?$/, (route) => json(route, [
    { id: "comment_1", issueId: "issue_1", body: "Lower intensity and reassemble only this chapter.", author: "local reviewer", createdAt: now },
  ]));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/artifacts/renders/chapter-1\\.wav$`), (route) => route.fulfill({
    contentType: "audio/wav",
    body: silentWav(),
  }));
  await page.route(/\/api\/v1\/issues\/issue_1\/?$/, (route) => json(route, { ...issues[0], status: "resolved" }));
  await page.route(new RegExp(`/api/v1/projects/${project.id}/segments/seg_4/patch/?$`), (route) => json(route, { status: "patched" }));
}

async function openProject(page) {
  await page.getByRole("listitem").filter({ hasText: project.title }).getByRole("button", { name: "Open" }).click();
  await page.getByText("Set up the local voice system").waitFor();
}

async function openChapter(page) {
  await page.getByRole("button", { name: /Chapter 1: The Harbor Clock/ }).click();
  await page.getByText("Editable story map").waitFor();
}

async function captureAssets() {
  mkdirSync(outputDir, { recursive: true });
  mkdirSync(frameDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
  await installRoutes(page);
  await page.goto(baseUrl);
  await page.getByText("Your local productions").waitFor();
  await page.screenshot({ path: path.join(outputDir, "dashboard-projects.png"), fullPage: false });

  await openProject(page);
  await page.locator(".import-desk").scrollIntoViewIfNeeded();
  await page.locator(".import-desk").screenshot({ path: path.join(outputDir, "manuscript-import.png") });

  await page.locator(".studio-section.settings").scrollIntoViewIfNeeded();
  await page.locator(".studio-section.settings").screenshot({ path: path.join(outputDir, "voice-setup.png") });

  await openChapter(page);
  await page.locator(".structure-view").scrollIntoViewIfNeeded();
  await page.locator(".segment-entry").nth(3).getByRole("button").first().click();
  await page.getByLabel("Narration text").waitFor();
  await page.locator(".structure-view").screenshot({ path: path.join(outputDir, "segment-editor.png") });

  await page.locator(".review").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(frameDir, "01-review.png"), fullPage: false });
  await page.getByRole("button", { name: "Discuss" }).click();
  await page.getByText("Lower intensity").waitFor();
  await page.screenshot({ path: path.join(frameDir, "02-patch.png"), fullPage: false });
  await page.locator(".exports").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(frameDir, "03-export.png"), fullPage: false });

  await browser.close();
  execFileSync("magick", [
    path.join(frameDir, "01-review.png"),
    "-resize",
    "1280x720^",
    "-gravity",
    "north",
    "-extent",
    "1280x720",
    path.join(frameDir, "01-review.gif"),
  ]);
  execFileSync("magick", [
    path.join(frameDir, "02-patch.png"),
    "-resize",
    "1280x720^",
    "-gravity",
    "north",
    "-extent",
    "1280x720",
    path.join(frameDir, "02-patch.gif"),
  ]);
  execFileSync("magick", [
    path.join(frameDir, "03-export.png"),
    "-resize",
    "1280x720^",
    "-gravity",
    "north",
    "-extent",
    "1280x720",
    path.join(frameDir, "03-export.gif"),
  ]);
  execFileSync("magick", [
    "-delay",
    "120",
    "-loop",
    "0",
    path.join(frameDir, "01-review.gif"),
    path.join(frameDir, "02-patch.gif"),
    path.join(frameDir, "03-export.gif"),
    path.join(outputDir, "review-patch-export.gif"),
  ]);
  rmSync(frameDir, { recursive: true, force: true });
}

const server = startWebServer();
try {
  await waitForServer(server);
  await captureAssets();
} finally {
  server?.kill("SIGTERM");
}
