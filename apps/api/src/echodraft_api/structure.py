import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord, SegmentRevisionRecord

from echodraft_domain import Chapter, Scene, Segment, SegmentRevision

from .container import AppContainer

STRUCTURE_PARSER_VERSION = "structure-parser-0.2.0"
CHAPTER_RE = re.compile(
    r"^(?P<markdown>#{1,3}\s+)?(?P<title>(?:chapter\s+(?:\d+|[ivxlcdm]+|[a-z]+)"
    r"(?:\s*[:.-]\s*.+)?|prologue|epilogue|afterword|acknowledg(?:e)?ments|"
    r"part\s+(?:\d+|[ivxlcdm]+|[a-z]+)(?:\s*[:.-]\s*.+)?|book\s+"
    r"(?:\d+|[ivxlcdm]+|[a-z]+)(?:\s*[:.-]\s*.+)?|.+))$",
    re.IGNORECASE,
)
EXPLICIT_CHAPTER_RE = re.compile(
    r"^(?:chapter\s+(?:\d+|[ivxlcdm]+|[a-z]+)|prologue|epilogue|afterword|"
    r"acknowledg(?:e)?ments|part\s+(?:\d+|[ivxlcdm]+|[a-z]+)|book\s+"
    r"(?:\d+|[ivxlcdm]+|[a-z]+))\b",
    re.IGNORECASE,
)
SCENE_RE = re.compile(
    r"^\s*(?:\*{3,}|---|#{4,}\s*.*|scene\s+\d+\b.*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
SPEAKER_RE = re.compile(
    r"\b([A-Z][a-z]{1,30})\s+(?:said|asked|replied|whispered|shouted|murmured)\b"
)
COLON_SPEAKER_RE = re.compile(r"^([A-Z][A-Za-z]{1,30}):\s+")


@dataclass(frozen=True)
class ChapterBoundary:
    start: int
    content_start: int
    title: str
    confidence: float
    status: str
    evidence: dict[str, object]


class StructureService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def extract(self, project_id: str, max_chars: int) -> None:
        source = self.container.sources.latest(project_id)
        project = self.container.projects.get(project_id)
        if not source or not source.canonical_path or not project:
            raise ValueError("A successfully imported canonical source is required.")
        text = Path(source.canonical_path).read_text(encoding="utf-8")
        hierarchy, warnings = self._hierarchy(project_id, source.id, text, max_chars)
        self.container.structure.replace(project_id, hierarchy, warnings)
        manifest = {
            "manifestType": "structure_manifest",
            "schemaVersion": "0.2.0",
            "projectId": project_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "status": "completed",
            "diagnostics": [
                {
                    "severity": warning["severity"],
                    "scopeType": warning["scope_type"],
                    "scopeId": warning["scope_id"],
                    "message": warning["message"],
                    "evidence": json.loads(str(warning["evidence_json"])),
                    "confidence": warning["confidence"],
                }
                for warning in warnings
            ],
            "payload": {
                "sourceDocumentId": source.id,
                "maxSegmentChars": max_chars,
                "parserVersion": STRUCTURE_PARSER_VERSION,
                "chapters": hierarchy,
            },
        }
        root = Path(project.artifact_path) / "manifests"
        version = root / f"structure_manifest.{uuid4().hex[:12]}.json"
        version.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (root / "structure_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _hierarchy(
        self, project_id: str, source_id: str, text: str, max_chars: int
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        boundaries = self._chapter_boundaries(text)
        warnings: list[dict[str, object]] = []
        if not boundaries:
            boundaries = [
                ChapterBoundary(
                    start=0,
                    content_start=0,
                    title="Unresolved chapter",
                    confidence=0.35,
                    status="unresolved",
                    evidence={"reason": "no chapter heading matched"},
                )
            ]
        elif boundaries[0].start > 0 and text[: boundaries[0].start].strip():
            boundaries.insert(
                0,
                ChapterBoundary(
                    start=0,
                    content_start=0,
                    title="Front matter",
                    confidence=0.72,
                    status="front_matter",
                    evidence={"reason": "text appears before first chapter heading"},
                ),
            )

        result: list[dict[str, object]] = []
        for chapter_index, boundary in enumerate(boundaries):
            end = boundaries[chapter_index + 1].start if chapter_index + 1 < len(boundaries) else len(text)
            chapter_id = f"chap_{uuid4().hex[:16]}"
            chapter_text = text[boundary.content_start:end].strip()
            if boundary.status == "unresolved":
                warnings.append(
                    self._warning(
                        project_id,
                        source_id,
                        "chapter",
                        chapter_id,
                        "warning",
                        "No reliable chapter heading was found.",
                        boundary.evidence,
                        boundary.confidence,
                    )
                )
            scenes = self._scenes(
                project_id, source_id, chapter_id, chapter_text, boundary.content_start, max_chars, warnings
            )
            result.append(
                {
                    "record": {
                        "id": chapter_id,
                        "project_id": project_id,
                        "order_index": chapter_index,
                        "title": boundary.title,
                        "start_offset": boundary.start,
                        "end_offset": end,
                        "confidence": boundary.confidence,
                        "status": boundary.status,
                        "parser_evidence_json": json.dumps(boundary.evidence),
                    },
                    "scenes": scenes,
                }
            )
        return result, warnings

    def _chapter_boundaries(self, text: str) -> list[ChapterBoundary]:
        boundaries: list[ChapterBoundary] = []
        for match in re.finditer(r"(?m)^.+$", text):
            line = match.group(0).strip()
            if not line:
                continue
            parsed = CHAPTER_RE.match(line)
            if not parsed:
                continue
            has_markdown = bool(parsed.group("markdown"))
            title = parsed.group("title").strip()
            is_explicit = bool(EXPLICIT_CHAPTER_RE.match(title))
            if not has_markdown and not is_explicit:
                continue
            confidence = 0.96 if has_markdown else 0.9
            status = "structured"
            boundaries.append(
                ChapterBoundary(
                    start=match.start(),
                    content_start=match.end(),
                    title=title.lstrip("#").strip(),
                    confidence=confidence,
                    status=status,
                    evidence={"line": line, "markdown": has_markdown, "explicit": is_explicit},
                )
            )
        return boundaries

    def _scenes(
        self,
        project_id: str,
        source_id: str,
        chapter_id: str,
        text: str,
        base: int,
        max_chars: int,
        warnings: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        pieces = list(SCENE_RE.finditer(text))
        starts = [0] + [match.end() for match in pieces]
        ends = [match.start() for match in pieces] + [len(text)]
        scene_status = "structured" if pieces else "unresolved"
        confidence = 0.86 if pieces else 0.48
        scenes: list[dict[str, object]] = []
        for start, end in zip(starts, ends):
            scene_text = text[start:end].strip()
            if not scene_text:
                continue
            scene_id = f"scene_{uuid4().hex[:16]}"
            evidence: dict[str, object] = {
                "separatorCount": len(pieces),
                "startOffset": base + start,
                "endOffset": base + end,
            }
            if not pieces and not scenes:
                warnings.append(
                    self._warning(
                        project_id,
                        source_id,
                        "scene",
                        scene_id,
                        "info",
                        "No explicit scene breaks were found; a single scene was inferred.",
                        evidence,
                        confidence,
                    )
                )
            scenes.append(
                {
                    "record": {
                        "id": scene_id,
                        "chapter_id": chapter_id,
                        "order_index": len(scenes),
                        "start_offset": base + start,
                        "end_offset": base + end,
                        "confidence": confidence,
                        "status": scene_status,
                        "parser_evidence_json": json.dumps(evidence),
                    },
                    "segments": self._segments(
                        project_id, source_id, scene_id, scene_text, base + start, max_chars, warnings
                    ),
                }
            )
        return scenes

    def _segments(
        self,
        project_id: str,
        source_id: str,
        scene_id: str,
        text: str,
        base: int,
        max_chars: int,
        warnings: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        units = self._segment_units(text, max_chars)
        result: list[dict[str, object]] = []
        cursor = 0
        for segment_text in units:
            local_start = text.find(segment_text, cursor)
            if local_start < 0:
                local_start = cursor
            cursor = local_start + len(segment_text)
            segment_id = f"seg_{uuid4().hex[:16]}"
            segment_type = self._segment_type(segment_text)
            speaker, speaker_confidence = self._speaker(segment_text)
            evidence = {
                "parserVersion": STRUCTURE_PARSER_VERSION,
                "segmentTypeRule": segment_type,
                "speakerRule": "deterministic" if speaker else None,
            }
            if segment_type == "dialogue" and not speaker:
                warnings.append(
                    self._warning(
                        project_id,
                        source_id,
                        "segment",
                        segment_id,
                        "warning",
                        "Dialogue segment has no deterministic speaker attribution.",
                        {"textPreview": segment_text[:120]},
                        0.45,
                    )
                )
            result.append(
                {
                    "id": segment_id,
                    "scene_id": scene_id,
                    "order_index": len(result),
                    "text_content": segment_text,
                    "normalized_text": segment_text,
                    "segment_type": segment_type,
                    "speaker_candidate": speaker,
                    "speaker_confidence": speaker_confidence,
                    "start_offset": base + local_start,
                    "end_offset": base + local_start + len(segment_text),
                    "revision": 1,
                    "status": "ready",
                    "parser_evidence_json": json.dumps(evidence),
                }
            )
        return result

    def _segment_units(self, text: str, max_chars: int) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
        units: list[str] = []
        for paragraph in paragraphs:
            if self._segment_type(paragraph) == "performance_beat" or len(paragraph) <= max_chars:
                units.append(paragraph)
                continue
            sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", paragraph) if item.strip()]
            current = ""
            for sentence in sentences:
                candidate = f"{current} {sentence}".strip()
                if current and len(candidate) > max_chars:
                    units.append(current)
                    current = sentence
                else:
                    current = candidate
            if current:
                units.append(current)
        return units

    @staticmethod
    def _segment_type(text: str) -> str:
        stripped = text.strip()
        if len(stripped) <= 140 and (
            (stripped.startswith("[") and stripped.endswith("]"))
            or (stripped.startswith("(") and stripped.endswith(")"))
        ):
            return "performance_beat"
        if stripped.startswith(('"', "'", "“", "‘")) or COLON_SPEAKER_RE.match(stripped):
            return "dialogue"
        return "narration"

    @staticmethod
    def _speaker(text: str) -> tuple[str | None, float]:
        colon = COLON_SPEAKER_RE.match(text)
        if colon:
            return colon.group(1), 0.86
        speaker = SPEAKER_RE.search(text)
        if speaker:
            return speaker.group(1), 0.75
        return None, 0.0

    @staticmethod
    def _warning(
        project_id: str,
        source_id: str,
        scope_type: str,
        scope_id: str,
        severity: str,
        message: str,
        evidence: dict[str, object],
        confidence: float,
    ) -> dict[str, object]:
        return {
            "id": f"structwarn_{uuid4().hex[:16]}",
            "project_id": project_id,
            "source_document_id": source_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "severity": severity,
            "message": message,
            "evidence_json": json.dumps(evidence),
            "confidence": confidence,
            "resolved": False,
            "created_at": datetime.now(UTC),
        }


def _evidence(payload: str | None) -> dict[str, object]:
    loaded = json.loads(payload or "{}")
    return cast(dict[str, object], loaded if isinstance(loaded, dict) else {})


def chapter_model(record: ChapterRecord) -> Chapter:
    return Chapter.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "orderIndex": record.order_index,
            "title": record.title,
            "confidence": record.confidence,
            "startOffset": record.start_offset,
            "endOffset": record.end_offset,
            "status": record.status,
            "parserEvidence": _evidence(record.parser_evidence_json),
            "userLocked": record.user_locked,
            "lockReason": record.lock_reason,
        }
    )


def scene_model(record: SceneRecord) -> Scene:
    return Scene.model_validate(
        {
            "id": record.id,
            "chapterId": record.chapter_id,
            "orderIndex": record.order_index,
            "confidence": record.confidence,
            "startOffset": record.start_offset,
            "endOffset": record.end_offset,
            "status": record.status,
            "parserEvidence": _evidence(record.parser_evidence_json),
            "userLocked": record.user_locked,
            "lockReason": record.lock_reason,
        }
    )


def segment_model(record: SegmentRecord) -> Segment:
    return Segment.model_validate(
        {
            "id": record.id,
            "sceneId": record.scene_id,
            "orderIndex": record.order_index,
            "textContent": record.text_content,
            "normalizedText": record.normalized_text,
            "segmentType": record.segment_type,
            "speakerCandidate": record.speaker_candidate,
            "speakerConfidence": record.speaker_confidence,
            "startOffset": record.start_offset,
            "endOffset": record.end_offset,
            "revision": record.revision,
            "status": record.status,
            "parserEvidence": _evidence(record.parser_evidence_json),
            "userLocked": record.user_locked,
            "lockReason": record.lock_reason,
        }
    )


def revision_model(record: SegmentRevisionRecord) -> SegmentRevision:
    return SegmentRevision.model_validate(
        {
            "id": record.id,
            "segmentId": record.segment_id,
            "revision": record.revision,
            "textContent": record.text_content,
            "createdAt": record.created_at,
        }
    )
