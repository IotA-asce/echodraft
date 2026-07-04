from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import cast

from echodraft_db.models import ChapterRecord, CharacterRecord, SceneRecord, SegmentRecord
from echodraft_domain import (
    LlmExtractionRequest,
    SpeakerAttribution,
    SpeakerAttributionUpdateResult,
)
from sqlalchemy import select

from .container import AppContainer
from .local_llm import LocalLlmService

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
            previous_segment = segments[index - 2] if index >= 2 else None
            next_segment = segments[index] if index < len(segments) else None
            self._upsert_deterministic(
                project_id, segment, character_index, previous_segment, next_segment
            )
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
    ) -> SpeakerAttributionUpdateResult:
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
        propagated = 0
        # A confirmation that links a character teaches every unresolved sibling
        # line with the same speaker hint -- one click, many rows.
        if (
            update_character
            and record.character_id
            and record.status == "approved"
            and self._speaker_matches_character(record.speaker_name, record.character_id)
        ):
            propagated = self.container.speaker_attributions.propagate_confirmation(
                record.project_id,
                source_attribution_id=record.id,
                character_id=record.character_id,
                speaker_name=record.speaker_name,
            )
        return SpeakerAttributionUpdateResult.model_validate(
            {**record.model_dump(), "propagatedCount": propagated}
        )

    def _upsert_deterministic(
        self,
        project_id: str,
        segment: SegmentRecord,
        character_index: CharacterIndex,
        previous_segment: SegmentRecord | None = None,
        next_segment: SegmentRecord | None = None,
    ) -> SpeakerAttribution:
        candidate = segment.speaker_candidate.strip() if segment.speaker_candidate else None
        turn_hint = (
            _nearby_turn_hint(segment, previous_segment, next_segment)
            if not candidate and _looks_like_dialogue(segment.text_content)
            else None
        )
        if turn_hint:
            candidate = turn_hint["speakerName"]
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
                "reason": turn_hint["reason"]
                if turn_hint
                else "deterministic_speaker_candidate"
                if candidate
                else "dialogue_without_speaker",
                "speakerCandidate": candidate,
                "textPreview": segment.text_content[:160],
                "segmentType": segment.segment_type,
                "source": "structure_parser",
                "speakerRule": parser_evidence.get("speakerRule"),
                "productionType": parser_evidence.get("productionType"),
                "structure": parser_evidence,
            }
            if turn_hint:
                evidence.update(turn_hint)
                confidence = min(max(confidence, 0.58), 0.72)
                status = "needs_review"
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

        exemplars = self.container.speaker_attributions.locked_exemplars(project_id, limit=5)
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
                        prompt=self._llm_prompt(batch, character_index, exemplars),
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

    def _speaker_matches_character(self, speaker_name: str | None, character_id: str) -> bool:
        key = _name_key(speaker_name)
        if not key:
            return False
        character = self.container.casting.character(character_id)
        if not character:
            return False
        names = [character.display_name, character.canonical_name or ""]
        names.extend(_aliases(character))
        return key in {_name_key(name) for name in names}

    @staticmethod
    def _llm_prompt(
        segments: list[SegmentRecord],
        character_index: CharacterIndex,
        exemplars: list[tuple[str, str]] | None = None,
    ) -> str:
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
        exemplar_block = ""
        if exemplars:
            exemplar_lines = "\n".join(
                f'Text: "{text[:120].replace(chr(10), " ")}" → Speaker: {name}'
                for name, text in exemplars[:5]
            )
            exemplar_block = (
                "Reviewer-confirmed examples from this book (follow this style):\n"
                f"{exemplar_lines}\n\n"
            )
        return (
            "Assign likely speakers for this bounded audiobook segment window. Use only the supplied "
            "Character Bible cast when linking a character. Leave uncertain speakers in review by "
            "returning low confidence. Return JSON that matches the supplied schema.\n\n"
            f"{exemplar_block}"
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


def _nearby_turn_hint(
    segment: SegmentRecord,
    previous_segment: SegmentRecord | None,
    next_segment: SegmentRecord | None,
) -> dict[str, str] | None:
    pronoun = (
        _pronoun_cue(segment.text_content)
        or _pronoun_cue(next_segment.text_content if next_segment else "")
        or _pronoun_cue(previous_segment.text_content if previous_segment else "")
    )
    previous_speaker = (
        previous_segment.speaker_candidate.strip()
        if previous_segment and previous_segment.speaker_candidate
        else None
    )
    next_speaker = (
        next_segment.speaker_candidate.strip() if next_segment and next_segment.speaker_candidate else None
    )
    speaker_name = previous_speaker or next_speaker
    if not speaker_name or not pronoun:
        return None
    return {
        "reason": "nearby_dialogue_turn",
        "speakerName": speaker_name,
        "previousSpeaker": previous_speaker or "",
        "nextSpeaker": next_speaker or "",
        "pronounCue": pronoun,
    }


def _pronoun_cue(text: str) -> str | None:
    lowered = text.casefold()
    for pronoun in ("she", "he", "they"):
        if re.search(rf"\b{pronoun}\b\s+(?:said|asked|replied|answered|whispered|called)", lowered):
            return pronoun
    return None


def _looks_like_dialogue(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(('"', "'", "“", "‘")) or stripped.endswith(('"', "'", "”", "’"))


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
