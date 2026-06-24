"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";

import { createProject, extractStructure, getJob, getSource, importSource, listChapters, listProjects, listScenes, listSegments, reparseSource, updateSegment, type Chapter, type Project, type Scene, type Segment, type SourceDocument } from "./api";

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
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [editingSegment, setEditingSegment] = useState<Segment | null>(null);
  const [segmentDraft, setSegmentDraft] = useState("");
  const [savingSegment, setSavingSegment] = useState(false);
  const [segmentEditError, setSegmentEditError] = useState<string | null>(null);
  const [segmentEditStatus, setSegmentEditStatus] = useState<string | null>(null);

  const hasUnsavedSegmentEdit = Boolean(editingSegment && segmentDraft !== editingSegment.textContent);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to load projects."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!hasUnsavedSegmentEdit) return;
    const protectUnsavedEdit = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = true;
    };
    window.addEventListener("beforeunload", protectUnsavedEdit);
    return () => window.removeEventListener("beforeunload", protectUnsavedEdit);
  }, [hasUnsavedSegmentEdit]);

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

  async function handleExtract() {
    if (!selectedProjectId) return;
    setImporting(true); setError(null);
    try { const job = await extractStructure(selectedProjectId); await waitForSource(job.id, selectedProjectId); setChapters(await listChapters(selectedProjectId)); setScenes([]); setSegments([]); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Structure extraction failed."); }
    finally { setImporting(false); }
  }

  function guardUnsavedSegmentEdit() {
    if (!hasUnsavedSegmentEdit) return true;
    setSegmentEditError("Save or cancel the current segment edit before navigating away.");
    return false;
  }

  async function openChapter(chapter: Chapter) {
    if (!guardUnsavedSegmentEdit()) return;
    setEditingSegment(null);
    setSegmentEditError(null);
    const next = await listScenes(chapter.id);
    setScenes(next);
    setSegments(next[0] ? await listSegments(next[0].id) : []);
  }

  async function openScene(scene: Scene) {
    if (!guardUnsavedSegmentEdit()) return;
    setEditingSegment(null);
    setSegmentEditError(null);
    setSegments(await listSegments(scene.id));
  }

  function beginSegmentEdit(segment: Segment) {
    if (editingSegment?.id === segment.id) return;
    if (hasUnsavedSegmentEdit && editingSegment?.id !== segment.id) {
      setSegmentEditError("Save or cancel the current segment edit before opening another segment.");
      return;
    }
    setEditingSegment(segment);
    setSegmentDraft(segment.textContent);
    setSegmentEditError(null);
    setSegmentEditStatus(null);
  }

  function cancelSegmentEdit() {
    setEditingSegment(null);
    setSegmentDraft("");
    setSegmentEditError(null);
  }

  async function saveSegmentEdit() {
    if (!editingSegment || !segmentDraft.trim() || !hasUnsavedSegmentEdit) return;
    setSavingSegment(true);
    setSegmentEditError(null);
    try {
      const updated = await updateSegment(editingSegment.id, segmentDraft.trim());
      setSegments((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSegmentEditStatus(`Revision r${updated.revision} saved.`);
      setEditingSegment(null);
      setSegmentDraft("");
    } catch (cause) {
      setSegmentEditError(cause instanceof Error ? cause.message : "Unable to save the segment revision.");
    } finally {
      setSavingSegment(false);
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
          {source ? <div className="source-result"><div className="source-heading"><strong>{source.originalFilename}</strong><span><button type="button" onClick={handleExtract} disabled={importing}>Extract structure</button><button type="button" onClick={handleReparse} disabled={importing}>Reparse</button></span></div><pre>{source.preview}</pre><ul className="warning-list">{source.warnings.length ? source.warnings.map((warning, index) => <li key={`${warning.message}-${index}`}><b>{warning.severity}</b><span>{warning.message}</span></li>) : <li><b>clear</b><span>No parser warnings.</span></li>}</ul></div> : <p className="import-placeholder">Select a project manuscript to inspect its source preview and parsing diagnostics.</p>}
        </div>
      </section> : null}
      {chapters.length ? <section className="structure-view">
        <div><p className="eyebrow">Structure viewer</p><h2>Editable story map</h2><p className="lede">Unresolved boundaries remain visible for editorial correction.</p></div>
        <div className="structure-columns">
          <div>{chapters.map((chapter) => <button className="tree-button" type="button" key={chapter.id} onClick={() => openChapter(chapter)}>{chapter.title || "Untitled"}<small>{chapter.status} · {Math.round(chapter.confidence * 100)}%</small></button>)}</div>
          <div>{scenes.map((scene, index) => <button className="tree-button" type="button" key={scene.id} onClick={() => openScene(scene)}>Scene {index + 1}<small>{scene.status} · {Math.round(scene.confidence * 100)}%</small></button>)}</div>
          <div className="segment-column" aria-live="polite">
            {segmentEditStatus ? <p className="segment-edit-status">{segmentEditStatus}</p> : null}
            {segments.map((segment) => <div className="segment-entry" key={segment.id}>
              <button className={`segment-button${editingSegment?.id === segment.id ? " editing" : ""}`} type="button" onClick={() => beginSegmentEdit(segment)} aria-expanded={editingSegment?.id === segment.id}>
                <span>{segment.textContent}</span><small>r{segment.revision} · {segment.speakerCandidate || "narration"}</small>
              </button>
              {editingSegment?.id === segment.id ? <div className="segment-editor">
                <div className="segment-editor-heading"><div><p className="eyebrow">Edit segment</p><strong>Revision r{segment.revision + 1}</strong></div><span>{segmentDraft.length} characters</span></div>
                <label htmlFor={`segment-editor-${segment.id}`}>Narration text</label>
                <textarea id={`segment-editor-${segment.id}`} value={segmentDraft} onChange={(event) => { setSegmentDraft(event.target.value); setSegmentEditError(null); }} onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); void saveSegmentEdit(); }
                  if (event.key === "Escape" && !savingSegment) cancelSegmentEdit();
                }} rows={8} autoFocus aria-describedby={`segment-editor-help-${segment.id}`} />
                <p className="segment-editor-help" id={`segment-editor-help-${segment.id}`}>{hasUnsavedSegmentEdit ? `Saving creates revision r${segment.revision + 1}; revision r${segment.revision} remains in history.` : "Make a change to create a new revision."} <kbd>Ctrl</kbd> + <kbd>Enter</kbd> saves; <kbd>Esc</kbd> cancels.</p>
                {segmentEditError ? <p className="segment-edit-error" role="alert">{segmentEditError}</p> : null}
                <div className="segment-editor-actions"><button className="secondary" type="button" onClick={cancelSegmentEdit} disabled={savingSegment}>Cancel</button><button type="button" onClick={() => void saveSegmentEdit()} disabled={savingSegment || !segmentDraft.trim() || !hasUnsavedSegmentEdit}>{savingSegment ? "Saving revision…" : "Save revision"}</button></div>
              </div> : null}
            </div>)}
          </div>
        </div>
      </section> : null}
    </main>
  );
}
