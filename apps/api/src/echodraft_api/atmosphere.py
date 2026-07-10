from __future__ import annotations

import json
import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import cast

from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord
from echodraft_domain import LlmExtractionRequest, LlmExtractionResult
from sqlalchemy import select

from .container import AppContainer
from .local_llm import LocalLlmService

PROFILE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "sceneId": {"type": "string"},
        "locationCategory": {"type": "string"},
        "timeOfDay": {"type": "string"},
        "weather": {"type": "string"},
        "interiorExterior": {"type": "string"},
        "mood": {"type": "string"},
        "tensionLevel": {"type": "number"},
        "explicitSoundEvents": {"type": "array", "items": {"type": "object"}},
        "noSfxRecommended": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": [
        "sceneId",
        "locationCategory",
        "timeOfDay",
        "weather",
        "interiorExterior",
        "mood",
        "tensionLevel",
        "explicitSoundEvents",
        "noSfxRecommended",
        "confidence",
    ],
}

LOCATIONS = {
    "forest": ("forest", "exterior"),
    "woods": ("forest", "exterior"),
    "tavern": ("tavern", "interior"),
    "street": ("city_street", "exterior"),
    "ship": ("ocean_ship", "exterior"),
    "ocean": ("ocean_ship", "exterior"),
    "office": ("office", "interior"),
    "kitchen": ("domestic_interior", "interior"),
    "room": ("generic_interior", "interior"),
}
WEATHER = {"rain": "rain", "storm": "storm", "snow": "snow", "wind": "wind", "fog": "fog"}
TIMES = {"dawn": "dawn", "morning": "morning", "dusk": "dusk", "evening": "evening", "night": "night"}
MOODS = {
    "quiet": "quiet",
    "silent": "quiet",
    "tense": "tense",
    "afraid": "fearful",
    "fear": "fearful",
    "angry": "angry",
    "warm": "warm",
    "bright": "bright",
}
EVENTS = {
    "door slammed": "door_slam",
    "knocked": "knock",
    "thunder": "thunder",
    "glass broke": "glass_break",
    "footsteps": "footsteps",
}


@dataclass(frozen=True)
class SceneText:
    id: str
    chapter_id: str
    text: str


class AtmosphereProfileService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def generate(
        self,
        project_id: str,
        *,
        use_local_llm: bool,
        model: str,
        job_id: str | None = None,
    ) -> dict[str, dict[str, object]]:
        scenes = self._scene_texts(project_id)
        deterministic = {scene.id: deterministic_profile(scene.id, scene.text) for scene in scenes}
        errors: list[str] = []
        refined: dict[str, dict[str, object]] = {}
        if use_local_llm and scenes:
            max_workers = min(len(scenes), self.container.orchestrator_pools.llm.max_workers)

            def refine(scene: SceneText) -> tuple[str, dict[str, object], str | None]:
                try:
                    result = LocalLlmService(self.container).extract(
                        project_id,
                        LlmExtractionRequest(
                            model=model,
                            task="scene_atmosphere_profile",
                            schema=PROFILE_SCHEMA,
                            prompt=_profile_prompt(scene),
                        ),
                        job_id,
                    )
                    return scene.id, normalize_profile(scene.id, result), None
                except ValueError as error:
                    return scene.id, {}, str(error)

            with ThreadPoolExecutor(
                max_workers=max(1, max_workers),
                thread_name_prefix="echodraft-atmosphere",
            ) as executor:
                for scene_id, profile, error in executor.map(refine, scenes):
                    if error:
                        errors.append(f"{scene_id}: {error}")
                    if profile:
                        refined[scene_id] = profile
        accepted = {
            scene.id: refined.get(scene.id) or deterministic[scene.id]
            for scene in scenes
        }
        with self.container.structure.database.session() as session:
            for scene_id, profile in accepted.items():
                record = session.get(SceneRecord, scene_id)
                if record:
                    record.atmosphere_profile_json = json.dumps(profile, sort_keys=True)
            session.commit()
        if errors:
            self.container.review.create_issue(
                project_id=project_id,
                category="sound_design",
                severity="warning",
                title="Some atmosphere profiles used deterministic fallback",
                description=(
                    "Local atmosphere refinement failed for one or more scenes; extraction "
                    "continued and uncertain scenes will receive no automatic ambience."
                ),
                metadata={"failedSceneCount": len(errors), "errors": errors[:10]},
                dedupe_key=f"atmosphere-profile:{project_id}",
            )
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id,
                {
                    "phase": "atmosphere_profiles",
                    "current": len(scenes),
                    "total": len(scenes),
                    "accepted": sum(bool(profile) for profile in accepted.values()),
                },
            )
        return accepted

    def profiles(self, project_id: str) -> dict[str, dict[str, object]]:
        with self.container.structure.database.session() as session:
            rows = session.scalars(
                select(SceneRecord)
                .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                .where(ChapterRecord.project_id == project_id)
            )
            return {row.id: _json_object(row.atmosphere_profile_json) for row in rows}

    def _scene_texts(self, project_id: str) -> list[SceneText]:
        with self.container.structure.database.session() as session:
            rows = list(
                session.execute(
                    select(SceneRecord, SegmentRecord)
                    .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                    .join(SegmentRecord, SegmentRecord.scene_id == SceneRecord.id)
                    .where(ChapterRecord.project_id == project_id)
                    .order_by(
                        ChapterRecord.order_index,
                        SceneRecord.order_index,
                        SegmentRecord.order_index,
                    )
                )
            )
        grouped: dict[str, tuple[str, list[str]]] = {}
        for scene, segment in rows:
            chapter_id, text = grouped.setdefault(scene.id, (scene.chapter_id, []))
            text.append(segment.text_content)
            grouped[scene.id] = (chapter_id, text)
        return [
            SceneText(scene_id, chapter_id, " ".join(text)[:6000])
            for scene_id, (chapter_id, text) in grouped.items()
        ]


