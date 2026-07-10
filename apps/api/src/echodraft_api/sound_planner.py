from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from echodraft_db.models import (
    AmbienceAssetRecord,
    AmbienceCueRecord,
    ChapterRenderRecord,
    SceneRecord,
)
from echodraft_domain import SoundPlanResult
from sqlalchemy import delete, select

from .atmosphere import AtmosphereProfileService
from .container import AppContainer
from .tier0_sound import LICENSE_NOTE, TierZeroSoundBank

MIN_SCENE_CONFIDENCE = 0.65
MIN_SFX_CONFIDENCE = 0.8
MIN_ANCHOR_JACCARD = 0.35


@dataclass(frozen=True)
class SegmentPlanInput:
    id: str
    text: str
    start_ms: int | None
    end_ms: int | None
    no_sfx: bool = False


@dataclass(frozen=True)
class SoundPlanSettings:
    sfx_budget_light: int = 2
    sfx_budget_dramatized: int = 5
    allow_opening_music: bool = True
    allow_peak_music: bool = True


@dataclass(frozen=True)
class PlannedSoundCue:
    scene_id: str
    kind: str
    rule: str
    tags: tuple[str, ...]
    plan_key: str
    run_scene_ids: tuple[str, ...] = ()
    event_type: str | None = None
    segment_id: str | None = None
    start_ms: int = 0
    sentence_evidence: str | None = None
    profile_evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SkippedSound:
    scene_id: str
    reason: str
    event_type: str | None = None
    sentence_evidence: str | None = None


@dataclass(frozen=True)
class SoundPlan:
    chapter_id: str
    render_mode: str
    cues: tuple[PlannedSoundCue, ...]
    skipped: tuple[SkippedSound, ...]
    sfx_used: int
    sfx_limit: int


