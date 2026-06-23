"use client";

import { FormEvent, useEffect, useState } from "react";

import { createProject, listProjects, type Project } from "./api";

export function ProjectDashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [rightsAcknowledged, setRightsAcknowledged] = useState(false);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to load projects."))
      .finally(() => setLoading(false));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim() || !rightsAcknowledged) return;
    setCreating(true);
    setError(null);
    try {
      const project = await createProject({
        title: title.trim(),
        author: author.trim() || undefined,
        rightsStatus: "declared",
      });
      setProjects((current) => [project, ...current]);
      setTitle("");
      setAuthor("");
      setRightsAcknowledged(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create project.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="desk-shell">
      <div className="grain" aria-hidden="true" />
      <header className="masthead">
        <a className="wordmark" href="#top" aria-label="echodraft home">
          <span className="wordmark-mark">e</span>
          <span>echodraft</span>
        </a>
        <p>Local studio / foundations</p>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">The production desk</p>
          <h1>Stories, prepared<br />for their next voice.</h1>
          <p className="lede">Set up a private audiobook project. Files, renders, and working notes stay on this machine.</p>
        </div>
        <aside className="status-card" aria-label="Foundation status">
          <span className="pulse" />
          <div>
            <p>System status</p>
            <strong>Local runtime ready</strong>
          </div>
          <small>Jobs will appear here as the production pipeline comes online.</small>
        </aside>
      </section>

      <section className="workspace">
        <form className="create-card" onSubmit={handleSubmit}>
          <p className="eyebrow">New project</p>
          <h2>Open a fresh production file</h2>
          <label>
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="The Glass Orchard" required />
          </label>
          <label>
            Author <span>optional</span>
            <input value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="A. Writer" />
          </label>
          <label className="rights-check">
            <input type="checkbox" checked={rightsAcknowledged} onChange={(event) => setRightsAcknowledged(event.target.checked)} />
            <span>I confirm I have the rights to create this audiobook draft.</span>
          </label>
          <button type="submit" disabled={creating || !rightsAcknowledged || !title.trim()}>
            {creating ? "Opening project…" : "Create project"}
          </button>
        </form>

        <section className="project-panel" aria-live="polite">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Project library</p>
              <h2>Your local productions</h2>
            </div>
            <span>{projects.length.toString().padStart(2, "0")} projects</span>
          </div>
          {error ? <div className="notice error">{error}</div> : null}
          {loading ? <div className="notice">Opening the local archive…</div> : null}
          {!loading && !error && projects.length === 0 ? (
            <div className="empty-state"><span>01</span><p>Your first project will create a local workspace for source, structure, audio, exports, logs, and manifests.</p></div>
          ) : null}
          <ul className="project-list">
            {projects.map((project) => (
              <li key={project.id}>
                <div className="project-index">{project.title.slice(0, 1).toUpperCase()}</div>
                <div>
                  <strong>{project.title}</strong>
                  <p>{project.author || "Independent production"} · {project.status}</p>
                </div>
                <time dateTime={project.createdAt}>{new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(project.createdAt))}</time>
              </li>
            ))}
          </ul>
        </section>
      </section>
    </main>
  );
}
