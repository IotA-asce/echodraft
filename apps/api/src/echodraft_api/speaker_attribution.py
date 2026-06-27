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
        speaker_name: str | None
        if segment.segment_type != "dialogue" and not candidate:
            speaker_name = "Narrator"
            confidence = max(segment.speaker_confidence, 0.9)
            status = "approved"
            evidence: dict[str, object] = {
                "reason": "narration_segment",
                "textPreview": segment.text_content[:160],
            }
        else:
            speaker_name = candidate
            confidence = segment.speaker_confidence if candidate else 0.0
            status = "approved" if character and confidence >= 0.7 else "needs_review"
            evidence = {
                "reason": "deterministic_speaker_candidate" if candidate else "dialogue_without_speaker",
                "speakerCandidate": candidate,
                "textPreview": segment.text_content[:160],
                "segmentType": segment.segment_type,
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
        prompt = self._llm_prompt(
            [
                segment_map[item.segment_id]
                for item in unresolved
                if item.segment_id in segment_map
            ],
            character_index,
        )
        from .local_llm import LocalLlmService

        result = LocalLlmService(self.container).extract(
            project_id,
            LlmExtractionRequest(
                model=model,
                task="speaker_attribution",
                schema=SPEAKER_ATTRIBUTION_SCHEMA,
                prompt=prompt,
            ),
            job_id,
        )
        attributions = result.result.get("attributions")
        if not isinstance(attributions, list):
            raise ValueError("Local LLM did not return speaker attributions.")
        for item in attributions:
            if not isinstance(item, dict):
                continue
            payload = cast(dict[str, object], item)
            segment_id = payload.get("segmentId")
            if not isinstance(segment_id, str) or segment_id not in segment_map:
                continue
            speaker_name = str(payload.get("speakerName") or "")
            character_name = str(payload.get("characterName") or speaker_name)
            raw_confidence = payload.get("confidence")
            confidence = (
                float(raw_confidence)
                if isinstance(raw_confidence, (int, float, str))
                else 0.0
            )
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
                },
                confidence=confidence,
                status="approved" if character and confidence >= 0.7 else "needs_review",
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
        characters = sorted({character.display_name for character in character_index.by_name.values()})
        segment_lines = "\n".join(
            f"- {segment.id}: {segment.text_content[:500].replace(chr(10), ' ')}"
            for segment in segments
        )
        return (
            "Assign likely speakers for audiobook dialogue segments. Use only the supplied cast "
            "when possible. Return JSON that matches the supplied schema.\n\n"
            f"Cast: {', '.join(characters) if characters else 'No cast records yet'}\n\n"
            f"Segments:\n{segment_lines}"
        )


def _name_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