def plan_chapter_sound(
    chapter_id: str,
    scene_ids: list[str],
    profiles: dict[str, dict[str, object]],
    segments: dict[str, tuple[SegmentPlanInput, ...]],
    render_mode: str,
    settings: SoundPlanSettings | None = None,
) -> SoundPlan:
    resolved_settings = settings or SoundPlanSettings()
    limit = (
        resolved_settings.sfx_budget_dramatized
        if render_mode == "dramatized"
        else resolved_settings.sfx_budget_light
    )
    if render_mode == "speech_only":
        return SoundPlan(chapter_id, render_mode, (), (), 0, limit)

    cues: list[PlannedSoundCue] = []
    skipped: list[SkippedSound] = []
    sfx_used = 0
    previous_signature: tuple[str, ...] | None = None
    previous_bed_index: int | None = None
    running_max_tension = 0.0
    peak_logged = False

    for index, scene_id in enumerate(scene_ids):
        profile = profiles.get(scene_id) or {}
        if _number(profile.get("confidence")) < MIN_SCENE_CONFIDENCE:
            skipped.append(SkippedSound(scene_id, "low_or_missing_profile_confidence"))
            previous_signature = None
            previous_bed_index = None
            continue

        signature = tuple(
            _normalized(profile.get(key), fallback)
            for key, fallback in (
                ("locationCategory", "unspecified"),
                ("interiorExterior", "unspecified"),
                ("weather", "none"),
                ("timeOfDay", "unspecified"),
            )
        )
        if signature == previous_signature and previous_bed_index is not None:
            previous = cues[previous_bed_index]
            cues[previous_bed_index] = PlannedSoundCue(
                **{
                    **asdict(previous),
                    "tags": previous.tags,
                    "run_scene_ids": (*previous.run_scene_ids, scene_id),
                }
            )
        else:
            tags = _bed_tags(profile)
            plan_key = _plan_key(
                chapter_id,
                render_mode,
                "scene_ambience_bed",
                scene_id,
                tags,
            )
            cues.append(
                PlannedSoundCue(
                    scene_id=scene_id,
                    kind="ambience",
                    rule="scene_ambience_bed",
                    tags=tags,
                    plan_key=plan_key,
                    run_scene_ids=(scene_id,),
                    profile_evidence=_profile_evidence(profile),
                )
            )
            previous_bed_index = len(cues) - 1
        previous_signature = signature

        tension = _number(profile.get("tensionLevel"))
        if index == 0 and resolved_settings.allow_opening_music:
            skipped.append(SkippedSound(scene_id, "tier0_music_unavailable"))
        elif (
            render_mode == "dramatized"
            and resolved_settings.allow_peak_music
            and not peak_logged
            and tension >= 0.8
            and tension - running_max_tension >= 0.3
        ):
            skipped.append(SkippedSound(scene_id, "tier0_music_unavailable"))
            peak_logged = True
        running_max_tension = max(running_max_tension, tension)

        events = profile.get("explicitSoundEvents")
        if not isinstance(events, list):
            continue
        for raw_event in events:
            if not isinstance(raw_event, dict):
                continue
            event = cast(dict[str, object], raw_event)
            event_type = _normalized(event.get("eventType"), "unknown")
            sentence = str(event.get("sentenceEvidence") or "").strip()
            if bool(profile.get("noSfxRecommended")):
                skipped.append(
                    SkippedSound(scene_id, "scene_no_sfx_recommended", event_type, sentence)
                )
                continue
            if _number(event.get("confidence")) < MIN_SFX_CONFIDENCE:
                skipped.append(SkippedSound(scene_id, "low_event_confidence", event_type, sentence))
                continue
            anchor = _locate_anchor(sentence, segments.get(scene_id, ()))
            if anchor is None:
                skipped.append(SkippedSound(scene_id, "no_timeline_anchor", event_type, sentence))
                continue
            segment, start_ms = anchor
            if segment.no_sfx:
                skipped.append(SkippedSound(scene_id, "segment_no_sfx_flag", event_type, sentence))
                continue
            if sfx_used >= limit:
                skipped.append(
                    SkippedSound(scene_id, "chapter_sfx_budget_exhausted", event_type, sentence)
                )
                continue
            tags = (event_type, *signature)
            plan_key = _plan_key(
                chapter_id,
                render_mode,
                "explicit_sound_event",
                scene_id,
                tags,
                segment.id,
                start_ms,
                sentence,
            )
            cues.append(
                PlannedSoundCue(
                    scene_id=scene_id,
                    kind="sfx",
                    rule="explicit_sound_event",
                    tags=tags,
                    plan_key=plan_key,
                    event_type=event_type,
                    segment_id=segment.id,
                    start_ms=start_ms,
                    sentence_evidence=sentence,
                    profile_evidence=_profile_evidence(profile),
                )
            )
            sfx_used += 1

    return SoundPlan(chapter_id, render_mode, tuple(cues), tuple(skipped), sfx_used, limit)


