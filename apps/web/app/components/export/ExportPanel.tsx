import type { ExportPackage, Project, Chapter } from "../../api";
import { assetUrl } from "../../api";
import { formatBytes } from "../../lib/format";
import { EmptyState } from "../common/EmptyState";

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
  onGoStructure: () => void;
  onSelectionChange: (chapterIds: string[]) => void;
  onAudioVariantChange: (value: "active" | "clean" | "mixed") => void;
  onTitleChange: (value: string) => void;
  onAuthorChange: (value: string) => void;
  onAlbumChange: (value: string) => void;
  onPublisherChange: (value: string) => void;
  onLanguageChange: (value: string) => void;
  onCoverPathChange: (value: string) => void;
  onExport: (format: "wav" | "mp3") => void;
}) {
  if (!chapters.length) {
    return <EmptyState title="No chapters ready for export." description="Produce at least one chapter before creating a package." onAction={onGoStructure} actionLabel="Go to structure" />;
  }

  return (
    <section className="studio-section exports export-panel">
      <div>
        <p className="eyebrow">07 / Export</p>
        <h2>Export Panel</h2>
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
          <label>
            Audio
            <select value={audioVariant} onChange={(event) => onAudioVariantChange(event.currentTarget.value as "active" | "clean" | "mixed")}>
              <option value="active">Active audio version</option>
              <option value="clean">Clean narration</option>
              <option value="mixed">Mixed render</option>
            </select>
          </label>
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
        </div>
        <div className="export-actions">
          <button type="button" disabled={!selectedChapterIds.length} onClick={() => onExport("wav")}>
            Export WAV ZIP
          </button>
          <button type="button" disabled={!selectedChapterIds.length} onClick={() => onExport("mp3")}>
            Export MP3 ZIP
          </button>
          <button type="button" disabled>
            M4B planned
          </button>
        </div>
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
            <p className="import-placeholder">No export history yet. WAV and MP3 ZIP packages will appear here after creation.</p>
          )}
        </div>
      </div>
    </section>
  );
}
