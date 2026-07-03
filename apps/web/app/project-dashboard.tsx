"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import {
  addComment, assembleChapter, assetUrl, compareSegmentRenders, createCharacter, createExport, createProject, createPronunciation, createSoundCue, createVoice, deleteVoice,
  extractStructure, getJob, getKokoroSetup, getLocalAiInstallJob, getProductionSettings, getProductionStatus, getSegmentReviewInspector,
  getSource, getStructureQuality, getTtsProviders, getTtsSettings, installKokoroSetup, installLocalAiModel,
  importSource, listCharacters, listChapterSoundCues, listChapters, listCleaningIssues, listComments, listExports, listIssues, listPronunciations, listRenderQueue,
  inferSegmentDirections, listLocalAiCatalog, listProjects, listScenes, listSegmentDirections, listSegments, listSoundAssets, listSourcePages, listSpeakerAttributions, listStructureWarnings, listVoices, mergeCharacter, mergeSegment, patchSegment, previewVoice, produceChapter,
  reparseSource, runReadiness, runSpeakerAttribution, saveProductionSettings, saveSegmentDirection, saveSegmentOverride, saveTtsSettings, testTtsSettings,
  setStructureLock, splitCharacter, splitSegment, updateCharacter, updateCleaningIssue, updateIssue, updateSegment, updateSpeakerAttribution, uploadSoundAsset, verifyLocalAiModel, type Chapter, type Character, type Comment, type Direction,
  type ExportPackage, type Issue, type Job, type KokoroSetupStatus, type LocalAiCatalogItem, type LocalAiInstallJob, type ReadinessReport,
  type ProductionSettings, type ProductionStatus, type Pronunciation, type Project, type RenderQueueItem, type Scene, type Segment,
  type SegmentDirection, type SegmentRenderComparison, type SegmentReviewInspector, type SoundAsset, type SoundCue, type SourceDocument, type SourcePage, type SpeakerAttribution, type StructureParserWarning, type StructureQuality, type TextCleanlinessIssue, type TtsProvider, type TtsProviderInfo, type TtsSettings, type VoiceProfile,
} from "./api";
import { InlineNotice } from "./components/common/InlineNotice";
import { ExportPanel } from "./components/export/ExportPanel";
import { StudioHero } from "./components/layout/StudioHero";
import { StudioShell } from "./components/layout/StudioShell";
import { ManuscriptIntakePanel } from "./components/manuscript/ManuscriptIntakePanel";
import { NewProjectPanel } from "./components/project/NewProjectPanel";
import { ProjectLibraryPanel } from "./components/project/ProjectLibraryPanel";
import { ReviewPatchPanel } from "./components/review/ReviewPatchPanel";
import { ModelCenter } from "./components/setup/ModelCenter";
import { LocalProviderSetup } from "./components/setup/LocalProviderSetup";
import { ProviderStatus } from "./components/setup/ProviderStatus";
import { StoryMapPanel } from "./components/structure/StoryMapPanel";
import { VoiceBiblePanel } from "./components/voices/VoiceBiblePanel";
import { uiCopy } from "./lib/copy";
import { buildWorkflowSteps, type WorkflowStepId } from "./lib/workflow";

