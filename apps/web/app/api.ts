export type Project = {
  id: string;
  title: string;
  author: string | null;
  status: string;
  artifactPath: string;
  createdAt: string;
};

export type CreateProjectPayload = {
  title: string;
  author?: string;
  rightsStatus: "declared";
};
export type Job = { id: string; status: "queued" | "running" | "succeeded" | "failed" | "cancelled"; errorMessage?: string | null };
export type ParserWarning = { severity: string; sourceRange?: string | null; message: string; suggestedAction?: string | null };
export type SourceDocument = { originalFilename: string; status: string; parserVersion: string; preview?: string | null; warnings: ParserWarning[] };
export type Chapter = { id: string; title?: string | null; status: string; confidence: number };
export type Scene = { id: string; status: string; confidence: number };
export type Segment = { id: string; textContent: string; revision: number; status: string; speakerCandidate?: string | null };

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = options?.body instanceof FormData ? options?.headers : { "Content-Type": "application/json", ...options?.headers };
  const response = await fetch(`${apiUrl}${path}`, { ...options, headers });
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? "The local studio could not complete that request.");
  }
  return response.json() as Promise<T>;
}

export const listProjects = () => request<Project[]>("/api/v1/projects");
export const createProject = (payload: CreateProjectPayload) =>
  request<Project>("/api/v1/projects", { method: "POST", body: JSON.stringify(payload) });
export const getJob = (id: string) => request<Job>(`/api/v1/jobs/${id}`);
export const getSource = (projectId: string) => request<SourceDocument>(`/api/v1/projects/${projectId}/source`);
export async function importSource(projectId: string, file: File) {
  const form = new FormData(); form.set("file", file); form.set("rightsAcknowledged", "true");
  return request<Job>(`/api/v1/projects/${projectId}/source/import`, { method: "POST", body: form });
}
export const reparseSource = (projectId: string) => request<Job>(`/api/v1/projects/${projectId}/source/reparse`, { method: "POST", body: JSON.stringify({ parserVersion: "ingestion-0.1.0" }) });
export const extractStructure = (projectId: string) => request<Job>(`/api/v1/projects/${projectId}/structure/extract`, { method: "POST", body: JSON.stringify({ maxSegmentChars: 600 }) });
export const listChapters = (projectId: string) => request<Chapter[]>(`/api/v1/projects/${projectId}/chapters`);
export const listScenes = (chapterId: string) => request<Scene[]>(`/api/v1/chapters/${chapterId}/scenes`);
export const listSegments = (sceneId: string) => request<Segment[]>(`/api/v1/scenes/${sceneId}/segments`);
export const updateSegment = (id: string, textContent: string) => request<Segment>(`/api/v1/segments/${id}`, { method: "PATCH", body: JSON.stringify({ textContent }) });