def deterministic_profile(scene_id: str, text: str) -> dict[str, object]:
    normalized = text.casefold()
    location = _first_match(normalized, LOCATIONS)
    weather = _first_match(normalized, WEATHER)
    time_of_day = _first_match(normalized, TIMES)
    mood = _first_match(normalized, MOODS)
    evidence_count = sum(value is not None for value in (location, weather, time_of_day, mood))
    events = [
        {"eventType": event_type, "sentenceEvidence": phrase, "confidence": 0.9}
        for phrase, event_type in EVENTS.items()
        if phrase in normalized
    ]
    evidence_count += min(2, len(events))
    confidence = min(0.92, 0.4 + 0.14 * evidence_count)
    if confidence < 0.65:
        return {}
    location_category, interior_exterior = (
        cast(tuple[str, str], location)
        if isinstance(location, tuple)
        else ("unspecified", "unspecified")
    )
    return {
        "sceneId": scene_id,
        "locationCategory": location_category,
        "timeOfDay": time_of_day or "unspecified",
        "weather": weather or "none",
        "interiorExterior": interior_exterior,
        "mood": mood or "neutral",
        "tensionLevel": 0.65 if mood in {"tense", "fearful", "angry"} else 0.25,
        "explicitSoundEvents": events,
        "noSfxRecommended": not bool(events),
        "confidence": round(confidence, 2),
        "source": "deterministic_explicit_evidence",
    }


def normalize_profile(scene_id: str, result: LlmExtractionResult) -> dict[str, object]:
    payload = result.result
    if payload.get("sceneId") != scene_id:
        return {}
    confidence = _clamp(payload.get("confidence"), 0, 1)
    if confidence < 0.65:
        return {}
    location = _choice(
        payload.get("locationCategory"),
        {value[0] for value in LOCATIONS.values()},
        "unspecified",
    )
    raw_events = payload.get("explicitSoundEvents")
    return {
        "sceneId": scene_id,
        "locationCategory": location,
        "timeOfDay": _choice(payload.get("timeOfDay"), set(TIMES.values()), "unspecified"),
        "weather": _choice(payload.get("weather"), {*WEATHER.values(), "none"}, "none"),
        "interiorExterior": _choice(payload.get("interiorExterior"), {"interior", "exterior", "unspecified"}, "unspecified"),
        "mood": _choice(payload.get("mood"), {*MOODS.values(), "neutral", "somber", "urgent"}, "neutral"),
        "tensionLevel": _clamp(payload.get("tensionLevel"), 0, 1),
        "explicitSoundEvents": (
            [item for item in raw_events if isinstance(item, dict)]
            if isinstance(raw_events, list)
            else []
        ),
        "noSfxRecommended": bool(payload.get("noSfxRecommended", False)),
        "confidence": confidence,
        "source": "local_llm",
        "llmRunId": result.run.id,
    }


def _profile_prompt(scene: SceneText) -> str:
    return (
        "Describe only explicit physical and emotional atmosphere evidence for this audiobook "
        "scene. Never invent a sound. Return the requested JSON.\n\n"
        f"TARGET_SCENE_ID: {scene.id}\nCHAPTER_ID: {scene.chapter_id}\nSCENE_TEXT:\n{scene.text}"
    )


def _first_match(text: str, mapping: Mapping[str, object]) -> object | None:
    return next((value for key, value in mapping.items() if re.search(rf"\b{re.escape(key)}\b", text)), None)


def _choice(value: object, allowed: set[str], default: str) -> str:
    normalized = str(value or "").casefold().replace("-", "_").replace(" ", "_")
    return normalized if normalized in allowed else default


def _clamp(value: object, minimum: float, maximum: float) -> float:
    numeric = float(value) if isinstance(value, (int, float)) else minimum
    return round(min(maximum, max(minimum, numeric)), 4)


def _json_object(payload: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], value) if isinstance(value, dict) else {}
