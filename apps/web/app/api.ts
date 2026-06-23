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

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? "The local studio could not complete that request.");
  }
  return response.json() as Promise<T>;
}

export const listProjects = () => request<Project[]>("/api/v1/projects");
export const createProject = (payload: CreateProjectPayload) =>
  request<Project>("/api/v1/projects", { method: "POST", body: JSON.stringify(payload) });