class SoundPlannerService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def run(self, project_id: str, chapter_id: str, render_mode: str) -> SoundPlanResult:
        project = self.container.projects.get(project_id)
        chapter = self.container.structure.chapter(chapter_id)
        if not project or not chapter or chapter.project_id != project_id:
            raise ValueError("Chapter or project not found.")
        scenes = self.container.structure.scenes(chapter_id)
        preserved_profiles = {
            scene.id: scene.atmosphere_profile_json
            for scene in scenes
            if _json_object(scene.atmosphere_profile_json)
        }
        if len(preserved_profiles) != len(scenes):
            AtmosphereProfileService(self.container).generate(
                project_id, use_local_llm=False, model=""
            )
            if preserved_profiles:
                with self.container.structure.database.session() as session:
                    for scene_id, profile_json in preserved_profiles.items():
                        record = session.get(SceneRecord, scene_id)
                        if record:
                            record.atmosphere_profile_json = profile_json
                    session.commit()
            scenes = self.container.structure.scenes(chapter_id)
        profiles = {scene.id: _json_object(scene.atmosphere_profile_json) for scene in scenes}
        timeline = self._latest_timeline(chapter_id)
        segment_inputs = self._segment_inputs(scenes, timeline)
        settings = self._settings(project_id)
        plan = plan_chapter_sound(
            chapter_id,
            [scene.id for scene in scenes],
            profiles,
            segment_inputs,
            render_mode,
            settings,
        )
        assets, cues = self._materialize(project_id, plan)
        manifest_path = self._write_manifest(
            Path(project.artifact_path), project_id, profiles, plan, assets, cues
        )
        return SoundPlanResult(
            chapterId=chapter_id,
            renderMode=render_mode,
            manifestPath=str(manifest_path),
            plannedCues=[_cue_payload(cue) for cue in plan.cues],
            skipped=[asdict(item) for item in plan.skipped],
            materializedAssetIds=assets,
            materializedCueIds=cues,
        )

    def _settings(self, project_id: str) -> SoundPlanSettings:
        record = self.container.production.get(project_id)
        raw = _json_object(record.auto_sound_design_json or "{}")
        budgets = raw.get("sfxBudget")
        budget = cast(dict[str, object], budgets) if isinstance(budgets, dict) else {}
        return SoundPlanSettings(
            sfx_budget_light=_bounded_budget(budget.get("light"), 2),
            sfx_budget_dramatized=_bounded_budget(budget.get("dramatized"), 5),
            allow_opening_music=bool(raw.get("allowOpeningMusic", True)),
            allow_peak_music=bool(raw.get("allowPeakMusic", True)),
        )

    def _segment_inputs(
        self,
        scenes: list[SceneRecord],
        timeline: dict[str, tuple[int, int]],
    ) -> dict[str, tuple[SegmentPlanInput, ...]]:
        all_segments = [segment for scene in scenes for segment in self.container.structure.segments(scene.id)]
        directions = self.container.segment_directions.records([segment.id for segment in all_segments])
        result: dict[str, tuple[SegmentPlanInput, ...]] = {}
        for scene in scenes:
            scene_segments = [segment for segment in all_segments if segment.scene_id == scene.id]
            starts = [timeline[segment.id][0] for segment in scene_segments if segment.id in timeline]
            scene_start = min(starts) if starts else None
            inputs: list[SegmentPlanInput] = []
            for segment in scene_segments:
                span = timeline.get(segment.id)
                direction = directions.get(segment.id)
                direction_payload = _json_object(direction.direction_json) if direction else {}
                inputs.append(
                    SegmentPlanInput(
                        segment.id,
                        segment.normalized_text,
                        span[0] - scene_start if span and scene_start is not None else None,
                        span[1] - scene_start if span and scene_start is not None else None,
                        bool(direction_payload.get("noSfx", False)),
                    )
                )
            result[scene.id] = tuple(inputs)
        return result

    def _latest_timeline(self, chapter_id: str) -> dict[str, tuple[int, int]]:
        with self.container.structure.database.session() as session:
            render = session.scalar(
                select(ChapterRenderRecord)
                .where(ChapterRenderRecord.chapter_id == chapter_id)
                .where(ChapterRenderRecord.status == "succeeded")
                .order_by(ChapterRenderRecord.created_at.desc(), ChapterRenderRecord.id.desc())
            )
        if not render or not Path(render.manifest_path).is_file():
            return {}
        payload = _json_object(Path(render.manifest_path).read_text(encoding="utf-8"))
        entries = payload.get("timeline")
        if not isinstance(entries, list):
            return {}
        timeline: dict[str, tuple[int, int]] = {}
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            segment_id = raw.get("segmentId")
            start = raw.get("startMs")
            end = raw.get("endMs")
            if isinstance(segment_id, str) and isinstance(start, int) and isinstance(end, int):
                timeline[segment_id] = (start, end)
        return timeline

    def _materialize(self, project_id: str, plan: SoundPlan) -> tuple[list[str], list[str]]:
        if plan.render_mode == "speech_only":
            return [], []
        bank = TierZeroSoundBank(
            self.container.settings.artifact_root.parent / "cache" / "generated-audio"
        )
        asset_ids: list[str] = []
        cue_ids: list[str] = []
        desired_keys = {cue.plan_key for cue in plan.cues}
        existing_assets = {
            asset.cache_key: asset
            for asset in self.container.ambience.assets(project_id)
            if asset.cache_key
        }
        with self.container.structure.database.session() as session:
            scene_ids = select(SceneRecord.id).where(SceneRecord.chapter_id == plan.chapter_id)
            existing_cues = list(
                session.scalars(
                    select(AmbienceCueRecord).where(AmbienceCueRecord.scene_id.in_(scene_ids))
                )
            )
        by_key = {
            str(_json_object(cue.evidence_json).get("planKey")): cue
            for cue in existing_cues
            if cue.origin == "auto_generated"
        }
        locked_slots = {
            (cue.scene_id, cue.cue_type)
            for cue in existing_cues
            if cue.origin == "auto_generated" and cue.user_locked
        }
        for planned in plan.cues:
            existing = by_key.get(planned.plan_key)
            if existing and existing.user_locked:
                cue_ids.append(existing.id)
                continue
            if not existing and (planned.scene_id, planned.kind) in locked_slots:
                continue
            resolved = bank.resolve(
                list(planned.tags),
                asset_type=planned.kind,
                duration_ms=10_000 if planned.kind == "ambience" else 2_000,
            )
            asset = existing_assets.get(resolved.cache_key)
            if not asset:
                asset = self.container.ambience.create_asset(
                    project_id,
                    resolved.entry.name,
                    str(resolved.path),
                    LICENSE_NOTE,
                    "bank",
                    asset_type=resolved.entry.asset_type,
                    duration_ms=resolved.duration_ms,
                    model="procedural_sound_bank",
                    prompt=", ".join(planned.tags),
                    cache_key=resolved.cache_key,
                    qa_status="passed",
                )
                existing_assets[resolved.cache_key] = asset
            asset_ids.append(asset.id)
            evidence = json.dumps(
                {
                    "planKey": planned.plan_key,
                    "rule": planned.rule,
                    "runSceneIds": list(planned.run_scene_ids),
                    "eventType": planned.event_type,
                    "segmentId": planned.segment_id,
                    "sentenceEvidence": planned.sentence_evidence,
                    "profile": planned.profile_evidence,
                },
                sort_keys=True,
            )
            if existing:
                with self.container.structure.database.session() as session:
                    record = session.get(AmbienceCueRecord, existing.id)
                    if record and not record.user_locked:
                        _apply_cue(record, planned, asset, evidence, plan.render_mode)
                        session.commit()
                        cue_ids.append(record.id)
            else:
                record = self.container.ambience.create_cue(
                    planned.scene_id,
                    asset.id,
                    planned.kind,
                    planned.start_ms,
                    -24.0 if planned.kind == "ambience" else -20.0,
                    800 if planned.kind == "ambience" else 0,
                    800 if planned.kind == "ambience" else 0,
                    planned.kind == "ambience",
                    plan.render_mode,
                    False,
                    origin="auto_generated",
                    evidence_json=evidence,
                )
                cue_ids.append(record.id)
        obsolete = [
            cue.id
            for cue in existing_cues
            if cue.origin == "auto_generated"
            and not cue.user_locked
            and str(_json_object(cue.evidence_json).get("planKey")) not in desired_keys
        ]
        if obsolete:
            with self.container.structure.database.session() as session:
                session.execute(delete(AmbienceCueRecord).where(AmbienceCueRecord.id.in_(obsolete)))
                session.commit()
        return list(dict.fromkeys(asset_ids)), cue_ids

    @staticmethod
    def _write_manifest(
        artifact_root: Path,
        project_id: str,
        profiles: dict[str, dict[str, object]],
        plan: SoundPlan,
        asset_ids: list[str],
        cue_ids: list[str],
    ) -> Path:
        root = artifact_root / "manifests" / "chapters" / plan.chapter_id
        root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "manifestType": "sound_plan_manifest",
            "schemaVersion": "0.1.0",
            "projectId": project_id,
            "chapterId": plan.chapter_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "status": "completed",
            "payload": {
                "renderMode": plan.render_mode,
                "atmosphereProfiles": profiles,
                "plannedCues": [_cue_payload(cue) for cue in plan.cues],
                "budgets": {"sfxUsed": plan.sfx_used, "sfxLimit": plan.sfx_limit},
                "skipped": [asdict(item) for item in plan.skipped],
                "materializedAssetIds": asset_ids,
                "materializedCueIds": cue_ids,
            },
            "diagnostics": [],
        }
        body = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        version = root / f"sound_plan_manifest.{uuid4().hex[:12]}.json"
        version.write_text(body, encoding="utf-8")
        latest = root / "sound_plan_manifest.json"
        latest.write_text(body, encoding="utf-8")
        return latest


