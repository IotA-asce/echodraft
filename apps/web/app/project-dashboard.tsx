"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";

import { createProject, getJob, getSource, importSource, listProjects, reparseSource, type Project, type SourceDocument } from "./api";

export function ProjectDashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [rightsAcknowledged, setRightsAcknowledged] = useState(false);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [source, setSource] = useState<SourceDocument | null>(null);
  const [importing, setImporting] = useState(false);

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
      setSelectedProjectId(project.id);
      setTitle("");
      setAuthor("");
      setRightsAcknowledged(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create project.");
    } finally {
      setCreating(false);
    }
  }

  async function waitForSource(jobId: string, projectId: string) {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const job = await getJob(jobId);
      if (job.status === "succeeded") { setSource(await getSource(projectId)); return; }
      if (job.status === "failed" || job.status === "cancelled") throw new Error(job.errorMessage || "Import failed.");
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error("Import is taking longer than expected. Check the job status and try again.");
  }

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedProjectId) return;
    setImporting(true); setError(null); setSource(null);
    try { const job = await importSource(selectedProjectId, file); await waitForSource(job.id, selectedProjectId); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Import failed."); }
    finally { setImporting(false); event.target.value = ""; }
  }

  async function handleReparse() {
    if (!selectedProjectId) return;
    setImporting(true); setError(null);
    try { const job = await reparseSource(selectedProjectId); await waitForSource(job.id, selectedProjectId); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Reparse failed."); }
    finally { setImporting(false); }
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
              <li key={project.id} className={selectedProjectId === project.id ? "selected" : undefined}>
                <div className="project-index">{project.title.slice(0, 1).toUpperCase()}</div>
                <div>
                  <strong>{project.title}</strong>
                  <p>{project.author || "Independent production"} · {project.status}</p>
                </div>
                <button className="select-project" type="button" onClick={() => { setSelectedProjectId(project.id); getSource(project.id).then(setSource).catch(() => setSource(null)); }}>Open</button>
              </li>
            ))}
          </ul>
        </section>
      </section>
      {selectedProjectId ? <section className="import-desk">
        <div><p className="eyebrow">Manuscript intake</p><h2>Bring in the working text</h2><p className="lede">TXT, Markdown, DOCX, and EPUB are normalized locally. The original file remains preserved beside the canonical text.</p></div>
        <div className="import-card">
          <label className="drop-zone"><input aria-label="Manuscript file" type="file" accept=".txt,.md,.markdown,.docx,.epub" onChange={handleFile} disabled={importing} /><strong>{importing ? "Preparing canonical text…" : "Choose a manuscript"}</strong><span>Rights-confirmed local import · 10 MB maximum</span></label>
          {source ? <div className="source-result"><div className="source-heading"><strong>{source.originalFilename}</strong><button type="button" onClick={handleReparse} disabled={importing}>Reparse</button></div><pre>{source.preview}</pre><ul className="warning-list">{source.warnings.length ? source.warnings.map((warning, index) => <li key={`${warning.message}-${index}`}><b>{warning.severity}</b><span>{warning.message}</span></li>) : <li><b>clear</b><span>No parser warnings.</span></li>}</ul></div> : <p className="import-placeholder">Select a project manuscript to inspect its source preview and parsing diagnostics.</p>}
        </div>
      </section> : null}
    </main>
  );
}