const directionFor = (scopeType: string, scopeId: string): Direction => ({ scopeType, scopeId, pace: 1, intensity: 0.4, tone: "neutral", emotion: "neutral", pauseBeforeMs: 0, pauseAfterMs: 120, stylePrompt: "Clear, restrained audiobook narration", emphasis: false, whisper: false, noSfx: true });
const emptyTts = (provider: TtsProvider): TtsSettings => ({ provider, setupMode: provider === "kokoro" ? "managed_onnx" : provider === "piper" ? "local_cli" : provider === "xtts_v2" ? "coqui_local" : null, ready: false, availableVoices: [], referenceVoiceConsent: false, language: "en" });
const messageOf = (cause: unknown) => cause instanceof Error ? cause.message : "The local studio could not complete that request.";
function csvList(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function ProjectDashboard() {
  const [projects, setProjects] = useState<Project[]>([]); const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [title, setTitle] = useState(""); const [author, setAuthor] = useState(""); const [rights, setRights] = useState(false);
  const [source, setSource] = useState<SourceDocument | null>(null); const [sourcePages, setSourcePages] = useState<SourcePage[]>([]); const [cleaningIssues, setCleaningIssues] = useState<TextCleanlinessIssue[]>([]); const [structureWarnings, setStructureWarnings] = useState<StructureParserWarning[]>([]); const [structureQuality, setStructureQuality] = useState<StructureQuality | null>(null); const [chapters, setChapters] = useState<Chapter[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]); const [segments, setSegments] = useState<Segment[]>([]); const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null);
  const [editing, setEditing] = useState<Segment | null>(null); const [draft, setDraft] = useState("");
  const [tts, setTts] = useState<TtsSettings | null>(null); const [ttsProviders, setTtsProviders] = useState<TtsProviderInfo[]>([]); const [selectedTtsProvider, setSelectedTtsProvider] = useState<TtsProvider>("mock"); const [kokoroSetup, setKokoroSetup] = useState<KokoroSetupStatus | null>(null); const [voices, setVoices] = useState<VoiceProfile[]>([]); const [production, setProduction] = useState<ProductionSettings | null>(null);
  const [status, setStatus] = useState<ProductionStatus | null>(null); const [job, setJob] = useState<Job | null>(null); const [setupJob, setSetupJob] = useState<Job | null>(null); const [importJob, setImportJob] = useState<Job | null>(null);
  const [localAiCatalog, setLocalAiCatalog] = useState<LocalAiCatalogItem[]>([]); const [localAiJob, setLocalAiJob] = useState<Job | null>(null); const [localAiInstallJob, setLocalAiInstallJob] = useState<LocalAiInstallJob | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]); const [comments, setComments] = useState<Comment[]>([]); const [activeIssue, setActiveIssue] = useState<Issue | null>(null);
  const [exports, setExports] = useState<ExportPackage[]>([]); const [characters, setCharacters] = useState<Character[]>([]); const [speakerAttributions, setSpeakerAttributions] = useState<SpeakerAttribution[]>([]); const [segmentDirections, setSegmentDirections] = useState<SegmentDirection[]>([]); const [renderQueue, setRenderQueue] = useState<RenderQueueItem[]>([]); const [renderCompare, setRenderCompare] = useState<SegmentRenderComparison | null>(null); const [segmentInspector, setSegmentInspector] = useState<SegmentReviewInspector | null>(null); const [pronunciations, setPronunciations] = useState<Pronunciation[]>([]); const [soundAssets, setSoundAssets] = useState<SoundAsset[]>([]); const [soundCues, setSoundCues] = useState<SoundCue[]>([]); const [readiness, setReadiness] = useState<ReadinessReport | null>(null);
  const [notice, setNotice] = useState<string | null>(null); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const [voiceName, setVoiceName] = useState(""); const [providerVoiceId, setProviderVoiceId] = useState(""); const [selectedExportIds, setSelectedExportIds] = useState<string[]>([]);
  const [exportAudioVariant, setExportAudioVariant] = useState<"active" | "clean" | "mixed">("active"); const [exportTitle, setExportTitle] = useState(""); const [exportAuthor, setExportAuthor] = useState(""); const [exportAlbum, setExportAlbum] = useState(""); const [exportPublisher, setExportPublisher] = useState(""); const [exportLanguage, setExportLanguage] = useState("en"); const [exportCoverPath, setExportCoverPath] = useState("");
  const [characterName, setCharacterName] = useState(""); const [characterAliases, setCharacterAliases] = useState(""); const [characterTraits, setCharacterTraits] = useState("");
  const [soundAssetType, setSoundAssetType] = useState<"ambience" | "music" | "sfx">("ambience"); const [soundCueType, setSoundCueType] = useState<"ambience" | "music" | "sfx">("ambience"); const [soundRenderMode, setSoundRenderMode] = useState<"light" | "dramatized" | "all">("light"); const [soundGain, setSoundGain] = useState(-24);
  const [selectedSoundAssetId, setSelectedSoundAssetId] = useState("");
  const [showAdvancedTts, setShowAdvancedTts] = useState(false);
  const [activeSection, setActiveSection] = useState<WorkflowStepId>("project");

  const project = useMemo(() => projects.find((item) => item.id === selectedProjectId) ?? null, [projects, selectedProjectId]);
  const narrator = voices.find((item) => item.id === production?.narratorVoiceProfileId) ?? null;
  const kokoroVoices = kokoroSetup?.availableVoices.length ? kokoroSetup.availableVoices : (tts?.provider === "kokoro" ? tts.availableVoices : []);
  const activeProviderInfo = ttsProviders.find((item) => item.provider === selectedTtsProvider) ?? null;
  const currentSceneId = segments[0]?.sceneId ?? scenes[0]?.id ?? null;
  const activeSoundAsset = soundAssets.find((item) => item.id === selectedSoundAssetId) ?? soundAssets.find((item) => item.assetType === soundCueType) ?? soundAssets[0] ?? null;
  const workflowSteps = useMemo(
    () =>
      buildWorkflowSteps({
        project,
        tts,
        source,
        structureWarnings,
        chapters,
        voices,
        production,
        selectedChapter,
        productionStatus: status,
        productionJob: job,
        issues,
        exports,
      }),
    [project, tts, source, structureWarnings, chapters, voices, production, selectedChapter, status, job, issues, exports],
  );

  useEffect(() => { listProjects().then(setProjects).catch((cause) => setError(messageOf(cause))); getTtsSettings().then((next) => { setTts(next); setSelectedTtsProvider(next.provider); }).catch((cause) => setError(messageOf(cause))); getTtsProviders().then(setTtsProviders).catch((cause) => setError(messageOf(cause))); getKokoroSetup().then(setKokoroSetup).catch((cause) => setError(messageOf(cause))); void refreshLocalAi(); }, []);
  useEffect(() => {
    if (!importJob || !selectedProjectId || !["queued", "running"].includes(importJob.status)) return;
    const timer = window.setTimeout(() => {
      void getJob(importJob.id).then(async (next) => {
        setImportJob(next);
        if (next.status === "succeeded") {
          await refreshImportedSource(selectedProjectId);
          setNotice("Manuscript normalized locally. Inspect the preview, then extract structure.");
          setActiveSection("manuscript");
          setBusy(false);
        }
        if (next.status === "failed" || next.status === "cancelled") {
          setError(next.errorMessage ?? "Manuscript import failed.");
          setBusy(false);
        }
      }).catch((cause) => { setError(messageOf(cause)); setBusy(false); });
    }, 750);
    return () => window.clearTimeout(timer);
  }, [importJob, selectedProjectId]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setTimeout(() => {
      void getJob(job.id).then((next) => {
        setJob(next);
        if (selectedProjectId && selectedChapter) void refreshRenderQueue(selectedProjectId, selectedChapter.id);
        if (next.status === "succeeded" && selectedProjectId && selectedChapter) {
          void refreshProduction(selectedProjectId, selectedChapter.id);
          void refreshRenderQueue(selectedProjectId, selectedChapter.id);
          setNotice("Chapter production completed. Review the active render below.");
          setActiveSection("review-patch");
        }
        if (next.status === "failed") setError(next.errorMessage ?? "Chapter production failed.");
      }).catch((cause) => setError(messageOf(cause)));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [job, selectedChapter, selectedProjectId]);
  useEffect(() => {
    if (!setupJob || !["queued", "running"].includes(setupJob.status)) return;
    const timer = window.setTimeout(() => {
      void getJob(setupJob.id).then((next) => {
        setSetupJob(next);
        if (next.status === "succeeded") {
          void refreshTtsSetup({ syncProvider: true });
          setNotice("Kokoro voice system is ready. Choose a voice and set your narrator.");
        }
        if (next.status === "failed") {
          setError(next.errorMessage ?? "Kokoro setup failed.");
          void refreshTtsSetup();
        }
      }).catch((cause) => setError(messageOf(cause)));
    }, 750);
    return () => window.clearTimeout(timer);
  }, [setupJob]);
  useEffect(() => {
    if (!localAiJob || !["queued", "running"].includes(localAiJob.status)) return;
    const timer = window.setTimeout(() => {
      void Promise.allSettled([getJob(localAiJob.id), getLocalAiInstallJob(localAiJob.id)]).then((settled) => {
        const [nextJob, nextInstallJob] = settled;
        if (nextJob.status === "fulfilled") {
          setLocalAiJob(nextJob.value);
          if (nextJob.value.status === "succeeded") {
            void refreshLocalAi();
            void refreshTtsSetup({ syncProvider: true });
            setNotice("Local AI setup completed and was verified.");
          }
          if (nextJob.value.status === "failed") {
            setError(nextJob.value.errorMessage ?? "Local AI setup failed.");
            void refreshLocalAi();
          }
        }
        if (nextInstallJob.status === "fulfilled") setLocalAiInstallJob(nextInstallJob.value);
      }).catch((cause) => setError(messageOf(cause)));
    }, 900);
    return () => window.clearTimeout(timer);
  }, [localAiJob]);

  async function loadProject(projectId: string) {
    setSelectedProjectId(projectId); setError(null); setNotice(null); setSelectedChapter(null); setScenes([]); setSegments([]); setSpeakerAttributions([]); setSegmentDirections([]); setRenderQueue([]); setRenderCompare(null); setSegmentInspector(null); setSoundCues([]); setReadiness(null); setStructureQuality(null);
    const settled = await Promise.allSettled([getSource(projectId), listChapters(projectId), listStructureWarnings(projectId), getStructureQuality(projectId), listVoices(projectId), getProductionSettings(projectId), listIssues(projectId), listExports(projectId), listCharacters(projectId), listSpeakerAttributions(projectId), listSegmentDirections(projectId), listPronunciations(projectId), listSoundAssets(projectId)]);
    const [nextSource, nextChapters, nextWarnings, nextQuality, nextVoices, nextProduction, nextIssues, nextExports, nextCharacters, nextAttributions, nextDirections, nextPronunciations, nextSoundAssets] = settled;
    setSource(nextSource.status === "fulfilled" ? nextSource.value : null); setChapters(nextChapters.status === "fulfilled" ? nextChapters.value : []);
    setStructureWarnings(nextWarnings.status === "fulfilled" ? nextWarnings.value : []);
    setStructureQuality(nextQuality.status === "fulfilled" ? nextQuality.value : null);
    if (nextSource.status === "fulfilled") { listSourcePages(nextSource.value.id).then(setSourcePages).catch(() => setSourcePages([])); listCleaningIssues(nextSource.value.id).then(setCleaningIssues).catch(() => setCleaningIssues([])); } else { setSourcePages([]); setCleaningIssues([]); }
    if (nextVoices.status === "fulfilled") setVoices(nextVoices.value); if (nextProduction.status === "fulfilled") setProduction(nextProduction.value);
    if (nextIssues.status === "fulfilled") setIssues(nextIssues.value); if (nextExports.status === "fulfilled") setExports(nextExports.value);
    if (nextCharacters.status === "fulfilled") setCharacters(nextCharacters.value); if (nextAttributions.status === "fulfilled") setSpeakerAttributions(nextAttributions.value); if (nextDirections.status === "fulfilled") setSegmentDirections(nextDirections.value); if (nextPronunciations.status === "fulfilled") setPronunciations(nextPronunciations.value); if (nextSoundAssets.status === "fulfilled") setSoundAssets(nextSoundAssets.value);
    setActiveSection("voice-engine");
  }
  async function waitFor(jobId: string, projectId: string) { for (let i = 0; i < 80; i += 1) { const next = await getJob(jobId); if (next.status === "succeeded") return; if (next.status === "failed" || next.status === "cancelled") throw new Error(next.errorMessage || "Background task failed."); await new Promise((resolve) => setTimeout(resolve, 250)); } throw new Error("The task is taking longer than expected."); }
  async function refreshLocalAi() { try { setLocalAiCatalog(await listLocalAiCatalog()); } catch (cause) { setError(messageOf(cause)); } }
  async function refreshProduction(projectId: string, chapterId: string) { try { const [nextStatus, nextIssues] = await Promise.all([getProductionStatus(projectId, chapterId), listIssues(projectId)]); setStatus(nextStatus); setIssues(nextIssues); } catch (cause) { setStatus(null); setError(messageOf(cause)); } }
  async function refreshRenderQueue(projectId: string, chapterId: string) { try { setRenderQueue(await listRenderQueue(projectId, chapterId)); } catch (cause) { setRenderQueue([]); setError(messageOf(cause)); } }
  async function refreshSoundDesign(projectId: string, chapterId?: string) { try { const [assets, cues] = await Promise.all([listSoundAssets(projectId), chapterId ? listChapterSoundCues(projectId, chapterId) : Promise.resolve([])]); setSoundAssets(assets); setSoundCues(cues); } catch (cause) { setError(messageOf(cause)); } }
  async function refreshImportedSource(projectId: string) { const nextSource = await getSource(projectId); setSource(nextSource); setSourcePages(await listSourcePages(nextSource.id).catch(() => [])); setCleaningIssues(await listCleaningIssues(nextSource.id).catch(() => [])); }
  async function inspectSegment(segmentId: string) { if (!selectedProjectId) return; try { const [comparison, inspector] = await Promise.all([compareSegmentRenders(selectedProjectId, segmentId), getSegmentReviewInspector(selectedProjectId, segmentId)]); setRenderCompare(comparison); setSegmentInspector(inspector); } catch { setRenderCompare(null); setSegmentInspector(null); } }
  async function refreshTtsSetup(options?: { syncProvider?: boolean }) { const [nextTts, nextSetup, nextProviders] = await Promise.all([getTtsSettings(), getKokoroSetup(), getTtsProviders()]); setTts(nextTts); setKokoroSetup(nextSetup); setTtsProviders(nextProviders); if (options?.syncProvider || nextTts.provider === "kokoro") setSelectedTtsProvider(nextTts.provider); }

  async function create(event: FormEvent) { event.preventDefault(); if (!title.trim() || !rights) return; setBusy(true); try { const created = await createProject({ title: title.trim(), author: author.trim() || undefined, rightsStatus: "declared" }); setProjects((current) => [created, ...current]); setTitle(""); setAuthor(""); setRights(false); await loadProject(created.id); setActiveSection("voice-engine"); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function chooseFile(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (!file || !selectedProjectId) return; setBusy(true); setError(null); setNotice(null); setImportJob(null); setActiveSection("manuscript"); try { const imported = await importSource(selectedProjectId, file); setImportJob(imported); setNotice("Manuscript import is running locally. Large PDFs and OCR can take a few minutes."); if (imported.status === "succeeded") { await refreshImportedSource(selectedProjectId); setNotice("Manuscript normalized locally. Inspect the preview, then extract structure."); setActiveSection("manuscript"); setBusy(false); } else if (!["queued", "running"].includes(imported.status)) setBusy(false); } catch (cause) { setError(messageOf(cause)); setBusy(false); } finally { event.target.value = ""; } }
  async function extract() { if (!selectedProjectId) return; setBusy(true); try { const extraction = await extractStructure(selectedProjectId); await waitFor(extraction.id, selectedProjectId); const [nextChapters, nextWarnings, nextQuality, nextIssues, nextCharacters, nextAttributions] = await Promise.all([listChapters(selectedProjectId), listStructureWarnings(selectedProjectId), getStructureQuality(selectedProjectId), listIssues(selectedProjectId), listCharacters(selectedProjectId), listSpeakerAttributions(selectedProjectId)]); setChapters(nextChapters); setStructureWarnings(nextWarnings); setStructureQuality(nextQuality); setIssues(nextIssues); setCharacters(nextCharacters); setSpeakerAttributions(nextAttributions); setActiveSection("structure"); setNotice("Structure and cast draft extracted. Review cast and voices before producing chapters."); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function openChapter(chapter: Chapter) { if (!selectedProjectId) return; setSelectedChapter(chapter); setStatus(null); setReadiness(null); setRenderCompare(null); setSegmentInspector(null); try { const nextScenes = await listScenes(chapter.id); const nextSegments = nextScenes[0] ? await listSegments(nextScenes[0].id) : []; setScenes(nextScenes); setSegments(nextSegments); await refreshProduction(selectedProjectId, chapter.id); await refreshRenderQueue(selectedProjectId, chapter.id); await refreshSoundDesign(selectedProjectId, chapter.id); if (nextSegments[0]) await inspectSegment(nextSegments[0].id); setActiveSection("produce"); } catch (cause) { setScenes([]); setSegments([]); setRenderQueue([]); setSoundCues([]); setError(messageOf(cause)); } }
  async function saveEdit() { if (!editing || !draft.trim()) return; setBusy(true); try { const updated = await updateSegment(editing.id, draft.trim()); setSegments((current) => current.map((item) => item.id === updated.id ? updated : item)); setEditing(null); setNotice(`Revision r${updated.revision} saved. It will be rendered during the next chapter run.`); if (selectedProjectId && selectedChapter) await refreshProduction(selectedProjectId, selectedChapter.id); if (segmentInspector?.segment.id === updated.id) await inspectSegment(updated.id); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function toggleSegmentLock(segment: Segment) { try { const updated = await setStructureLock("segment", segment.id, { locked: !segment.userLocked, reason: segment.userLocked ? null : "Locked in Structure Editor" }) as Segment; setSegments((current) => current.map((item) => item.id === updated.id ? updated : item)); } catch (cause) { setError(messageOf(cause)); } }
  async function splitAtReadingBreak(segment: Segment) { const midpoint = Math.floor(segment.textContent.length / 2); const before = segment.textContent.lastIndexOf(" ", midpoint); const after = segment.textContent.indexOf(" ", midpoint); const splitOffset = before > 24 ? before : after > 0 ? after : midpoint; try { await splitSegment(segment.id, splitOffset); setSegments(await listSegments(segment.sceneId)); setSegmentInspector(null); setNotice("Segment split. Review both resulting segments before production."); } catch (cause) { setError(messageOf(cause)); } }
  async function mergeWithNext(segment: Segment, nextSegment?: Segment) { if (!nextSegment) return; try { await mergeSegment(segment.id, nextSegment.id); setSegments(await listSegments(segment.sceneId)); setSegmentInspector(null); setNotice("Segments merged and marked for review."); } catch (cause) { setError(messageOf(cause)); } }
  async function saveTts() { if (!tts) return; setBusy(true); try { const saved = await saveTtsSettings({ provider: selectedTtsProvider, setupMode: selectedTtsProvider === "kokoro" ? tts.setupMode : selectedTtsProvider === "piper" ? "local_cli" : selectedTtsProvider === "xtts_v2" ? "coqui_local" : null, executable: tts.executable, runtimeRoot: tts.runtimeRoot, pythonPath: tts.pythonPath, modelPath: tts.modelPath, voicesDataPath: tts.voicesDataPath, voiceRegistryPath: tts.voiceRegistryPath, piperModelPath: tts.piperModelPath, piperConfigPath: tts.piperConfigPath, referenceVoicePath: tts.referenceVoicePath, referenceVoiceConsent: tts.referenceVoiceConsent, language: tts.language }); setTts(saved); setSelectedTtsProvider(saved.provider); await testTtsSettings(); await refreshTtsSetup({ syncProvider: true }); setNotice("Local voice engine settings saved and validated."); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function installLocalAi(item: LocalAiCatalogItem) { setBusy(true); try { const next = await installLocalAiModel(item.modelKey, { confirmNetworkDownload: true, confirmThirdPartyLicense: true, confirmSystemInstall: true, repair: item.status === "failed" }); setLocalAiJob(next); setLocalAiInstallJob(null); setNotice(`${item.displayName} setup is running locally.`); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function verifyLocalAi(item: LocalAiCatalogItem) { setBusy(true); try { await verifyLocalAiModel(item.modelKey); await refreshLocalAi(); setNotice(`${item.displayName} health was checked.`); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function resolveCleaningIssue(issue: TextCleanlinessIssue) { try { const updated = await updateCleaningIssue(issue.id, { status: "resolved", resolvedByUser: true }); setCleaningIssues((current) => current.map((item) => item.id === updated.id ? updated : item)); } catch (cause) { setError(messageOf(cause)); } }
  async function startKokoroSetup() { setSelectedTtsProvider("kokoro"); setBusy(true); try { const next = await installKokoroSetup({ confirmNetworkDownload: true, confirmThirdPartyLicense: true, repair: kokoroSetup?.state === "failed" || kokoroSetup?.state === "incomplete" }); setSetupJob(next); setNotice("Kokoro setup is running locally. This can take several minutes on the first run."); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function addVoice(event: FormEvent) { event.preventDefault(); if (!selectedProjectId || !voiceName.trim() || !providerVoiceId.trim()) return; try { const voice = await createVoice(selectedProjectId, { name: voiceName.trim(), backend: selectedTtsProvider, providerVoiceId: providerVoiceId.trim() }); setVoices((current) => [...current, voice]); setVoiceName(""); setProviderVoiceId(""); } catch (cause) { setError(messageOf(cause)); } }
  async function addCharacter(event: FormEvent) { event.preventDefault(); if (!selectedProjectId || !characterName.trim()) return; try { const item = await createCharacter(selectedProjectId, { displayName: characterName.trim(), aliases: csvList(characterAliases), traits: csvList(characterTraits), roleType: "major" }); setCharacters((current) => [...current, item].sort((a, b) => a.displayName.localeCompare(b.displayName))); setCharacterName(""); setCharacterAliases(""); setCharacterTraits(""); } catch (cause) { setError(messageOf(cause)); } }
  async function saveCharacter(characterId: string, payload: Parameters<typeof updateCharacter>[1]) { try { const item = await updateCharacter(characterId, payload); setCharacters((current) => current.map((candidate) => candidate.id === item.id ? item : candidate)); setNotice("Character bible updated."); } catch (cause) { setError(messageOf(cause)); } }
  async function mergeCast(source: Character, targetId: string) { if (!selectedProjectId || !targetId || targetId === source.id) return; try { await mergeCharacter(targetId, source.id, `Merged from Character Bible on ${new Date().toISOString()}`); setCharacters(await listCharacters(selectedProjectId)); setNotice("Character records merged; source remains linked for traceability."); } catch (cause) { setError(messageOf(cause)); } }
  async function splitCast(character: Character) { if (!selectedProjectId) return; const displayName = window.prompt("New character name", `${character.displayName} variant`); if (!displayName?.trim()) return; try { await splitCharacter(character.id, { displayName: displayName.trim(), reason: `Split from ${character.displayName} in Character Bible` }); setCharacters(await listCharacters(selectedProjectId)); setNotice("Character split created with history on both records."); } catch (cause) { setError(messageOf(cause)); } }
  async function runCastReview(useLocalLlm = false) { if (!selectedProjectId) return; setBusy(true); try { const next = await runSpeakerAttribution(selectedProjectId, { useLocalLlm }); await waitFor(next.id, selectedProjectId); const [nextAttributions, nextCharacters] = await Promise.all([listSpeakerAttributions(selectedProjectId), listCharacters(selectedProjectId)]); setSpeakerAttributions(nextAttributions); setCharacters(nextCharacters); setNotice(useLocalLlm ? "Cast review refreshed with local Ollama speaker assistance." : "Cast review refreshed from the current Structure & Cast Draft."); if (selectedChapter) await refreshProduction(selectedProjectId, selectedChapter.id); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function saveAttribution(attributionId: string, payload: Parameters<typeof updateSpeakerAttribution>[1]) { try { const item = await updateSpeakerAttribution(attributionId, payload); setSpeakerAttributions((current) => current.map((candidate) => candidate.id === item.id ? item : candidate)); setNotice("Speaker attribution updated."); if (selectedProjectId && selectedChapter) await refreshProduction(selectedProjectId, selectedChapter.id); } catch (cause) { setError(messageOf(cause)); } }
  async function ensureKokoroVoice(voiceId: string) { if (!selectedProjectId) return null; const existing = voices.find((voice) => voice.providerVoiceId === voiceId && voice.backend === "kokoro"); if (existing) return existing; const created = await createVoice(selectedProjectId, { name: `Kokoro ${voiceId}`, backend: "kokoro", providerVoiceId: voiceId }); setVoices((current) => [...current, created]); return created; }
  async function previewKokoroVoice(voiceId: string) { try { const voice = await ensureKokoroVoice(voiceId); if (voice) await playPreview(voice.id); } catch (cause) { setError(messageOf(cause)); } }
  async function selectKokoroNarrator(voiceId: string) { try { const voice = await ensureKokoroVoice(voiceId); if (voice) await selectNarrator(voice.id); } catch (cause) { setError(messageOf(cause)); } }
  async function removeVoice(voiceId: string) { try { await deleteVoice(voiceId); setVoices((current) => current.filter((voice) => voice.id !== voiceId)); } catch (cause) { setError(messageOf(cause)); } }
  async function selectNarrator(voiceId: string) { if (!selectedProjectId) return; try { const next = await saveProductionSettings(selectedProjectId, { narratorVoiceProfileId: voiceId, defaultDirection: production?.defaultDirection ?? directionFor("project", selectedProjectId) }); setProduction(next); if (selectedChapter) await refreshProduction(selectedProjectId, selectedChapter.id); } catch (cause) { setError(messageOf(cause)); } }
  async function playPreview(voiceId: string) { if (!selectedProjectId) return; try { const preview = await previewVoice(selectedProjectId, voiceId, directionFor("project", selectedProjectId)); const player = new Audio(assetUrl(preview.audioUrl)); await player.play(); } catch (cause) { setError(messageOf(cause)); } }
  async function setOverride(segmentId: string, voiceProfileId: string) { if (!selectedProjectId) return; try { await saveSegmentOverride(selectedProjectId, segmentId, { voiceProfileId: voiceProfileId || null }); setNotice("Segment voice override saved for future production."); } catch (cause) { setError(messageOf(cause)); } }
  async function inferDirections() { if (!selectedProjectId) return; setBusy(true); try { const next = await inferSegmentDirections(selectedProjectId); await waitFor(next.id, selectedProjectId); setSegmentDirections(await listSegmentDirections(selectedProjectId)); setNotice("Direction inference completed."); if (selectedChapter) await refreshProduction(selectedProjectId, selectedChapter.id); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function saveDirection(segmentId: string, direction: Direction) { if (!selectedProjectId) return; try { const item = await saveSegmentDirection(selectedProjectId, segmentId, { direction, userLocked: true }); setSegmentDirections((current) => [...current.filter((candidate) => candidate.segmentId !== segmentId), item]); setNotice("Segment direction saved; affected renders will refresh on the next run."); if (selectedChapter) await refreshProduction(selectedProjectId, selectedChapter.id); } catch (cause) { setError(messageOf(cause)); } }
  async function produce(force = false) { if (!selectedProjectId || !selectedChapter) return; try { setActiveSection("produce"); setRenderQueue([]); setJob(await produceChapter(selectedProjectId, selectedChapter.id, force)); setNotice("Chapter production is running locally."); } catch (cause) { setError(messageOf(cause)); } }
  async function chooseSoundFile(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (!file || !selectedProjectId) return; setBusy(true); try { const asset = await uploadSoundAsset(selectedProjectId, file, soundAssetType); setSoundAssets((current) => [asset, ...current]); setSelectedSoundAssetId(asset.id); setNotice("Sound asset imported locally. Assign it to a scene before assembling a mix."); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); event.target.value = ""; } }
  async function addSoundCue() { if (!selectedProjectId || !selectedChapter || !currentSceneId || !activeSoundAsset) return; try { const cue = await createSoundCue(selectedProjectId, { sceneId: currentSceneId, assetId: activeSoundAsset.id, cueType: soundCueType, gainDb: soundGain, fadeInMs: 700, fadeOutMs: 900, ducking: true, renderMode: soundRenderMode, noSfx: false }); setSoundCues((current) => [...current, cue]); setNotice("Sound cue assigned. Assemble a light or dramatized mix when narration is current."); } catch (cause) { setError(messageOf(cause)); } }
  async function assembleSound(mode: "clean" | "light" | "dramatized") { if (!selectedProjectId || !selectedChapter) return; setBusy(true); try { const render = await assembleChapter(selectedProjectId, selectedChapter.id, mode); await refreshProduction(selectedProjectId, selectedChapter.id); setStatus((current) => current ? { ...current, activeRender: render } : current); await refreshSoundDesign(selectedProjectId, selectedChapter.id); setNotice(mode === "clean" ? "Clean narration render assembled." : `${mode} chapter mix assembled.`); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function runReadinessReport() { if (!selectedProjectId) return; setBusy(true); try { const report = await runReadiness(selectedProjectId, selectedChapter?.id); setReadiness(report); setIssues(await listIssues(selectedProjectId)); setNotice("Readiness report updated."); } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); } }
  async function setReadinessIssue(issueId: string, status: "resolved" | "ignored" | "locked") { try { await updateIssue(issueId, { status }); if (selectedProjectId) { setReadiness(await runReadiness(selectedProjectId, selectedChapter?.id)); setIssues(await listIssues(selectedProjectId)); } } catch (cause) { setError(messageOf(cause)); } }
  async function openIssue(issue: Issue) { setActiveIssue(issue); try { setComments(await listComments(issue.id)); } catch (cause) { setError(messageOf(cause)); } }
  async function comment(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); if (!activeIssue || !String(form.get("comment") || "").trim()) return; try { const added = await addComment(activeIssue.id, String(form.get("comment"))); setComments((current) => [...current, added]); event.currentTarget.reset(); } catch (cause) { setError(messageOf(cause)); } }
  async function resolveIssue(issue: Issue) { try { const updated = await updateIssue(issue.id, { status: "resolved" }); setIssues((current) => current.map((item) => item.id === updated.id ? updated : item)); if (activeIssue?.id === updated.id) setActiveIssue(updated); } catch (cause) { setError(messageOf(cause)); } }
  async function patch(issue: Issue) { if (!selectedProjectId || !issue.segmentId) return; try { await patchSegment(selectedProjectId, issue.segmentId, { issueId: issue.id }); setNotice("Segment patched and its chapter reassembled."); if (selectedChapter) await refreshProduction(selectedProjectId, selectedChapter.id); await inspectSegment(issue.segmentId); setReadiness(await runReadiness(selectedProjectId, selectedChapter?.id)); setIssues(await listIssues(selectedProjectId)); } catch (cause) { setError(messageOf(cause)); } }
  async function exportSelected(format: "wav" | "mp3") { if (!selectedProjectId || !selectedExportIds.length) return; try { const item = await createExport(selectedProjectId, format, selectedExportIds, { audioVariant: exportAudioVariant, title: exportTitle.trim() || undefined, author: exportAuthor.trim() || undefined, album: exportAlbum.trim() || undefined, publisher: exportPublisher.trim() || undefined, language: exportLanguage.trim() || undefined, coverImagePath: exportCoverPath.trim() || undefined }); setExports((current) => [item, ...current]); setActiveSection("export"); setNotice("Export package created. Download the ZIP from export history."); } catch (cause) { setError(messageOf(cause)); } }

  return <div className="desk-shell"><div className="grain" aria-hidden="true" />
    <StudioHero tts={tts} setupJob={setupJob} job={job} selectedChapter={selectedChapter} status={status} />
    {error ? <InlineNotice tone="error">{error}</InlineNotice> : null}{notice ? <InlineNotice tone="success">{notice}</InlineNotice> : null}
    <StudioShell steps={workflowSteps} activeStep={activeSection} onStepChange={setActiveSection}>
      {activeSection === "project" ? (
        <section className="workspace">
          <NewProjectPanel
            title={title}
            author={author}
            rights={rights}
            busy={busy}
            onTitleChange={setTitle}
            onAuthorChange={setAuthor}
            onRightsChange={setRights}
            onSubmit={create}
          />
          <ProjectLibraryPanel projects={projects} selectedProjectId={selectedProjectId} onOpen={(projectId) => void loadProject(projectId)} />
        </section>
      ) : null}
    {project ? <>
      {activeSection === "voice-engine" ? <section className="studio-section settings" aria-labelledby="voice-engine-title"><div><p className="eyebrow">01 / Voice engine</p><h2 id="voice-engine-title">Choose a voice engine</h2><p className="lede">Mock is built in. Kokoro, Piper, and consent-gated XTTS-v2 run locally; no manuscript text or generated audio leaves this machine.</p></div><div className="studio-card"><div className="field-row"><label>Voice engine<select aria-label="Voice engine" value={selectedTtsProvider} onChange={(event) => { const provider = event.target.value as TtsProvider; setSelectedTtsProvider(provider); setTts((current) => ({ ...(current ?? emptyTts(provider)), provider, setupMode: provider === "kokoro" ? "managed_onnx" : provider === "piper" ? "local_cli" : provider === "xtts_v2" ? "coqui_local" : null })); }}><option value="mock">Mock (silent workflow audio)</option><option value="kokoro">Kokoro managed preset voice system</option><option value="piper">Piper local fallback</option><option value="xtts_v2">XTTS-v2 opt-in reference voice</option></select></label></div><ProviderStatus providers={ttsProviders} active={selectedTtsProvider} />{selectedTtsProvider === "mock" ? <><button type="button" onClick={() => void saveTts()} disabled={busy}>{uiCopy.startWithMockVoiceEngine}</button><p className={tts?.ready && tts.provider === "mock" ? "capability ready" : "capability"}>{tts?.ready && tts.provider === "mock" ? "Mock voice engine is ready. It creates silent workflow audio." : tts?.message || activeProviderInfo?.message || "Mock is built in and needs no download."}</p></> : selectedTtsProvider === "kokoro" ? <div className="kokoro-setup-card"><div><strong>Set up Kokoro preset voices</strong><p>{kokoroSetup?.message || "Echodraft will create a local Python runtime, download Kokoro ONNX model files, build the preset voice list, and validate a local preview."}</p><small>Runtime: {kokoroSetup?.runtimeRoot || ".echodraft/kokoro/managed-onnx-v1"}</small></div><button type="button" onClick={() => void startKokoroSetup()} disabled={busy || setupJob?.status === "running"}>{kokoroSetup?.state === "failed" || kokoroSetup?.state === "incomplete" ? "Repair setup" : kokoroSetup?.ready ? "Repair setup" : "Download and install Kokoro locally"}</button>{setupJob && ["queued", "running"].includes(setupJob.status) ? <p className="capability">Step {String(setupJob.progress.step ?? "?")}/{String(setupJob.progress.total ?? "?")}: {String(setupJob.progress.message ?? setupJob.progress.phase ?? "working")}</p> : null}<div className="setup-steps">{(kokoroSetup?.steps ?? []).map((step) => <span key={step.phase} className={`setup-step ${step.status}`}>{step.label}</span>)}</div>{kokoroSetup?.nextAction ? <p className={kokoroSetup.ready ? "capability ready" : "capability"}>{kokoroSetup.nextAction}</p> : null}{kokoroVoices.length ? <div className="voice-picker"><strong>Available Kokoro preset voices</strong>{kokoroVoices.slice(0, 12).map((voiceId) => { const profile = voices.find((voice) => voice.providerVoiceId === voiceId && voice.backend === "kokoro"); return <article className="voice-card" key={voiceId}><div><strong>{voiceId}</strong><small>{profile ? "Preset profile ready" : "Available preset voice"}</small></div><span><button type="button" className="small-button" onClick={() => void previewKokoroVoice(voiceId)}>Preview</button><button type="button" className="small-button" onClick={() => void selectKokoroNarrator(voiceId)}>{profile && narrator?.id === profile.id ? "Narrator" : "Set narrator"}</button></span></article>; })}</div> : null}<button type="button" className="small-button" onClick={() => setShowAdvancedTts((current) => !current)}>Advanced: use a custom voice adapter</button>{showAdvancedTts ? <div className="advanced-tts"><p className="capability">Compatibility mode for a prebuilt wrapper. Most users should use managed Kokoro setup above.</p><label>Executable<input value={tts?.executable ?? ""} onChange={(event) => setTts((current) => ({ ...(current ?? emptyTts("kokoro")), setupMode: "custom_adapter", executable: event.target.value }))} /></label><label>Model path<input value={tts?.modelPath ?? ""} onChange={(event) => setTts((current) => ({ ...(current ?? emptyTts("kokoro")), setupMode: "custom_adapter", modelPath: event.target.value }))} /></label><label>Voice registry<input value={tts?.voiceRegistryPath ?? ""} onChange={(event) => setTts((current) => ({ ...(current ?? emptyTts("kokoro")), setupMode: "custom_adapter", modelPath: tts?.modelPath, voiceRegistryPath: event.target.value }))} /></label><button type="button" onClick={() => void saveTts()} disabled={busy}>Save custom adapter</button></div> : null}</div> : <LocalProviderSetup provider={selectedTtsProvider} tts={tts ?? emptyTts(selectedTtsProvider)} onChange={setTts} onSave={saveTts} busy={busy} />}<details className="advanced-local-setup"><summary>Advanced local capability setup</summary><ModelCenter catalog={localAiCatalog} job={localAiJob} installJob={localAiInstallJob} busy={busy} onInstall={installLocalAi} onVerify={verifyLocalAi} /></details></div></section> : null}
      {activeSection === "voices-cast" ? (
        <VoiceBiblePanel
          voices={voices}
          narrator={narrator}
          voiceName={voiceName}
          providerVoiceId={providerVoiceId}
          characters={characters}
          attributions={speakerAttributions}
          pronunciations={pronunciations}
          characterName={characterName}
          characterAliases={characterAliases}
          characterTraits={characterTraits}
          busy={busy}
          onVoiceNameChange={setVoiceName}
          onProviderVoiceIdChange={setProviderVoiceId}
          onAddVoice={addVoice}
          onPreviewVoice={(voiceId) => void playPreview(voiceId)}
          onSelectNarrator={(voiceId) => void selectNarrator(voiceId)}
          onRemoveVoice={(voiceId) => void removeVoice(voiceId)}
          onCharacterNameChange={setCharacterName}
          onCharacterAliasesChange={setCharacterAliases}
          onCharacterTraitsChange={setCharacterTraits}
          onAddCharacter={addCharacter}
          onSaveCharacter={saveCharacter}
          onMergeCharacter={mergeCast}
          onSplitCharacter={splitCast}
          onRunCastReview={runCastReview}
          onSaveAttribution={saveAttribution}
          onAddPronunciation={async (value) => {
            const parts = value.includes("->") ? value.split("->") : value.split("→");
            const [term, replacementText] = parts.map((item) => item.trim());
            const item = await createPronunciation(project.id, term, replacementText);
            setPronunciations((current) => [...current, item]);
          }}
        />
      ) : null}
      {activeSection === "manuscript" ? (
        <ManuscriptIntakePanel
          busy={busy}
          importJob={importJob}
          source={source}
          pages={sourcePages}
          cleaningIssues={cleaningIssues}
          onChooseFile={chooseFile}
          onExtract={() => void extract()}
          onReparse={() => {
            if (selectedProjectId) void reparseSource(selectedProjectId);
          }}
          onResolveCleaningIssue={resolveCleaningIssue}
        />
      ) : null}
      {(activeSection === "structure" || activeSection === "produce") ? (
        <StoryMapPanel
          chapters={chapters}
          scenes={scenes}
          segments={segments}
          selectedChapter={selectedChapter}
          editing={editing}
          draft={draft}
          voices={voices}
          directions={segmentDirections}
          supportedDirection={(ttsProviders.find((item) => item.provider === tts?.provider)?.capabilities as { direction?: string[] } | undefined)?.direction ?? null}
          warnings={structureWarnings}
          issues={issues}
          quality={structureQuality}
          status={status}
          job={job}
          provider={tts?.provider}
          renderQueue={renderQueue}
          renderCompare={renderCompare}
          soundAssets={soundAssets}
          soundCues={soundCues}
          selectedSoundAssetId={activeSoundAsset?.id ?? ""}
          currentSceneId={currentSceneId}
          soundAssetType={soundAssetType}
          soundCueType={soundCueType}
          soundRenderMode={soundRenderMode}
          soundGain={soundGain}
          busy={busy}
          onGoManuscript={() => setActiveSection("manuscript")}
          onInferDirections={() => void inferDirections()}
          onOpenChapter={(chapter) => void openChapter(chapter)}
          onOpenScene={(scene) => void listSegments(scene.id).then(setSegments)}
          onStartEdit={(segment) => {
            setEditing(segment);
            setDraft(segment.textContent);
          }}
          onDraftChange={setDraft}
          onCancelEdit={() => setEditing(null)}
          onSaveEdit={() => void saveEdit()}
          onToggleLock={(segment) => void toggleSegmentLock(segment)}
          onSplit={(segment) => void splitAtReadingBreak(segment)}
          onMerge={(segment, nextSegment) => void mergeWithNext(segment, nextSegment)}
          onInspect={(segmentId) => void inspectSegment(segmentId)}
          onOverride={(segmentId, voiceId) => void setOverride(segmentId, voiceId)}
          onSaveDirection={saveDirection}
          onProduce={(force = false) => void produce(force)}
          onAssetType={setSoundAssetType}
          onAssetSelect={setSelectedSoundAssetId}
          onCueType={setSoundCueType}
          onRenderMode={setSoundRenderMode}
          onGain={setSoundGain}
          onSoundFile={chooseSoundFile}
          onAddCue={addSoundCue}
          onAssemble={assembleSound}
        />
      ) : null}
      {activeSection === "review-patch" ? (
        <ReviewPatchPanel
          selectedChapter={selectedChapter}
          segments={segments}
          status={status}
          job={job}
          provider={tts?.provider}
          readiness={readiness}
          busy={busy}
          inspector={segmentInspector}
          comparison={renderCompare}
          issues={issues}
          activeIssue={activeIssue}
          comments={comments}
          onGoProduce={() => setActiveSection("produce")}
          onRunReadiness={runReadinessReport}
          onSetReadinessIssue={setReadinessIssue}
          onInspect={(segmentId) => void inspectSegment(segmentId)}
          onOpenIssue={(issue) => void openIssue(issue)}
          onPatch={(issue) => void patch(issue)}
          onResolveIssue={(issue) => void resolveIssue(issue)}
          onComment={comment}
        />
      ) : null}
      {activeSection === "export" ? (
        <ExportPanel
          project={project}
          chapters={chapters}
          selectedChapterIds={selectedExportIds}
          audioVariant={exportAudioVariant}
          title={exportTitle}
          author={exportAuthor}
          album={exportAlbum}
          publisher={exportPublisher}
          language={exportLanguage}
          coverPath={exportCoverPath}
          exports={exports}
          onGoStructure={() => setActiveSection("structure")}
          onSelectionChange={setSelectedExportIds}
          onAudioVariantChange={setExportAudioVariant}
          onTitleChange={setExportTitle}
          onAuthorChange={setExportAuthor}
          onAlbumChange={setExportAlbum}
          onPublisherChange={setExportPublisher}
          onLanguageChange={setExportLanguage}
          onCoverPathChange={setExportCoverPath}
          onExport={(format) => void exportSelected(format)}
        />
      ) : null}
    </> : null}
    </StudioShell>
  </div>;
}