def _apply_cue(
    record: AmbienceCueRecord,
    planned: PlannedSoundCue,
    asset: AmbienceAssetRecord,
    evidence: str,
    render_mode: str,
) -> None:
    record.asset_id = asset.id
    record.cue_type = planned.kind
    record.start_ms = planned.start_ms
    record.gain_db = -24.0 if planned.kind == "ambience" else -20.0
    record.fade_in_ms = 800 if planned.kind == "ambience" else 0
    record.fade_out_ms = 800 if planned.kind == "ambience" else 0
    record.ducking = planned.kind == "ambience"
    record.render_mode = render_mode
    record.no_sfx = False
    record.origin = "auto_generated"
    record.evidence_json = evidence
    record.muted = False


def _locate_anchor(
    sentence: str, segments: tuple[SegmentPlanInput, ...]
) -> tuple[SegmentPlanInput, int] | None:
    query = _normalize_text(sentence)
    if not query:
        return None
    best: tuple[float, int, SegmentPlanInput, int] | None = None
    query_tokens = set(query.split())
    for index, segment in enumerate(segments):
        text = _normalize_text(segment.text)
        if segment.start_ms is None or segment.end_ms is None or not text:
            continue
        char_index = text.find(query)
        if char_index >= 0:
            score = 1.0
        else:
            tokens = set(text.split())
            score = len(query_tokens & tokens) / len(query_tokens | tokens) if tokens else 0.0
            char_index = 0
        candidate = (score, -index, segment, char_index)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None or best[0] < MIN_ANCHOR_JACCARD:
        return None
    _, _, segment, char_index = best
    assert segment.start_ms is not None and segment.end_ms is not None
    normalized = _normalize_text(segment.text)
    ratio = char_index / max(1, len(normalized))
    start_ms = segment.start_ms + round(ratio * (segment.end_ms - segment.start_ms))
    return segment, start_ms


