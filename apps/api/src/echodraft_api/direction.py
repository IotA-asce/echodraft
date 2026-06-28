import json
import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import uuid4

from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord
from echodraft_domain import DirectionProfile, SegmentDirection, VoicePreview
from sqlalchemy import select

from .container import AppContainer
from .tts_providers import TtsProvider

CONTROLLED_EMOTIONS = {
    "neutral",
    "warm",
    "tense",
    "quiet",
    "urgent",
    "somber",
    "bright",
    "fearful",
    "angry",
}


class DirectionService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.adapter: TtsProvider = container.tts_adapter

    def preview(
        self, project_id: str, text: str, voice_id: str, direction: DirectionProfile
    ) -> VoicePreview:
        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")
        path = (
            Path(project.artifact_path) / "audio" / "previews" / f"preview_{uuid4().hex[:12]}.wav"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        profile = self.container.casting.voice(voice_id)
        provider_voice_id = profile.provider_voice_id if profile and profile.provider_voice_id else voice_id
        synthesis_text, applied = apply_pronunciations(text, self.container.casting.pronunciations(project_id))
        metadata = self.adapter.preview(synthesis_text, provider_voice_id, path, direction)
        manifest = Path(project.artifact_path) / "manifests" / "direction_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "manifestType": "direction_manifest",
                    "schemaVersion": "0.1.0",
                    "projectId": project_id,
                    "payload": {
                        "voiceProfileId": voice_id,
                        "text": text,
                        "synthesisText": synthesis_text,
                        "pronunciationsApplied": applied,
                        "effectiveDirection": direction.model_dump(by_alias=True),
                        "tts": metadata,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return VoicePreview(
            assetPath=str(path),
            adapter=str(metadata["provider"]),
            modelVersion=str(metadata["modelVersion"]),
            direction=direction,
        )

    def list_segment_directions(self, project_id: str) -> list[SegmentDirection]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        return self.container.segment_directions.all_for_project(project_id)

    def segment_direction(self, project_id: str, segment_id: str) -> SegmentDirection:
        self._validate_segment_project(project_id, segment_id)
        existing = self.container.segment_directions.get(segment_id)
        if existing:
            return existing
        direction = DirectionProfile(scopeType="segment", scopeId=segment_id)
        return self._save(project_id, segment_id, direction, "manual", False)

    def update_segment_direction(
        self, project_id: str, segment_id: str, direction: DirectionProfile, user_locked: bool
    ) -> SegmentDirection:
        self._validate_segment_project(project_id, segment_id)
        return self._save(project_id, segment_id, direction, "manual", user_locked)

    def infer_segment_directions(self, project_id: str, job_id: str | None = None) -> list[SegmentDirection]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        segments = self._segments(project_id)
        for index, segment in enumerate(segments, 1):
            self._save(project_id, segment.id, self._infer(segment), "inferred", False)
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "direction_inference",
                        "current": index,
                        "total": len(segments),
                        "segmentId": segment.id,
                    },
                )
        return self.list_segment_directions(project_id)

    def _save(
        self,
        project_id: str,
        segment_id: str,
        direction: DirectionProfile,
        source: str,
        user_locked: bool,
    ) -> SegmentDirection:
        normalized = self._normalized(direction, segment_id)
        payload = json.dumps(normalized.model_dump(by_alias=True), sort_keys=True)
        return self.container.segment_directions.upsert(
            project_id,
            segment_id,
            payload,
            source,
            user_locked,
            hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

    @staticmethod
    def _normalized(direction: DirectionProfile, segment_id: str) -> DirectionProfile:
        if direction.emotion not in CONTROLLED_EMOTIONS:
            raise ValueError(
                f"Emotion must be one of: {', '.join(sorted(CONTROLLED_EMOTIONS))}."
            )
        return direction.model_copy(update={"scope_type": "segment", "scope_id": segment_id})

    @staticmethod
    def _infer(segment: SegmentRecord) -> DirectionProfile:
        text = segment.text_content.casefold()
        emotion = "neutral"
        intensity = 0.42
        pace = 1.0
        whisper = False
        pause_after = 120
        if any(token in text for token in ("whisper", "softly", "hushed")):
            emotion = "quiet"
            intensity = 0.25
            pace = 0.88
            whisper = True
        elif "!" in segment.text_content or any(token in text for token in ("run", "hurry", "now")):
            emotion = "urgent"
            intensity = 0.72
            pace = 1.12
            pause_after = 80
        elif "?" in segment.text_content:
            emotion = "tense"
            intensity = 0.56
        elif any(token in text for token in ("grief", "alone", "rain", "grave")):
            emotion = "somber"
            intensity = 0.35
            pace = 0.92
            pause_after = 220
        return DirectionProfile(
            scopeType="segment",
            scopeId=segment.id,
            pace=pace,
            intensity=intensity,
            tone=emotion,
            emotion=emotion,
            pauseAfterMs=pause_after,
            whisper=whisper,
            stylePrompt=f"{emotion} audiobook delivery",
        )

    def _validate_segment_project(self, project_id: str, segment_id: str) -> None:
        segment = self.container.structure.segment(segment_id)
        if not segment:
            raise ValueError("Segment not found.")
        with self.container.structure.database.session() as session:
            scene = session.get(SceneRecord, segment.scene_id)
            chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
        if not chapter or chapter.project_id != project_id:
            raise ValueError("Segment or project not found.")

    def _segments(self, project_id: str) -> list[SegmentRecord]:
        with self.container.structure.database.session() as session:
            return list(
                session.scalars(
                    select(SegmentRecord)
                    .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                    .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                    .where(ChapterRecord.project_id == project_id)
                    .order_by(
                        ChapterRecord.order_index,
                        SceneRecord.order_index,
                        SegmentRecord.order_index,
                    )
                )
            )


def apply_pronunciations(text: str, entries: Iterable[Any]) -> tuple[str, list[dict[str, object]]]:
    result = text
    applied: list[dict[str, object]] = []
    for entry in sorted(list(entries), key=lambda item: len(getattr(item, "term", "")), reverse=True):
        term = getattr(entry, "term", "")
        replacement = getattr(entry, "replacement_text", None) or getattr(entry, "phonetic", None)
        if not term or not replacement:
            continue
        pattern = re.compile(rf"\b{re.escape(term)}\b", flags=re.IGNORECASE)
        result, count = pattern.subn(str(replacement), result)
        if count:
            applied.append({"term": str(term), "replacement": str(replacement), "count": str(count)})
    return result, applied
