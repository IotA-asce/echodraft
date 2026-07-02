from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import cast

from echodraft_db.models import ChapterRecord, CharacterRecord, SceneRecord, SegmentRecord
from echodraft_domain import LlmExtractionRequest, SpeakerAttribution
from sqlalchemy import select

from .container import AppContainer

SPEAKER_ATTRIBUTION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "attributions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segmentId": {"type": "string"},
                    "speakerName": {"type": "string"},
                    "characterName": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["segmentId", "speakerName", "confidence"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["attributions", "warnings"],
}
SPEAKER_ATTRIBUTION_BATCH_CHARS = 5000
SPEAKER_ATTRIBUTION_BATCH_SEGMENTS = 20


@dataclass(frozen=True)
class CharacterIndex:
    by_name: dict[str, CharacterRecord]


class SpeakerAttributionService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def list_attributions(
        self, project_id: str, status: str | None = None
    ) -> list[SpeakerAttribution]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        return self.container.speaker_attributions.list_attributions(project_id, status)

    def generate(
        self,
        project_id: str,
        *,
        use_local_llm: bool = False,
        model: str = "qwen3:4b",
        job_id: str | None = None,
    ) -> list[SpeakerAttribution]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        segments = self._segments(project_id)
        character_index = self._character_index(project_id)
        for index, segment in enumerate(segments, 1):
            self._upsert_deterministic(project_id, segment, character_index)
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "speaker_attribution",
                        "current": index,
                        "total": len(segments),
                        "segmentId": segment.id,
                    },
                )
        if use_local_llm:
            self._apply_local_llm(project_id, model, segments, character_index, job_id)
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id,
                {"phase": "speaker_attribution", "current": len(segments), "total": len(segments)},
            )
        return self.list_attributions(project_id)

    def update(
        self,
        attribution_id: str,
        *,
        character_id: str | None,
        update_character: bool,
        speaker_name: str | None,
        status: str | None,
        user_locked: bool | None,
    ) -> SpeakerAttribution:
        record = self.container.speaker_attributions.update(
            attribution_id,
            character_id=character_id,
            update_character=update_character,
            speaker_name=speaker_name,
            status=status,
            user_locked=user_locked,
        )
        if not record:
            raise ValueError("Speaker attribution not found.")
        return record

    def _upsert_deterministic(
        self, project_id: str, segment: SegmentRecord, character_index: CharacterIndex
    ) -> SpeakerAttribution:
        candidate = segment.speaker_candidate.strip() if segment.speaker_candidate else None
        character = character_index.by_name.get(_name_key(candidate)) if candidate else None
        parser_evidence = _evidence(segment.parser_evidence_json)
        speaker_name: str | None
        if segment.segment_type != "dialogue" and not candidate:
            speaker_name = "Narrator"
            confidence = max(segment.speaker_confidence, 0.9)
            status = "approved"
            evidence: dict[str, object] = {
                "reason": "narration_segment",
                "textPreview": segment.text_content[:160],
                "source": "structure_parser",
                "structure": parser_evidence,
            }
        else:
            speaker_name = candidate
            confidence = segment.speaker_confidence if candidate else 0.0
            status = "approved" if character and confidence >= 0.8 else "needs_review"
            evidence = {
                "reason": "deterministic_speaker_candidate" if candidate else "dialogue_without_speaker",
                "speakerCandidate": candidate,
                "textPreview": segment.text_content[:160],
                "segmentType": segment.segment_type,
                "source": "structure_parser",
                "speakerRule": parser_evidence.get("speakerRule"),
                "productionType": parser_evidence.get("productionType"),
                "structure": parser_evidence,
            }
        return self.container.speaker_attributions.upsert(
            project_id,
            segment.id,
            character_id=character.id if character else None,
            speaker_name=speaker_name,
            method="deterministic",
            evidence=evidence,
            confidence=confidence,
            status=status,
        )

    def _apply_local_llm(
        self,
        project_id: str,
        model: str,
        segments: list[SegmentRecord],
        character_index: CharacterIndex,
        job_id: str | None,
    ) -> None:
        unresolved = [
            item
            for item in self.container.speaker_attributions.list_attributions(
                project_id, "needs_review"
            )
            if not item.user_locked
        ]
        if not unresolved:
            return
        segment_map = {segment.id: segment for segment in segments}
        from .local_llm import LocalLlmService

        unresolved_segments = [
            segment_map[item.segment_id]
            for item in unresolved
            if item.segment_id in segment_map
        ]
        batches = list(_segment_batches(unresolved_segments))
        for batch_index, batch in enumerate(batches, 1):
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "llm_speaker_attribution",
                        "current": batch_index,
                        "total": len(batches),
                    },
                )
            try:
                result = LocalLlmService(self.container).extract(
                    project_id,
                    LlmExtractionRequest(
                        model=model,
                        task="speaker_attribution",
                        schema=SPEAKER_ATTRIBUTION_SCHEMA,
                        prompt=self._llm_prompt(batch, character_index),
                    ),
                    job_id,
                )
            except ValueError as error:
                self.container.review.create_issue(
                    project_id=project_id,
                    category="cast_discovery",
                    severity="warning",
                    title="LLM speaker attribution skipped a segment window",
                    description="Local Ollama failed while assigning speakers; deterministic review rows remain.",
                    metadata={"error": str(error)[:500], "segmentIds": [segment.id for segment in batch]},
                    dedupe_key=f"speaker-llm:{project_id}:{batch[0].id}",
                )
                continue
            attributions = result.result.get("attributions")
            if not isinstance(attributions, list):
                continue
            for item in attributions:
                if not isinstance(item, dict):
                    continue
                payload = cast(dict[str, object], item)
                segment_id = payload.get("segmentId")
                if not isinstance(segment_id, str) or segment_id not in segment_map:
                    continue
                speaker_name = str(payload.get("speakerName") or "")
                character_name = str(payload.get("characterName") or speaker_name)
                confidence = _confidence(payload.get("confidence"))
                character = character_index.by_name.get(_name_key(character_name))
                self.container.speaker_attributions.upsert(
                    project_id,
                    segment_id,
                    character_id=character.id if character else None,
                    speaker_name=speaker_name or None,
                    method="ollama",
                    evidence={
                        "reason": "ollama_fallback",
                        "llmRunId": result.run.id,
                        "textPreview": segment_map[segment_id].text_content[:160],
                        "evidence": payload.get("evidence"),
                        "structure": _evidence(segment_map[segment_id].parser_evidence_json),
                    },
                    confidence=confidence,
                    status="approved" if character and confidence >= 0.8 else "needs_review",
                )

    def _segments(self, project_id: str) -> list[SegmentRecord]:
        with self.container.structure.database.session() as session:
            rows = session.scalars(
                select(SegmentRecord)
                .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                .where(ChapterRecord.project_id == project_id)
                .order_by(ChapterRecord.order_index, SceneRecord.order_index, SegmentRecord.order_index)
            )
            return list(rows)

    def _character_index(self, project_id: str) -> CharacterIndex:
        by_name: dict[str, CharacterRecord] = {}
        for character in self.container.casting.characters(project_id):
            if character.merged_into_character_id:
                continue
            names = [character.display_name, character.canonical_name or ""]
            try:
                aliases = json.loads(character.aliases_json)
            except json.JSONDecodeError:
                aliases = []
            if isinstance(aliases, list):
                names.extend(str(item) for item in aliases)
            for name in names:
                key = _name_key(name)
                if key:
                    by_name[key] = character
        return CharacterIndex(by_name=by_name)

    @staticmethod
    def _llm_prompt(segments: list[SegmentRecord], character_index: CharacterIndex) -> str:
        characters = sorted(
            {character.id: character for character in character_index.by_name.values()}.values(),
            key=lambda item: item.display_name,
        )
        character_lines: list[str] = []
        for character in characters:
            aliases = _aliases(character)
            alias_suffix = f" (aliases: {', '.join(aliases)})" if aliases else ""
            character_lines.append(f"{character.display_name}{alias_suffix}")
        segment_lines = "\n".join(
            f"- {segment.id}: {segment.text_content[:500].replace(chr(10), ' ')}"
            for segment in segments
        )
        return (
            "Assign likely speakers for this bounded audiobook segment window. Use only the supplied "
            "Character Bible cast when linking a character. Leave uncertain speakers in review by "
            "returning low confidence. Return JSON that matches the supplied schema.\n\n"
            f"Cast: {'; '.join(character_lines) if character_lines else 'No cast records yet'}\n\n"
            f"Segments:\n{segment_lines}"
        )


def _name_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _aliases(character: CharacterRecord) -> list[str]:
    try:
        aliases = json.loads(character.aliases_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(aliases, list):
        return []
    return [str(item) for item in aliases if str(item).strip()]


def _evidence(payload: str | None) -> dict[str, object]:
    try:
        loaded = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], loaded if isinstance(loaded, dict) else {})


def _confidence(value: object) -> float:
    if isinstance(value, (int, float, str)):
        try:
            return min(max(float(value), 0.0), 1.0)
        except ValueError:
            return 0.0
    return 0.0


def _segment_batches(segments: list[SegmentRecord]) -> list[list[SegmentRecord]]:
    batches: list[list[SegmentRecord]] = []
    current: list[SegmentRecord] = []
    current_chars = 0
    for segment in segments:
        length = len(segment.text_content)
        if (
            current
            and current_chars + length > SPEAKER_ATTRIBUTION_BATCH_CHARS
            or len(current) >= SPEAKER_ATTRIBUTION_BATCH_SEGMENTS
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += length
    if current:
        batches.append(current)
    return batches
