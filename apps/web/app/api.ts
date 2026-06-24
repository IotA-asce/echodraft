export type Project = { id: string; title: string; author: string | null; status: string; artifactPath: string; createdAt: string };
export type Job = { id: string; status: "queued" | "running" | "succeeded" | "failed" | "cancelled"; errorMessage?: string | null; progress: Record<string, unknown> };
export type ParserWarning = { severity: string; sourceRange?: string | null; message: string; suggestedAction?: string | null };
export type SourceDocument = { originalFilename: string; status: string; parserVersion: string; preview?: string | null; warnings: ParserWarning[] };
export type Chapter = { id: string; title?: string | null; status: string; confidence: number };
export type Scene = { id: string; status: string; confidence: number };
export type Segment = { id: string; textContent: string; revision: number; status: string; speakerCandidate?: string | null };
export type Direction = { scopeType: string; scopeId: string; pace: number; intensity: number; tone: string; stylePrompt?: string | null; emphasis: boolean; whisper: boolean; noSfx: boolean };
export type TtsSettings = { provider: "mock" | "kokoro"; executable?: string | null; modelPath?: string | null; voiceRegistryPath?: string | null; ready: boolean; message?: string | null; availableVoices: string[] };
export type VoiceProfile = { id: string; projectId: string; name: string; backend: string; providerVoiceId: string; stylePrompt?: string | null };
export type ProductionSettings = { projectId: string; narratorVoiceProfileId?: string | null; defaultDirection?: Direction | null };
export type SegmentOverride = { segmentId: string; voiceProfileId?: string | null; direction?: Direction | null };
export type SegmentRender = { id: string; segmentId: string; status: string; audioPath: string; audioUrl?: string | null; durationMs: number; parentRenderId?: string | null };
export type ChapterRender = { id: string; chapterId: string; status: string; speechPath: string; audioUrl?: string | null; durationMs: number; renderMode: string };
export type ProductionStatus = { chapterId: string; ready: boolean; reason?: string | null; totalSegments: number; currentSegments: number; activeRender?: ChapterRender | null };
export type Issue = { id: string; projectId: string; chapterId?: string | null; segmentId?: string | null; severity: string; category: string; title: string; description: string; status: string };
export type Comment = { id: string; issueId: string; body: string; author: string; createdAt: string };
export type ExportPackage = { id: string; projectId: string; format: string; status: string; outputPath: string; manifestPath: string; archivePath?: string | null; downloadUrl?: string | null };
export type Character = { id: string; projectId: string; displayName: string; roleType: string; notes?: string | null };
export type Pronunciation = { id: string; term: string; phonetic?: string | null; replacementText?: string | null };

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const assetUrl = (path?: string | null) => path ? `${apiUrl}${path}` : undefined;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = options?.body instanceof FormData ? options?.headers : { "Content-Type": "application/json", ...options?.headers };
  const response = await fetch(`${apiUrl}${path}`, { ...options, headers });
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? "The local studio could not complete that request.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
const json = (method: string, body?: object): RequestInit => ({ method, body: body ? JSON.stringify(body) : undefined });

export const listProjects = () => request<Project[]>("/api/v1/projects");
export const createProject = (payload: { title: string; author?: string; rightsStatus: "declared" }) => request<Project>("/api/v1/projects", json("POST", payload));
export const getJob = (id: string) => request<Job>(`/api/v1/jobs/${id}`);
export const getSource = (projectId: string) => request<SourceDocument>(`/api/v1/projects/${projectId}/source`);
export async function importSource(projectId: string, file: File) { const form = new FormData(); form.set("file", file); form.set("rightsAcknowledged", "true"); return request<Job>(`/api/v1/projects/${projectId}/source/import`, { method: "POST", body: form }); }
export const reparseSource = (projectId: string) => request<Job>(`/api/v1/projects/${projectId}/source/reparse`, json("POST", { parserVersion: "ingestion-0.1.0" }));
export const extractStructure = (projectId: string) => request<Job>(`/api/v1/projects/${projectId}/structure/extract`, json("POST", { maxSegmentChars: 600 }));
export const listChapters = (projectId: string) => request<Chapter[]>(`/api/v1/projects/${projectId}/chapters`);
export const listScenes = (chapterId: string) => request<Scene[]>(`/api/v1/chapters/${chapterId}/scenes`);
export const listSegments = (sceneId: string) => request<Segment[]>(`/api/v1/scenes/${sceneId}/segments`);
export const updateSegment = (id: string, textContent: string) => request<Segment>(`/api/v1/segments/${id}`, json("PATCH", { textContent }));

