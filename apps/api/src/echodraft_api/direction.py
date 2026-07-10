import hashlib
import json
import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord
from echodraft_domain import (
    DirectionProfile,
    LlmExtractionRequest,
    SegmentDirection,
    SpeakerAttribution,
    VoicePreview,
)
from sqlalchemy import select

from .container import AppContainer
from .local_llm import LocalLlmService
from .tts_providers import TtsProvider

DIRECTION_INFERENCE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "directions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segmentId": {"type": "string"},
                    "emotion": {"type": "string"},
                    "tone": {"type": "string"},
                    "pace": {"type": "number"},
                    "intensity": {"type": "number"},
                    "pauseBeforeMs": {"type": "integer"},
                    "pauseAfterMs": {"type": "integer"},
                    "stylePrompt": {"type": "string"},
                    "emphasis": {"type": "boolean"},
                    "whisper": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["segmentId", "emotion", "tone", "pace", "intensity", "confidence"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["directions", "warnings"],
}
DIRECTION_INFERENCE_BATCH_CHARS = 5000
DIRECTION_INFERENCE_BATCH_SEGMENTS = 20
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


@dataclass(frozen=True)
class DirectionInferenceWindow:
    segments: list[SegmentRecord]
    target_segment_ids: set[str]


@dataclass(frozen=True)
class ChapterFlowInfo:
    by_segment: dict[str, dict[str, object]]
    last_segment_ids: set[str]


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

    def infer_segment_directions(
        self,
        project_id: str,
        job_id: str | None = None,
        *,
        use_local_llm: bool = False,
        model: str = "qwen3:4b",
    ) -> list[SegmentDirection]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        segments = self._segments(project_id)
        chapter_flow = self._chapter_flow(project_id)
        for index, segment in enumerate(segments, 1):
            self._save(
                project_id,
                segment.id,
                self._infer(segment),
                "inferred",
                False,
                evidence={
                    "reason": "deterministic_direction_inference",
                    "textPreview": segment.text_content[:160],
                },
            )
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
            if (
                self.container.settings.progressive_delivery_enabled
                and job_id
                and segment.id in chapter_flow.last_segment_ids
            ):
                chapter = chapter_flow.by_segment.get(segment.id) or {}
                self._emit_chapter_ready(
                    project_id,
                    job_id,
                    chapter,
                    provisional=True,
                )
        if use_local_llm:
            if self.container.settings.direction_v2_enabled:
                self._apply_local_llm_v2(project_id, model, segments, job_id)
            else:
                self._apply_local_llm(project_id, model, segments, job_id)
        if self.container.settings.direction_v2_enabled:
            self._write_inference_manifest(project_id)
        return self.list_segment_directions(project_id)

    def _save(
        self,
        project_id: str,
        segment_id: str,
        direction: DirectionProfile,
        source: str,
        user_locked: bool,
        evidence: dict[str, object] | None = None,
    ) -> SegmentDirection:
        normalized = self._normalized(direction, segment_id)
        payload = json.dumps(normalized.model_dump(by_alias=True), sort_keys=True)
        evidence_payload = json.dumps(evidence or {}, sort_keys=True)
        return self.container.segment_directions.upsert(
            project_id,
            segment_id,
            payload,
            source,
            user_locked,
            hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            evidence_payload,
        )

    def _apply_local_llm(
        self,
        project_id: str,
        model: str,
        segments: list[SegmentRecord],
        job_id: str | None,
    ) -> None:
        segment_ids = [segment.id for segment in segments]
        existing_records = self.container.segment_directions.records(segment_ids)
        target_segments = [
            segment
            for segment in segments
            if not existing_records.get(segment.id)
            or not existing_records[segment.id].user_locked
        ]
        if not target_segments:
            return
        segment_map = {segment.id: segment for segment in segments}
        direction_hints = {item.segment_id: item for item in self.list_segment_directions(project_id)}
        attributions = {
            item.segment_id: item for item in self.container.speaker_attributions.list_attributions(project_id)
        }
        windows = list(_direction_context_windows(segments, target_segments))
        for batch_index, window in enumerate(windows, 1):
            scene_window_segment_ids = [segment.id for segment in window.segments]
            target_segment_ids = [
                segment.id for segment in window.segments if segment.id in window.target_segment_ids
            ]
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "llm_direction_inference",
                        "current": batch_index,
                        "total": len(windows),
                    },
                )
            try:
                result = LocalLlmService(self.container).extract(
                    project_id,
                    LlmExtractionRequest(
                        model=model,
                        task="direction_inference",
                        schema=DIRECTION_INFERENCE_SCHEMA,
                        prompt=self._llm_prompt(
                            window.segments,
                            target_segment_ids=window.target_segment_ids,
                            attributions=attributions,
                            direction_hints=direction_hints,
                        ),
                    ),
                    job_id,
                )
            except ValueError as error:
                self.container.review.create_issue(
                    project_id=project_id,
                    category="direction",
                    severity="warning",
                    title="LLM direction inference skipped a segment window",
                    description=(
                        "Local Ollama failed while inferring delivery directions; "
                        "deterministic directions remain in place."
                    ),
                    metadata={"error": str(error)[:500], "segmentIds": target_segment_ids},
                    dedupe_key=f"direction-llm:{project_id}:{target_segment_ids[0]}",
                )
                continue
            directions = result.result.get("directions")
            if not isinstance(directions, list):
                continue
            for item in directions:
                if not isinstance(item, dict):
                    continue
                payload = cast(dict[str, object], item)
                segment_id = payload.get("segmentId")
                if not isinstance(segment_id, str) or segment_id not in window.target_segment_ids:
                    continue
                segment = segment_map.get(segment_id)
                if not segment:
                    continue
                direction = _direction_from_llm_payload(payload, segment_id)
                if not direction:
                    continue
                speaker_name = _speaker_name(segment, attributions.get(segment_id))
                confidence = _confidence(payload.get("confidence"))
                self._save(
                    project_id,
                    segment_id,
                    direction,
                    "llm_inferred",
                    False,
                    evidence={
                        "reason": "llm_direction_inference",
                        "llmRunId": result.run.id,
                        "model": model,
                        "confidence": confidence,
                        "sceneWindowSegmentIds": scene_window_segment_ids,
                        "targetSegmentIds": target_segment_ids,
                        "speakerName": speaker_name,
                        "evidence": str(payload.get("evidence") or "")[:500],
                        "textPreview": segment.text_content[:160],
                    },
                )

    def _apply_local_llm_v2(
        self,
        project_id: str,
        model: str,
        segments: list[SegmentRecord],
        job_id: str | None,
    ) -> None:
        existing_records = self.container.segment_directions.records(
            [segment.id for segment in segments]
        )
        target_segments = [
            segment
            for segment in segments
            if not existing_records.get(segment.id)
            or not existing_records[segment.id].user_locked
        ]
        if not target_segments:
            return
        segment_map = {segment.id: segment for segment in segments}
        direction_hints = {
            item.segment_id: item for item in self.list_segment_directions(project_id)
        }
        attributions = {
            item.segment_id: item
            for item in self.container.speaker_attributions.list_attributions(project_id)
        }
        windows = list(_direction_context_windows(segments, target_segments))
        llm = LocalLlmService(self.container)
        max_workers = min(len(windows), self.container.orchestrator_pools.llm.max_workers)

        def infer_window(
            index: int, window: DirectionInferenceWindow
        ) -> tuple[int, DirectionInferenceWindow, object]:
            request = LlmExtractionRequest(
                model=model,
                task="direction_v2_map",
                schema=DIRECTION_INFERENCE_SCHEMA,
                prompt=self._llm_prompt_v2(
                    project_id,
                    window,
                    attributions=attributions,
                    direction_hints=direction_hints,
                ),
            )
            try:
                return index, window, llm.extract(project_id, request, job_id)
            except ValueError as error:
                return index, window, error

        results: list[tuple[int, DirectionInferenceWindow, object]] = []
        with ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="echodraft-direction-v2",
        ) as executor:
            futures = [
                executor.submit(infer_window, index, window)
                for index, window in enumerate(windows, 1)
            ]
            for future in futures:
                results.append(future.result())

        for index, window, outcome in sorted(results, key=lambda item: item[0]):
            target_ids = sorted(window.target_segment_ids)
            if isinstance(outcome, ValueError):
                self.container.review.create_issue(
                    project_id=project_id,
                    category="direction",
                    severity="warning",
                    title="Direction v2 kept deterministic window results",
                    description=(
                        "Local direction refinement failed; deterministic directions remain."
                    ),
                    metadata={"error": str(outcome)[:500], "segmentIds": target_ids},
                    dedupe_key=f"direction-v2:{project_id}:{target_ids[0]}",
                )
                continue
            result = cast(Any, outcome)
            directions = result.result.get("directions")
            if not isinstance(directions, list):
                continue
            profile_inputs = self._profile_inputs(window, attributions)
            for raw in directions:
                if not isinstance(raw, dict):
                    continue
                payload = cast(dict[str, object], raw)
                segment_id = payload.get("segmentId")
                if not isinstance(segment_id, str) or segment_id not in window.target_segment_ids:
                    continue
                segment = segment_map.get(segment_id)
                if not segment:
                    continue
                direction = _direction_from_llm_payload(payload, segment_id)
                if not direction:
                    continue
                self._save(
                    project_id,
                    segment_id,
                    direction,
                    "llm_inferred",
                    False,
                    evidence={
                        "reason": "direction_v2_scene_window",
                        "llmRunId": result.run.id,
                        "model": model,
                        "confidence": _confidence(payload.get("confidence")),
                        "sceneWindowSegmentIds": [item.id for item in window.segments],
                        "targetSegmentIds": target_ids,
                        "speakerName": _speaker_name(
                            segment, attributions.get(segment_id)
                        ),
                        "profileInputs": profile_inputs,
                        "evidence": str(payload.get("evidence") or "")[:500],
                    },
                )
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "llm_direction_v2",
                        "current": index,
                        "total": len(windows),
                    },
                )
        if self.container.settings.progressive_delivery_enabled and job_id:
            flow = self._chapter_flow(project_id)
            emitted: set[str] = set()
            for chapter in flow.by_segment.values():
                chapter_id = str(chapter.get("chapterId") or "")
                if chapter_id and chapter_id not in emitted:
                    self._emit_chapter_ready(
                        project_id, job_id, chapter, provisional=False
                    )
                    emitted.add(chapter_id)

    def _llm_prompt_v2(
        self,
        project_id: str,
        window: DirectionInferenceWindow,
        *,
        attributions: dict[str, SpeakerAttribution],
        direction_hints: dict[str, SegmentDirection],
    ) -> str:
        base = self._llm_prompt(
            window.segments,
            target_segment_ids=window.target_segment_ids,
            attributions=attributions,
            direction_hints=direction_hints,
        )
        profiles = self._profile_inputs(window, attributions)
        return (
            "Direction v2: treat each character profile as the baseline delivery style and infer "
            "only the scene-specific deviation. Preserve conservative audiobook delivery.\n\n"
            f"Project: {project_id}\n"
            f"Character profiles: {json.dumps(profiles, sort_keys=True)}\n\n"
            f"{base}"
        )

    def _profile_inputs(
        self,
        window: DirectionInferenceWindow,
        attributions: dict[str, SpeakerAttribution],
    ) -> list[dict[str, object]]:
        character_ids = {
            attribution.character_id
            for segment in window.segments
            if (attribution := attributions.get(segment.id))
            and attribution.character_id
        }
        profiles: list[dict[str, object]] = []
        for character_id in sorted(character_ids):
            character = self.container.casting.character(character_id)
            if not character:
                continue
            profiles.append(
                {
                    "characterId": character.id,
                    "displayName": character.display_name,
                    "traits": _json_array(character.traits_json),
                    "speakingStyle": _json_array(character.speaking_style_json),
                }
            )
        return profiles

    def _chapter_flow(self, project_id: str) -> ChapterFlowInfo:
        with self.container.structure.database.session() as session:
            rows = list(
                session.execute(
                    select(
                        SegmentRecord.id,
                        ChapterRecord.id,
                        ChapterRecord.order_index,
                        ChapterRecord.title,
                    )
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
        by_segment: dict[str, dict[str, object]] = {}
        segments_by_chapter: dict[str, list[str]] = {}
        for segment_id, chapter_id, chapter_order, title in rows:
            by_segment[segment_id] = {
                "chapterId": chapter_id,
                "chapterOrder": chapter_order,
                "title": title,
            }
            segments_by_chapter.setdefault(chapter_id, []).append(segment_id)
        return ChapterFlowInfo(
            by_segment=by_segment,
            last_segment_ids={ids[-1] for ids in segments_by_chapter.values() if ids},
        )

    def _emit_chapter_ready(
        self,
        project_id: str,
        job_id: str,
        chapter: dict[str, object],
        *,
        provisional: bool,
    ) -> None:
        chapter_id = str(chapter.get("chapterId") or "")
        if not chapter_id:
            return
        chapter_order_value = chapter.get("chapterOrder")
        chapter_order = (
            int(chapter_order_value)
            if isinstance(chapter_order_value, (int, float, str))
            and not isinstance(chapter_order_value, bool)
            else 0
        )
        self.container.orchestrator_repository.upsert_checkpoint(
            unit_key=f"chapter_direction:{job_id}:{chapter_id}:{'provisional' if provisional else 'final'}",
            job_id=job_id,
            project_id=project_id,
            stage="chapter-flow.direction-ready",
            stage_version="2",
            scope={"chapterId": chapter_id, "chapterOrder": chapter_order},
            status="done",
            output_ref=f"manifests/direction_manifest.json#chapter={chapter_id}",
        )
        self.container.orchestrator_repository.append_event(
            job_id=job_id,
            project_id=project_id,
            event_type="chapter.direction.ready",
            stage="direction",
            scope={"chapterId": chapter_id, "chapterOrder": chapter_order},
            payload={
                "provisional": provisional,
                "priority": 10 + chapter_order,
                "title": chapter.get("title"),
            },
        )

    def _write_inference_manifest(self, project_id: str) -> None:
        project = self.container.projects.get(project_id)
        if not project:
            return
        rows = self.list_segment_directions(project_id)
        manifest = {
            "manifestType": "direction_manifest",
            "schemaVersion": "0.2.0",
            "manifestVersion": "direction-v2",
            "projectId": project_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "payload": {
                "rows": [
                    {
                        "segmentId": row.segment_id,
                        "source": row.source,
                        "userLocked": row.user_locked,
                        "direction": row.direction.model_dump(by_alias=True),
                        "llmRunId": row.evidence.get("llmRunId"),
                        "profileInputs": row.evidence.get("profileInputs") or [],
                    }
                    for row in rows
                ]
            },
        }
        root = Path(project.artifact_path) / "manifests"
        root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(manifest, indent=2)
        (root / f"direction_manifest.{uuid4().hex[:12]}.json").write_text(
            payload, encoding="utf-8"
        )
        (root / "direction_manifest.json").write_text(payload, encoding="utf-8")

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

    @staticmethod
    def _llm_prompt(
        segments: list[SegmentRecord],
        *,
        target_segment_ids: set[str],
        attributions: dict[str, SpeakerAttribution],
        direction_hints: dict[str, SegmentDirection],
    ) -> str:
        segment_lines: list[str] = []
        for segment in segments:
            role = "TARGET" if segment.id in target_segment_ids else "CONTEXT"
            speaker_hint = _speaker_prompt_hint(segment, attributions.get(segment.id))
            direction_hint = _direction_hint(direction_hints.get(segment.id))
            segment_lines.append(
                f"- {role} {segment.id} "
                f"[type={segment.segment_type}; {speaker_hint}; "
                f"existingDirection={direction_hint}]: "
                f"{segment.text_content[:500].replace(chr(10), ' ')}"
            )
        return (
            "Infer audiobook delivery directions for TARGET segments using same-scene context. "
            "Use CONTEXT lines only as evidence for continuity, mood, speaker intent, and nearby "
            "previous/next segments. Return direction rows only for TARGET segment IDs; never "
            "return CONTEXT-only segment IDs. Keep outputs conservative and reviewable. Return JSON "
            "that matches the supplied schema.\n\n"
            f"Allowed emotions: {', '.join(sorted(CONTROLLED_EMOTIONS))}\n"
            "Direction controls: emotion, tone, pace from 0.5 to 2.0, intensity from 0.0 to 1.0, "
            "pauseBeforeMs, pauseAfterMs, stylePrompt, emphasis, whisper, confidence, evidence.\n\n"
            f"Segments:\n{chr(10).join(segment_lines)}"
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


def _json_array(payload: str | None) -> list[object]:
    try:
        value = json.loads(payload or "[]")
    except json.JSONDecodeError:
        return []
    return cast(list[object], value if isinstance(value, list) else [])


def _direction_context_windows(
    segments: list[SegmentRecord],
    target_segments: list[SegmentRecord],
) -> list[DirectionInferenceWindow]:
    if not target_segments:
        return []
    scene_segments: dict[str, list[SegmentRecord]] = {}
    for segment in segments:
        scene_segments.setdefault(segment.scene_id, []).append(segment)
    targets_by_scene: dict[str, list[SegmentRecord]] = {}
    for target in target_segments:
        targets_by_scene.setdefault(target.scene_id, []).append(target)

    windows: list[DirectionInferenceWindow] = []
    for scene_id, targets in targets_by_scene.items():
        ordered_scene = scene_segments.get(scene_id, [])
        if not ordered_scene:
            continue
        if _fits_llm_window(ordered_scene):
            windows.append(
                DirectionInferenceWindow(
                    segments=ordered_scene,
                    target_segment_ids={target.id for target in targets},
                )
            )
            continue
        for target_batch in _segment_batches(targets):
            target_ids = {target.id for target in target_batch}
            windows.append(
                DirectionInferenceWindow(
                    segments=_bounded_scene_window(ordered_scene, target_ids),
                    target_segment_ids=target_ids,
                )
            )
    return windows


def _bounded_scene_window(
    scene_segments: list[SegmentRecord], target_segment_ids: set[str]
) -> list[SegmentRecord]:
    target_positions = [
        index for index, segment in enumerate(scene_segments) if segment.id in target_segment_ids
    ]
    if not target_positions:
        return []
    start = min(target_positions)
    end = max(target_positions)
    window = scene_segments[start : end + 1]
    left = start - 1
    right = end + 1
    while left >= 0 or right < len(scene_segments):
        added = False
        if left >= 0 and _fits_llm_window([scene_segments[left], *window]):
            window = [scene_segments[left], *window]
            left -= 1
            added = True
        if right < len(scene_segments) and _fits_llm_window([*window, scene_segments[right]]):
            window = [*window, scene_segments[right]]
            right += 1
            added = True
        if not added:
            break
    return window


def _fits_llm_window(segments: list[SegmentRecord]) -> bool:
    return (
        len(segments) <= DIRECTION_INFERENCE_BATCH_SEGMENTS
        and sum(len(segment.text_content) for segment in segments) <= DIRECTION_INFERENCE_BATCH_CHARS
    )


def _segment_batches(segments: list[SegmentRecord]) -> list[list[SegmentRecord]]:
    batches: list[list[SegmentRecord]] = []
    current: list[SegmentRecord] = []
    current_chars = 0
    for segment in segments:
        length = len(segment.text_content)
        if current and (
            current_chars + length > DIRECTION_INFERENCE_BATCH_CHARS
            or len(current) >= DIRECTION_INFERENCE_BATCH_SEGMENTS
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += length
    if current:
        batches.append(current)
    return batches


def _direction_from_llm_payload(
    payload: dict[str, object], segment_id: str
) -> DirectionProfile | None:
    emotion = str(payload.get("emotion") or "").strip().casefold()
    if emotion not in CONTROLLED_EMOTIONS:
        return None
    tone = str(payload.get("tone") or emotion).strip() or emotion
    try:
        return DirectionProfile(
            scopeType="segment",
            scopeId=segment_id,
            pace=_bounded_float(payload.get("pace"), 0.5, 2.0, 1.0),
            intensity=_bounded_float(payload.get("intensity"), 0.0, 1.0, 0.5),
            tone=tone[:80],
            emotion=emotion,
            pauseBeforeMs=_bounded_int(payload.get("pauseBeforeMs"), 0, 5000, 0),
            pauseAfterMs=_bounded_int(payload.get("pauseAfterMs"), 0, 5000, 120),
            stylePrompt=_style_prompt(payload.get("stylePrompt"), emotion),
            emphasis=bool(payload.get("emphasis", False)),
            whisper=bool(payload.get("whisper", False)),
            noSfx=True,
        )
    except ValueError:
        return None


def _bounded_float(value: object, minimum: float, maximum: float, fallback: float) -> float:
    if isinstance(value, (int, float, str)):
        try:
            return min(max(float(value), minimum), maximum)
        except ValueError:
            return fallback
    return fallback


def _bounded_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
    if isinstance(value, (int, float, str)):
        try:
            return min(max(int(float(value)), minimum), maximum)
        except ValueError:
            return fallback
    return fallback


def _style_prompt(value: object, emotion: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()[:240]
    return f"{emotion} audiobook delivery"


def _confidence(value: object) -> float:
    return _bounded_float(value, 0.0, 1.0, 0.0)


def _speaker_name(segment: SegmentRecord, attribution: SpeakerAttribution | None) -> str:
    if attribution and attribution.speaker_name:
        return attribution.speaker_name
    if segment.speaker_candidate:
        return segment.speaker_candidate
    return ""


def _speaker_prompt_hint(segment: SegmentRecord, attribution: SpeakerAttribution | None) -> str:
    candidate = segment.speaker_candidate or "Unknown"
    approved = (
        attribution.speaker_name
        if attribution and attribution.status == "approved" and attribution.speaker_name
        else "None"
    )
    return f"speakerCandidate={candidate}; approvedSpeaker={approved}"


def _direction_hint(direction: SegmentDirection | None) -> str:
    if not direction:
        return "none"
    profile = direction.direction
    return (
        f"{profile.emotion}; tone={profile.tone}; pace={profile.pace:.2f}; "
        f"intensity={profile.intensity:.2f}; pauseAfterMs={profile.pause_after_ms}; "
        f"source={direction.source}"
    )