def _bed_tags(profile: dict[str, object]) -> tuple[str, ...]:
    return tuple(
        _normalized(profile.get(key), fallback)
        for key, fallback in (
            ("locationCategory", "unspecified"),
            ("interiorExterior", "unspecified"),
            ("weather", "none"),
            ("timeOfDay", "unspecified"),
            ("mood", "neutral"),
        )
    )


def _profile_evidence(profile: dict[str, object]) -> dict[str, object]:
    keys = (
        "locationCategory",
        "interiorExterior",
        "weather",
        "timeOfDay",
        "mood",
        "tensionLevel",
        "confidence",
    )
    return {key: profile[key] for key in keys if key in profile}


def _plan_key(*parts: object) -> str:
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _cue_payload(cue: PlannedSoundCue) -> dict[str, object]:
    return {
        "sceneId": cue.scene_id,
        "kind": cue.kind,
        "rule": cue.rule,
        "tags": list(cue.tags),
        "planKey": cue.plan_key,
        "runSceneIds": list(cue.run_scene_ids),
        "eventType": cue.event_type,
        "segmentId": cue.segment_id,
        "startMs": cue.start_ms,
        "sentenceEvidence": cue.sentence_evidence,
        "profileEvidence": cue.profile_evidence,
    }


def _json_object(payload: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return {}
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _normalized(value: object, fallback: str) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    return normalized or fallback


def _normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", value.casefold()))


def _number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _bounded_budget(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, min(20, value))
    return default