export const getTtsSettings = () => request<TtsSettings>("/api/v1/settings/tts");
export const saveTtsSettings = (payload: Omit<TtsSettings, "ready" | "message" | "availableVoices">) => request<TtsSettings>("/api/v1/settings/tts", json("PUT", payload));
export const testTtsSettings = () => request<TtsSettings>("/api/v1/settings/tts/test", json("POST", {}));
export const listVoices = (projectId: string) => request<VoiceProfile[]>(`/api/v1/projects/${projectId}/voices`);
export const createVoice = (projectId: string, payload: { name: string; backend: string; providerVoiceId: string; stylePrompt?: string }) => request<VoiceProfile>(`/api/v1/projects/${projectId}/voices`, json("POST", payload));
export const deleteVoice = (voiceId: string) => request<void>(`/api/v1/voices/${voiceId}`, { method: "DELETE" });
export const previewVoice = (projectId: string, voiceProfileId: string, direction: Direction) => request<{ assetPath: string; audioUrl?: string }>(`/api/v1/projects/${projectId}/voices/preview`, json("POST", { text: "This is a local Echodraft voice preview.", voiceProfileId, direction }));
export const listCharacters = (projectId: string) => request<Character[]>(`/api/v1/projects/${projectId}/characters`);
export const createCharacter = (projectId: string, displayName: string) => request<Character>(`/api/v1/projects/${projectId}/characters`, json("POST", { displayName }));
export const listPronunciations = (projectId: string) => request<Pronunciation[]>(`/api/v1/projects/${projectId}/pronunciations`);
export const createPronunciation = (projectId: string, term: string, replacementText?: string) => request<Pronunciation>(`/api/v1/projects/${projectId}/pronunciations`, json("POST", { term, replacementText }));
export const getProductionSettings = (projectId: string) => request<ProductionSettings>(`/api/v1/projects/${projectId}/production-settings`);
export const saveProductionSettings = (projectId: string, payload: { narratorVoiceProfileId?: string | null; defaultDirection?: Direction | null }) => request<ProductionSettings>(`/api/v1/projects/${projectId}/production-settings`, json("PUT", payload));
export const getSegmentOverride = (projectId: string, segmentId: string) => request<SegmentOverride>(`/api/v1/projects/${projectId}/segments/${segmentId}/production-override`);
export const saveSegmentOverride = (projectId: string, segmentId: string, payload: { voiceProfileId?: string | null; direction?: Direction | null }) => request<SegmentOverride>(`/api/v1/projects/${projectId}/segments/${segmentId}/production-override`, json("PUT", payload));
export const getProductionStatus = (projectId: string, chapterId: string) => request<ProductionStatus>(`/api/v1/projects/${projectId}/chapters/${chapterId}/production-status`);
export const produceChapter = (projectId: string, chapterId: string, force = false) => request<Job>(`/api/v1/projects/${projectId}/chapters/${chapterId}/produce?force=${force}`, json("POST"));
export const listChapterRenders = (projectId: string, chapterId: string) => request<ChapterRender[]>(`/api/v1/projects/${projectId}/chapters/${chapterId}/renders`);
export const listIssues = (projectId: string) => request<Issue[]>(`/api/v1/projects/${projectId}/issues`);
export const updateIssue = (issueId: string, payload: { status?: string; severity?: string }) => request<Issue>(`/api/v1/issues/${issueId}`, json("PATCH", payload));
export const listComments = (issueId: string) => request<Comment[]>(`/api/v1/issues/${issueId}/comments`);
export const addComment = (issueId: string, body: string) => request<Comment>(`/api/v1/issues/${issueId}/comments`, json("POST", { body }));
export const patchSegment = (projectId: string, segmentId: string, payload: { textContent?: string; issueId?: string; voiceProfileId: string; direction: Direction }) => request<unknown>(`/api/v1/projects/${projectId}/segments/${segmentId}/patch`, json("POST", payload));
export const createExport = (projectId: string, format: "wav" | "mp3", chapterIds: string[]) => request<ExportPackage>(`/api/v1/projects/${projectId}/exports`, json("POST", { format, chapterIds }));
export const listExports = (projectId: string) => request<ExportPackage[]>(`/api/v1/projects/${projectId}/exports`);
