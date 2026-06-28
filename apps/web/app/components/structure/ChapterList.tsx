import type { Chapter } from "../../api";
import { formatStructureStatus } from "../../lib/format";

export function ChapterList({
  chapters,
  selectedChapterId,
  onOpen,
}: {
  chapters: Chapter[];
  selectedChapterId?: string | null;
  onOpen: (chapter: Chapter) => void;
}) {
  return (
    <div>
      {chapters.map((chapter) => (
        <button className={selectedChapterId === chapter.id ? "tree-button active" : "tree-button"} type="button" key={chapter.id} onClick={() => onOpen(chapter)}>
          {chapter.title || "Untitled"}
          <small>
            {formatStructureStatus(chapter.status, chapter.confidence)}
            {chapter.userLocked ? " · locked" : ""}
          </small>
        </button>
      ))}
    </div>
  );
}
