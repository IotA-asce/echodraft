import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord, SegmentRevisionRecord

from echodraft_domain import Chapter, LlmExtractionRequest, Scene, Segment, SegmentRevision

from .container import AppContainer
from .local_llm import LocalLlmService

STRUCTURE_PARSER_VERSION = "structure-parser-0.3.0"
DEFAULT_REFINEMENT_MODEL = "qwen3:4b"
DEFAULT_REFINEMENT_MODEL_KEY = "qwen3_4b_ollama"
LLM_REFINEMENT_BATCH_CHARS = 3200
SPEAKER_NAME_PATTERN = r"([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3})"
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
    rf"\b{SPEAKER_NAME_PATTERN}\s+"
    r"(?:said|asked|replied|whispered|shouted|murmured|called|answered)\b"
)
COLON_SPEAKER_RE = re.compile(rf"^{SPEAKER_NAME_PATTERN}:\s+")
IGNORED_SPEAKER_CANDIDATES = {
    "he",
    "she",
    "they",
    "we",
    "you",
    "i",
    "it",
    "narrator",
}

SEGMENT_REFINEMENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "roughSegmentId": {"type": "string"},
                    "segmentType": {"type": "string"},
                    "text": {"type": "string"},
                    "speakerHint": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": [
                    "roughSegmentId",
                    "segmentType",
                    "text",
                    "speakerHint",
                    "confidence",
                    "evidence",
                ],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["segments", "warnings"],
}


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

    def extract(self, project_id: str, max_chars: int, job_id: str | None = None) -> None:
        source = self.container.sources.latest(project_id)
        project = self.container.projects.get(project_id)
        if not source or not source.canonical_path or not project:
            raise ValueError("A successfully imported canonical source is required.")
        text = Path(source.canonical_path).read_text(encoding="utf-8")
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id, {"phase": "deterministic_structure", "message": "Drafting structure locally."}
            )
        hierarchy, warnings = self._hierarchy(project_id, source.id, text, max_chars)
        hierarchy = self._refine_hierarchy(project_id, source.id, hierarchy, warnings, job_id)
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id, {"phase": "saving_structure", "message": "Saving refined structure."}
            )
        self.container.structure.replace(project_id, hierarchy, warnings)
        self._run_cast_and_speaker_draft(project_id, source.id, job_id)
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
                "pipeline": [
                    "deterministic_parser",
                    "llm_segment_refinement",
                    "cast_discovery",
                    "speaker_attribution",
                ],
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
                "sources": ["deterministic_parser"],
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
        if colon and not _ignored_speaker(colon.group(1)):
            return colon.group(1).strip(), 0.86
        speaker = SPEAKER_RE.search(text)
        if speaker and not _ignored_speaker(speaker.group(1)):
            return speaker.group(1).strip(), 0.75
        return None, 0.0

    def _refine_hierarchy(
        self,
        project_id: str,
        source_id: str,
        hierarchy: list[dict[str, object]],
        warnings: list[dict[str, object]],
        job_id: str | None,
    ) -> list[dict[str, object]]:
        ready, message = self._local_llm_ready()
        if not ready:
            warnings.append(
                self._warning(
                    project_id,
                    source_id,
                    "project",
                    project_id,
                    "info",
                    "LLM segment refinement not run; deterministic structure was kept.",
                    {
                        "source": "llm_segment_refinement",
                        "model": DEFAULT_REFINEMENT_MODEL,
                        "reason": message or "Local Ollama model is not ready.",
                    },
                    0.8,
                )
            )
            return hierarchy

        total = sum(
            len(cast(list[dict[str, object]], scene["segments"]))
            for chapter in hierarchy
            for scene in cast(list[dict[str, object]], chapter["scenes"])
        )
        processed = 0
        llm = LocalLlmService(self.container)
        for chapter in hierarchy:
            for scene in cast(list[dict[str, object]], chapter["scenes"]):
                segments = cast(list[dict[str, object]], scene["segments"])
                refined: list[dict[str, object]] = []
                for batch in self._segment_batches(segments):
                    if job_id:
                        self.container.jobs_repository.set_progress(
                            job_id,
                            {
                                "phase": "llm_segment_refinement",
                                "current": processed,
                                "total": total,
                                "message": "Refining deterministic segments with local Ollama.",
                            },
                        )
                    refined.extend(
                        self._refine_batch(project_id, source_id, llm, segments, batch, warnings, job_id)
                    )
                    processed += len(batch)
                for order, segment in enumerate(refined):
                    segment["order_index"] = order
                scene["segments"] = refined
        return hierarchy

    def _refine_batch(
        self,
        project_id: str,
        source_id: str,
        llm: LocalLlmService,
        scene_segments: list[dict[str, object]],
        batch: list[dict[str, object]],
        warnings: list[dict[str, object]],
        job_id: str | None,
    ) -> list[dict[str, object]]:
        prompt = self._refinement_prompt(scene_segments, batch)
        try:
            result = llm.extract(
                project_id,
                LlmExtractionRequest(
                    model=DEFAULT_REFINEMENT_MODEL,
                    task="llm_segment_refinement",
                    schema=SEGMENT_REFINEMENT_SCHEMA,
                    prompt=prompt,
                ),
                job_id,
            )
        except ValueError as error:
            warnings.append(
                self._warning(
                    project_id,
                    source_id,
                    "segment",
                    str(batch[0]["id"]),
                    "warning",
                    "LLM segment refinement failed; deterministic segments were kept.",
                    {
                        "source": "llm_segment_refinement",
                        "segmentIds": [str(item["id"]) for item in batch],
                        "error": str(error)[:500],
                    },
                    0.6,
                )
            )
            return batch

        raw_segments = result.result.get("segments")
        if not isinstance(raw_segments, list):
            warnings.append(
                self._warning(
                    project_id,
                    source_id,
                    "segment",
                    str(batch[0]["id"]),
                    "warning",
                    "LLM segment refinement returned no segment list; deterministic segments were kept.",
                    {"source": "llm_segment_refinement", "llmRunId": result.run.id},
                    0.5,
                )
            )
            return batch
        grouped: dict[str, list[dict[str, object]]] = {}
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            payload = cast(dict[str, object], item)
            rough_id = payload.get("roughSegmentId")
            if isinstance(rough_id, str):
                grouped.setdefault(rough_id, []).append(payload)

        output: list[dict[str, object]] = []
        for rough in batch:
            rough_id = str(rough["id"])
            pieces = grouped.get(rough_id, [])
            if not pieces:
                warnings.append(
                    self._warning(
                        project_id,
                        source_id,
                        "segment",
                        rough_id,
                        "warning",
                        "LLM segment refinement omitted a deterministic segment; original segment was kept.",
                        {"source": "llm_segment_refinement", "llmRunId": result.run.id},
                        0.5,
                    )
                )
                output.append(rough)
                continue
            refined = self._validated_refinement(project_id, source_id, rough, pieces, result.run.id, warnings)
            output.extend(refined or [rough])
        return output

    def _validated_refinement(
        self,
        project_id: str,
        source_id: str,
        rough: dict[str, object],
        pieces: list[dict[str, object]],
        run_id: str,
        warnings: list[dict[str, object]],
    ) -> list[dict[str, object]] | None:
        rough_text = str(rough["text_content"])
        piece_texts = [str(piece.get("text") or "").strip() for piece in pieces]
        allowed_types = {"narration", "dialogue", "performance_beat"}
        if (
            not all(piece_texts)
            or _normalized_compare(" ".join(piece_texts)) != _normalized_compare(rough_text)
            or any(str(piece.get("segmentType") or "") not in allowed_types for piece in pieces)
        ):
            warnings.append(
                self._warning(
                    project_id,
                    source_id,
                    "segment",
                    str(rough["id"]),
                    "warning",
                    "LLM segment refinement failed validation; deterministic segment was kept.",
                    {
                        "source": "llm_segment_refinement",
                        "llmRunId": run_id,
                        "roughSegmentId": rough["id"],
                        "reason": "text mismatch, empty text, or unsupported segment type",
                    },
                    0.55,
                )
            )
            return None

        output: list[dict[str, object]] = []
        cursor = 0
        rough_start = _int_value(rough["start_offset"])
        for piece in pieces:
            text = str(piece["text"]).strip()
            local_start = rough_text.find(text, cursor)
            if local_start < 0:
                local_start = cursor
            cursor = min(len(rough_text), local_start + len(text))
            segment_type = str(piece["segmentType"])
            speaker_hint = str(piece.get("speakerHint") or "").strip()
            confidence = _clamp_float(piece.get("confidence"), 0.0, 1.0)
            detected_speaker, detected_confidence = self._speaker(text)
            speaker = speaker_hint if speaker_hint and not _ignored_speaker(speaker_hint) else detected_speaker
            speaker_confidence = confidence if speaker_hint else detected_confidence
            deterministic_evidence = _evidence(str(rough.get("parser_evidence_json") or "{}"))
            evidence = {
                **deterministic_evidence,
                "sources": ["deterministic_parser", "llm_segment_refinement"],
                "roughSegmentId": rough["id"],
                "llmRunId": run_id,
                "llmEvidence": piece.get("evidence"),
                "llmConfidence": confidence,
            }
            output.append(
                {
                    "id": f"seg_{uuid4().hex[:16]}",
                    "scene_id": rough["scene_id"],
                    "order_index": _int_value(rough["order_index"]) + len(output),
                    "text_content": text,
                    "normalized_text": text,
                    "segment_type": segment_type,
                    "speaker_candidate": speaker,
                    "speaker_confidence": speaker_confidence,
                    "start_offset": rough_start + local_start,
                    "end_offset": rough_start + local_start + len(text),
                    "revision": 1,
                    "status": "ready",
                    "parser_evidence_json": json.dumps(evidence),
                }
            )
        return output

    def _refinement_prompt(
        self, scene_segments: list[dict[str, object]], batch: list[dict[str, object]]
    ) -> str:
        first_index = scene_segments.index(batch[0])
        last_index = scene_segments.index(batch[-1])
        previous_text = str(scene_segments[first_index - 1]["text_content"])[-240:] if first_index else ""
        next_text = (
            str(scene_segments[last_index + 1]["text_content"])[:240]
            if last_index + 1 < len(scene_segments)
            else ""
        )
        rough_lines = "\n\n".join(
            (
                f"ROUGH_SEGMENT {segment['id']}\n"
                f"type={segment['segment_type']} speakerHint={segment.get('speaker_candidate') or ''}\n"
                f"text={segment['text_content']}"
            )
            for segment in batch
        )
        return (
            "Refine deterministic audiobook structure into ordered renderable subsegments. "
            "Return only JSON that matches the supplied schema.\n\n"
            "Rules:\n"
            "- Never invent, rewrite, summarize, or drop manuscript text.\n"
            "- Preserve source order exactly.\n"
            "- Split each rough segment only into narration, dialogue, or performance_beat pieces.\n"
            "- Every returned item must use the exact roughSegmentId it came from.\n"
            "- speakerHint must be an observed proper name or an empty string.\n"
            "- Do not use text from adjacent context in returned segments.\n\n"
            f"Previous context snippet:\n{previous_text}\n\n"
            f"Next context snippet:\n{next_text}\n\n"
            f"Rough segments:\n{rough_lines}"
        )

    @staticmethod
    def _segment_batches(segments: list[dict[str, object]]) -> list[list[dict[str, object]]]:
        batches: list[list[dict[str, object]]] = []
        current: list[dict[str, object]] = []
        current_chars = 0
        for segment in segments:
            length = len(str(segment["text_content"]))
            if current and current_chars + length > LLM_REFINEMENT_BATCH_CHARS:
                batches.append(current)
                current = []
                current_chars = 0
            current.append(segment)
            current_chars += length
        if current:
            batches.append(current)
        return batches

    def _local_llm_ready(self) -> tuple[bool, str | None]:
        installation = self.container.local_ai.installation(DEFAULT_REFINEMENT_MODEL_KEY)
        if installation and installation.status == "installed":
            return True, "Local Ollama model is marked installed in Model Center."
        return False, "Ollama model qwen3:4b is not marked installed in Model Center."

    def _run_cast_and_speaker_draft(
        self, project_id: str, source_id: str, job_id: str | None
    ) -> None:
        ready, _message = self._local_llm_ready()
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id,
                {"phase": "cast_discovery", "message": "Discovering cast from refined segments."},
            )
        from .cast_discovery import CastDiscoveryService
        from .speaker_attribution import SpeakerAttributionService

        CastDiscoveryService(self.container).discover(
            project_id, source_id=source_id, use_local_llm=ready, job_id=job_id
        )
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id,
                {"phase": "speaker_attribution", "message": "Linking speakers to cast records."},
            )
        try:
            SpeakerAttributionService(self.container).generate(
                project_id, use_local_llm=ready, model=DEFAULT_REFINEMENT_MODEL, job_id=job_id
            )
        except ValueError as error:
            self.container.review.create_issue(
                project_id=project_id,
                category="cast_discovery",
                severity="warning",
                title="LLM speaker attribution needs review",
                description="Local LLM speaker attribution failed after deterministic rows were created.",
                metadata={
                    "sourceDocumentId": source_id,
                    "model": DEFAULT_REFINEMENT_MODEL,
                    "error": str(error)[:500],
                },
                dedupe_key=f"cast-speaker-llm:{project_id}:{source_id}",
            )

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


def _ignored_speaker(value: str | None) -> bool:
    if not value:
        return True
    return re.sub(r"[^a-z]+", "", value.casefold()) in IGNORED_SPEAKER_CANDIDATES


def _normalized_compare(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clamp_float(value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, (int, float, str)):
        try:
            numeric = float(value)
        except ValueError:
            numeric = minimum
    else:
        numeric = minimum
    return min(max(numeric, minimum), maximum)


def _int_value(value: object) -> int:
    if isinstance(value, (int, str)):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


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
