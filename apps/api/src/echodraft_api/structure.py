import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord, SegmentRevisionRecord

from echodraft_domain import Chapter, Scene, Segment, SegmentRevision

from .container import AppContainer


class StructureService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def extract(self, project_id: str, max_chars: int) -> None:
        source = self.container.sources.latest(project_id)
        project = self.container.projects.get(project_id)
        if not source or not source.canonical_path or not project:
            raise ValueError("A successfully imported canonical source is required.")
        text = Path(source.canonical_path).read_text(encoding="utf-8")
        hierarchy = self._hierarchy(project_id, text, max_chars)
        self.container.structure.replace(project_id, hierarchy)
        manifest = {"manifestType": "structure_manifest", "schemaVersion": "0.1.0", "projectId": project_id, "generatedAt": datetime.now(UTC).isoformat(), "status": "completed", "diagnostics": [], "payload": {"sourceDocumentId": source.id, "maxSegmentChars": max_chars, "chapters": hierarchy}}
        root = Path(project.artifact_path) / "manifests"
        version = root / f"structure_manifest.{uuid4().hex[:12]}.json"
        version.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (root / "structure_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _hierarchy(self, project_id: str, text: str, max_chars: int) -> list[dict[str, object]]:
        matches = list(re.finditer(r"(?im)^(?:#{1,3}\s+|chapter\s+\d+\s*[:.-]?\s*)(.+)$", text))
        boundaries = [(m.start(), m.group(1).strip(), 0.95, "structured") for m in matches]
        if not boundaries:
            boundaries = [(0, "Unresolved chapter", 0.35, "unresolved")]
        result: list[dict[str, object]] = []
        for chapter_index, (start, title, confidence, status) in enumerate(boundaries):
            end = boundaries[chapter_index + 1][0] if chapter_index + 1 < len(boundaries) else len(text)
            chapter_id = f"chap_{uuid4().hex[:16]}"
            chapter_text = text[start:end].strip()
            scenes = self._scenes(chapter_id, chapter_text, start, max_chars)
            result.append({"record": {"id": chapter_id, "project_id": project_id, "order_index": chapter_index, "title": title, "start_offset": start, "end_offset": end, "confidence": confidence, "status": status}, "scenes": scenes})
        return result

    def _scenes(self, chapter_id: str, text: str, base: int, max_chars: int) -> list[dict[str, object]]:
        pieces = list(re.finditer(r"(?m)^\s*(?:\*{3,}|---|#)\s*$", text))
        starts = [0] + [match.end() for match in pieces]
        ends = [match.start() for match in pieces] + [len(text)]
        scene_status = "structured" if pieces else "unresolved"
        confidence = 0.85 if pieces else 0.4
        scenes: list[dict[str, object]] = []
        for index, (start, end) in enumerate(zip(starts, ends)):
            scene_text = text[start:end].strip()
            if not scene_text:
                continue
            scene_id = f"scene_{uuid4().hex[:16]}"
            scenes.append({"record": {"id": scene_id, "chapter_id": chapter_id, "order_index": len(scenes), "start_offset": base + start, "end_offset": base + end, "confidence": confidence, "status": scene_status}, "segments": self._segments(scene_id, scene_text, base + start, max_chars)})
        return scenes

    def _segments(self, scene_id: str, text: str, base: int, max_chars: int) -> list[dict[str, object]]:
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
        batches: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                batches.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            batches.append(current)
        result: list[dict[str, object]] = []
        cursor = 0
        for index, segment_text in enumerate(batches):
            local_start = text.find(segment_text, cursor)
            cursor = local_start + len(segment_text)
            speaker = re.search(r"\b([A-Z][a-z]{1,30})\s+(?:said|asked|replied|whispered)\b", segment_text)
            result.append({"id": f"seg_{uuid4().hex[:16]}", "scene_id": scene_id, "order_index": index, "text_content": segment_text, "normalized_text": segment_text, "segment_type": "dialogue" if segment_text.startswith(('"', "'")) else "narration", "speaker_candidate": speaker.group(1) if speaker else None, "speaker_confidence": 0.75 if speaker else 0.0, "start_offset": base + local_start, "end_offset": base + local_start + len(segment_text), "revision": 1, "status": "ready"})
        return result


def chapter_model(record: ChapterRecord) -> Chapter:
    return Chapter.model_validate({"id": record.id, "projectId": record.project_id, "orderIndex": record.order_index, "title": record.title, "confidence": record.confidence, "startOffset": record.start_offset, "endOffset": record.end_offset, "status": record.status})

def scene_model(record: SceneRecord) -> Scene:
    return Scene.model_validate({"id": record.id, "chapterId": record.chapter_id, "orderIndex": record.order_index, "confidence": record.confidence, "startOffset": record.start_offset, "endOffset": record.end_offset, "status": record.status})

def segment_model(record: SegmentRecord) -> Segment:
    return Segment.model_validate({"id": record.id, "sceneId": record.scene_id, "orderIndex": record.order_index, "textContent": record.text_content, "normalizedText": record.normalized_text, "segmentType": record.segment_type, "speakerCandidate": record.speaker_candidate, "speakerConfidence": record.speaker_confidence, "startOffset": record.start_offset, "endOffset": record.end_offset, "revision": record.revision, "status": record.status})

def revision_model(record: SegmentRevisionRecord) -> SegmentRevision:
    return SegmentRevision.model_validate({"id": record.id, "segmentId": record.segment_id, "revision": record.revision, "textContent": record.text_content, "createdAt": record.created_at})
