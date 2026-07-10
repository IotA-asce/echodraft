import { useState } from "react";
import type { Chapter, ExportEstimate, ExportFormat, ExportPackage, Project } from "../../api";
import { assetUrl } from "../../api";
import { formatBytes } from "../../lib/format";
import { EmptyState } from "../common/EmptyState";
import { Select } from "../../design-system";

export function ExportPanel({
  project,
  chapters,
  selectedChapterIds,
  audioVariant,
  title,
  author,
  album,
  publisher,
  language,
  coverPath,
  exports,
  estimate,
  busy,
  onGoStructure,
  onSelectionChange,
  onAudioVariantChange,
  onTitleChange,
  onAuthorChange,
  onAlbumChange,
  onPublisherChange,
  onLanguageChange,
  onCoverPathChange,
  onExport,
}: {
  project: Project;
  chapters: Chapter[];
  selectedChapterIds: string[];
  audioVariant: "active" | "clean" | "mixed";
  title: string;
  author: string;
  album: string;
  publisher: string;
  language: string;
  coverPath: string;
  exports: ExportPackage[];
  estimate: ExportEstimate | null;
  busy?: boolean;
  onGoStructure: () => void;
  onSelectionChange: (chapterIds: string[]) => void;
  onAudioVariantChange: (value: "active" | "clean" | "mixed") => void;
  onTitleChange: (value: string) => void;
  onAuthorChange: (value: string) => void;
  onAlbumChange: (value: string) => void;
  onPublisherChange: (value: string) => void;
  onLanguageChange: (value: string) => void;
  onCoverPathChange: (value: string) => void;
  onExport: (format: ExportFormat, options?: { includeRetailSample?: boolean }) => void;
}) {
  const [includeRetailSample, setIncludeRetailSample] = useState(false);
  const latestExport = exports[0] ?? null;
  const latestScores = latestExport?.qa?.outputs ?? [];
  const hasBlockers = Boolean(estimate?.blockers.length);

  if (!chapters.length) {
    return <EmptyState title="No chapters ready for export." description="Produce at least one chapter before creating a package." onAction={onGoStructure} actionLabel="Go to structure" />;
  }

  return (
    <section className="studio-section exports export-panel" aria-labelledby="export-panel-title">
      <div>
        <p className="eyebrow">07 / Export</p>
        <h2 id="export-panel-title">Export Panel</h2>
        <p className="lede">Choose chapters, package clean or mixed audio, and keep checksums, readiness summaries, and render lineage with each local ZIP.</p>
      </div>
      <div className="studio-card">
        <div className="chapter-checks">
          {chapters.map((chapter) => (
            <label key={chapter.id}>
              <input
                type="checkbox"
                checked={selectedChapterIds.includes(chapter.id)}
                onChange={(event) => onSelectionChange(event.target.checked ? [...selectedChapterIds, chapter.id] : selectedChapterIds.filter((id) => id !== chapter.id))}
              />
              {chapter.title || "Untitled"}
            </label>
          ))}
        </div>
        <div className="export-polish-grid">
          <Select label="Audio" value={audioVariant} onValueChange={(value) => onAudioVariantChange(value as "active" | "clean" | "mixed")} options={[{ value: "active", label: "Active audio version" }, { value: "clean", label: "Clean narration" }, { value: "mixed", label: "Mixed render" }]} />
          <label>
            Title
            <input value={title} placeholder={project.title} onChange={(event) => onTitleChange(event.currentTarget.value)} />
          </label>
          <label>
            Author
            <input value={author} placeholder={project.author ?? "Author"} onChange={(event) => onAuthorChange(event.currentTarget.value)} />
          </label>
          <label>
            Album
            <input value={album} placeholder={project.title} onChange={(event) => onAlbumChange(event.currentTarget.value)} />
          </label>
          <label>
            Publisher
            <input value={publisher} onChange={(event) => onPublisherChange(event.currentTarget.value)} />
          </label>
          <label>
            Language
            <input value={language} onChange={(event) => onLanguageChange(event.currentTarget.value)} />
          </label>
          <label className="cover-field">
            Cover path
            <input value={coverPath} placeholder="/path/to/cover.jpg" onChange={(event) => onCoverPathChange(event.currentTarget.value)} />
          </label>
          <label className="retail-sample-toggle">
            <input type="checkbox" checked={includeRetailSample} onChange={(event) => setIncludeRetailSample(event.currentTarget.checked)} />
            Include retail sample
          </label>
        </div>
        <div className="export-actions">
          <button type="button" disabled={!selectedChapterIds.length || hasBlockers || busy} onClick={() => onExport("wav", { includeRetailSample: false })}>
            Export WAV ZIP
          </button>
          <button type="button" disabled={!selectedChapterIds.length || hasBlockers || busy} onClick={() => onExport("mp3", { includeRetailSample })}>
            Export MP3 ZIP
          </button>
          <button type="button" disabled={!selectedChapterIds.length || hasBlockers || busy} onClick={() => onExport("m4b", { includeRetailSample })}>
            Export M4B
          </button>
        </div>
        {estimate ? (
          <div className={hasBlockers ? "export-estimate blocked" : "export-estimate"}>
            <div className="source-heading">
              <strong>Export readiness</strong>
              <span>{hasBlockers ? `${estimate.blockers.length} blocker${estimate.blockers.length === 1 ? "" : "s"}` : `${formatBytes(estimate.estimatedSizeBytes)} estimated`}</span>
            </div>
            {hasBlockers ? (
              estimate.blockers.slice(0, 8).map((blocker) => (
                <p key={`${blocker.code}-${blocker.chapterId ?? "global"}-${blocker.issueId ?? "none"}`}>
                  <b>{blocker.scope}</b>
                  <span>{blocker.message}</span>
                </p>
              ))
            ) : (
              <p><b>Ready</b><span>Selected chapters can be packaged with the current settings.</span></p>
            )}
          </div>
        ) : null}
        {latestExport && latestScores.length ? (
          <div className="export-scorecard" aria-label="Latest export QA scorecard">
            <div className="scorecard-header">
              <strong>Latest QA</strong>
              <span className={latestExport.qa.allWithinTolerance ? "score-pass" : "score-check"}>
                {latestExport.qa.allWithinTolerance ? "✓" : "✗"}
              </span>
            </div>
            {latestScores.map((score) => (
              <p className="score-row" key={score.filename}>
                <span>{score.filename}</span>
                <span>{typeof score.lufsIntegrated === "number" ? `${score.lufsIntegrated.toFixed(1)} LUFS` : "LUFS n/a"}</span>
                <span>{typeof score.truePeakDb === "number" ? `${score.truePeakDb.toFixed(1)} dBTP` : "Peak n/a"}</span>
                <span className={score.withinTolerance ? "score-pass" : "score-check"}>{score.withinTolerance ? "✓" : "✗"}</span>
              </p>
            ))}
          </div>
        ) : null}
        <div className="export-history">
          {exports.length ? (
            exports.map((item) => (
              <p className="export-row" key={item.id}>
                <span>
                  {item.format.toUpperCase()} · {item.audioVariant} · {item.chapterCount || selectedChapterIds.length} chapters · {formatBytes(item.estimatedSizeBytes)}
                  {item.checksum ? ` · ${item.checksum.slice(0, 10)}` : ""}
                </span>
                {item.downloadUrl ? <a href={assetUrl(item.downloadUrl)}>Download ZIP</a> : null}
              </p>
            ))
          ) : (
            <p className="import-placeholder">No export history yet. WAV, MP3, and M4B packages will appear here after creation.</p>
          )}
        </div>
      </div>
    </section>
  );
}
