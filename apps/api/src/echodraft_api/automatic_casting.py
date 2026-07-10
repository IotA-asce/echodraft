from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from echodraft_db.models import (
    CastingDecisionRecord,
    ChapterRecord,
    CharacterRecord,
    SceneRecord,
    SegmentRecord,
    SpeakerAttributionRecord,
    VoiceProfileRecord,
)
from echodraft_domain import CastingDecision, VoiceCatalogEntry
from sqlalchemy import or_, select

from .container import AppContainer
from .voice_catalog import VoiceCatalogService

CASTING_ALGORITHM_VERSION = "1.0.0"
MIN_DIALOGUE_WORDS = 5
DISTINCT_THRESHOLD = 0.35

# Bounded greedy-with-backtracking solver for majors (design doc "Step 3").
# When a major's best available score falls below this threshold, the solver
# backtracks one prior major assignment to its second-best candidate and
# retries, bounded to MAX_BACKTRACK_DEPTH total backtracks so the whole pass
# stays roughly linear even on a large cast.
BACKTRACK_SCORE_THRESHOLD = 1.0
MAX_BACKTRACK_DEPTH = 3

# Relaxation ladder (design doc "Consistency rules" + this fix): a character
# must always end with a voice. On hard-constraint exhaustion, soft/hard
# constraints are relaxed in this fixed order, and every relaxation actually
# applied is recorded on the decision's evidence trail.
RELAXATION_DROP_TIMBRE = "droppedTimbrePreference"
RELAXATION_ALLOW_REUSE = "allowedNonNarratorVoiceReuse"
RELAXATION_DROP_GENDER = "droppedGenderRequirement"
RELAXATION_DROP_REMAINING = "droppedRemainingRequiredFacets"

# Small, deterministic pace offsets (+/-3-5%) applied by pool index so pooled
# minor characters sharing one catalog voice are not byte-identical in
# delivery (design doc "apply_pool_offset"). Index 0 is unperturbed -- the
# first minor to use a pooled voice sounds exactly like the catalog voice;
# only the second-and-later sharers are nudged.
POOL_PACE_OFFSETS: tuple[float, ...] = (0.0, 0.04, -0.04, 0.05, -0.05, 0.03, -0.03)


@dataclass(frozen=True)
class PointOfViewEvidence:
    classification: str
    first_person_pronoun_ratio: float
    narration_word_count: int


@dataclass(frozen=True)
class NarratorSelection:
    projectId: str
    voiceProfileId: str
    voiceCatalogEntryId: str
    pointOfView: str
    firstPersonPronounRatio: float
    stylePreset: str
    score: int
    evidence: dict[str, object]


@dataclass(frozen=True)
class CastingSpec:
    character_id: str
    required_facets: dict[str, str]
    preferred_facets: dict[str, str]
    timbre_preference: list[str]
    prominence_class: str
    dialogue_word_count: int
    dialogue_segment_count: int
    scene_co_occurrence: list[str]
    confidence: float
    evidence_refs: list[str]


@dataclass(frozen=True)
class _MajorAssignment:
    spec: CastingSpec
    voice: VoiceCatalogEntry
    score: float
    candidate_scores: list[dict[str, object]]
    relaxations: list[str]
    scored: list[tuple[VoiceCatalogEntry, float, list[dict[str, object]]]]


class AutomaticCastingService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def select_narrator(
        self, project_id: str, style_preset: str = "warm_neutral"
    ) -> dict[str, object]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        narration = self._narration(project_id)
        pov = detect_point_of_view(narration)
        # Incremental: cheap no-op once every installed voice is cataloged,
        # but always self-heals a catalog that is missing newly installed
        # engine voices (see voice_catalog.audition_backfill's incremental
        # skip-if-already-cataloged behavior).
        catalog = VoiceCatalogService(self.container).audition_backfill()
        eligible = [entry for entry in catalog if _catalog_entry_is_eligible(entry)]
        if not eligible:
            raise ValueError("No commercially usable voice catalog entry is available.")
        selected = sorted(
            eligible,
            key=lambda entry: (-_narrator_score(entry.facets, style_preset), entry.id),
        )[0]
        voice_profile_id = self._project_voice(
            project_id,
            selected.id,
            selected.engine,
            selected.engine_voice_id,
        )
        current = self.container.production.get(project_id)
        self.container.production.update(
            project_id,
            voice_profile_id,
            current.default_direction_json,
        )
        return asdict(
            NarratorSelection(
                projectId=project_id,
                voiceProfileId=voice_profile_id,
                voiceCatalogEntryId=selected.id,
                pointOfView=pov.classification,
                firstPersonPronounRatio=pov.first_person_pronoun_ratio,
                stylePreset=style_preset,
                score=_narrator_score(selected.facets, style_preset),
                evidence={
                    "narrationWordCount": pov.narration_word_count,
                    "catalogVersion": selected.catalog_version,
                    "facets": selected.facets,
                },
            )
        )

    def auto_cast(
        self,
        project_id: str,
        *,
        style_preset: str = "warm_neutral",
        scope: str = "all",
        job_id: str | None = None,
    ) -> list[CastingDecision]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        if scope not in {"all", "unlocked_only"}:
            raise ValueError("Casting scope must be 'all' or 'unlocked_only'.")
        settings = self.container.production.get(project_id)
        if not settings.auto_cast_enabled:
            raise ValueError("Automatic casting is disabled for this project.")
        self.container.production.configure_casting(project_id, style_preset=style_preset)
        # See select_narrator: incremental backfill is cheap once cataloged,
        # and self-heals a catalog missing newly installed engine voices.
        catalog = VoiceCatalogService(self.container).audition_backfill()
        eligible = [entry for entry in catalog if _catalog_entry_is_eligible(entry)]
        if not eligible:
            raise ValueError("No commercially usable voice catalog entry is available.")
        catalog_by_id = {entry.id: entry for entry in eligible}
        catalog_version = _catalog_snapshot_version(eligible)
        existing_narrator_decision = self._decision_record(
            settings.narrator_casting_decision_id
        )
        preserve_narrator = bool(
            settings.narrator_voice_profile_id
            and (
                not settings.narrator_casting_decision_id
                or (existing_narrator_decision and existing_narrator_decision.user_locked)
            )
        )
        if preserve_narrator:
            selection = self._existing_narrator_selection(
                project_id,
                cast(str, settings.narrator_voice_profile_id),
                style_preset,
                eligible,
            )
        else:
            selection = self.select_narrator(project_id, style_preset)
        narrator_catalog_id = cast(str, selection["voiceCatalogEntryId"])
        narrator_candidates = [
            {
                "voiceId": entry.id,
                "score": float(_narrator_score(entry.facets, style_preset)),
                "facetMatch": float(_narrator_score(entry.facets, style_preset)),
                "timbreMatch": 0.0,
                "repeatPenalty": 0.0,
                "distinctivenessPenalty": 0.0,
            }
            for entry in sorted(
                eligible,
                key=lambda item: (-_narrator_score(item.facets, style_preset), item.id),
            )[:3]
        ]
        narrator_decision = (
            _decision_model(existing_narrator_decision)
            if preserve_narrator and existing_narrator_decision
            else self._save_decision(
                project_id=project_id,
                character_id=None,
                role="narrator",
                voice_catalog_entry_id=narrator_catalog_id,
                prominence_class=None,
                score=_float_value(selection["score"]),
                candidate_scores=narrator_candidates,
                evidence={
                    **cast(dict[str, object], selection["evidence"]),
                    "pointOfView": selection["pointOfView"],
                    "firstPersonPronounRatio": selection["firstPersonPronounRatio"],
                    "stylePreset": style_preset,
                    "legacyAssignmentPreserved": preserve_narrator,
                },
                catalog_version=catalog_version,
                user_locked=preserve_narrator,
                locked_reason=(
                    "Legacy hand narrator preserved during automatic casting."
                    if preserve_narrator
                    else None
                ),
            )
        )
        self.container.production.configure_casting(
            project_id,
            narrator_casting_decision_id=narrator_decision.id,
            update_narrator_decision=True,
        )

        assignment_rows = self.container.casting.prepare_automatic_casting_assignments(
            project_id
        )
        locked_character_ids = {row.character_id for row in assignment_rows if row.user_locked}
        locked_catalog_ids = {
            profile.voice_catalog_entry_id
            for row in assignment_rows
            if row.user_locked
            and (profile := self.container.casting.voice(row.voice_profile_id))
            and profile.voice_catalog_entry_id
        }
        specs = [
            spec
            for spec in self.derive_casting_specs(project_id)
            if spec.character_id not in locked_character_ids
        ]
        assignable = [
            entry
            for entry in eligible
            if entry.id != narrator_catalog_id and entry.id not in locked_catalog_ids
        ]
        narrator_profile_id = cast(str, selection["voiceProfileId"])
        assigned: dict[str, VoiceCatalogEntry] = {}
        pool_usage: dict[str, int] = {}
        decisions = [narrator_decision]
        # Majors get a dedicated bounded backtracking pass (Fix 2): they are
        # first pick of the catalog while it is least depleted, and a purely
        # greedy pick order can lock in a locally-good but globally-poor
        # arrangement when scene co-occurrence makes assignment a joint, not
        # incremental, optimization. `_assign_majors` mutates `assigned` in
        # place so minors processed afterward see majors' final choices.
        major_specs = [spec for spec in specs if spec.prominence_class == "major"]
        major_assignments = (
            self._assign_majors(major_specs, assignable, assigned) if assignable else {}
        )
        for index, spec in enumerate(specs, 1):
            relaxations: list[str] = []
            pool_offset = 0.0
            if spec.prominence_class == "walk_on" or not assignable:
                chosen = catalog_by_id[narrator_catalog_id]
                candidate_scores = [
                    {
                        "voiceId": chosen.id,
                        "score": 0.0,
                        "facetMatch": 0.0,
                        "timbreMatch": 0.0,
                        "repeatPenalty": 0.0,
                        "distinctivenessPenalty": 0.0,
                        "fallback": "narrator_min_dialogue_floor",
                    }
                ]
                score = 0.0
                voice_profile_id = narrator_profile_id
                if spec.prominence_class != "walk_on":
                    # Every assignable catalog voice was already claimed
                    # (narrator reservation + locks); fall back to the
                    # narrator voice rather than ever leaving a character
                    # unvoiced (casting must never abort mid-run).
                    relaxations.append("catalogExhaustedFellBackToNarrator")
            elif spec.prominence_class == "major":
                result = major_assignments[spec.character_id]
                chosen = result.voice
                score = result.score
                candidate_scores = result.candidate_scores
                relaxations = result.relaxations
                voice_profile_id = self._project_voice(
                    project_id,
                    chosen.id,
                    chosen.engine,
                    chosen.engine_voice_id,
                )
            else:
                scored, relaxations = self._rank_candidates(spec, assignable, assigned)
                chosen, score, candidate_scores = scored[0]
                voice_profile_id = self._project_voice(
                    project_id,
                    chosen.id,
                    chosen.engine,
                    chosen.engine_voice_id,
                )
                if spec.prominence_class == "minor":
                    # Pooled minors sharing one catalog voice get a small,
                    # deterministic pace offset by pool index so they are not
                    # byte-identical in delivery (design doc
                    # `apply_pool_offset`). Applied at render time by
                    # production.py's direction resolution.
                    offset_index = pool_usage.get(chosen.id, 0)
                    pool_usage[chosen.id] = offset_index + 1
                    pool_offset = POOL_PACE_OFFSETS[offset_index % len(POOL_PACE_OFFSETS)]
            evidence: dict[str, object] = {
                "requiredFacets": spec.required_facets,
                "preferredFacets": spec.preferred_facets,
                "timbrePreference": spec.timbre_preference,
                "dialogueWordCount": spec.dialogue_word_count,
                "dialogueSegmentCount": spec.dialogue_segment_count,
                "sceneCoOccurrence": spec.scene_co_occurrence,
                "confidence": spec.confidence,
                "evidenceRefs": spec.evidence_refs,
                "scope": scope,
                "relaxations": relaxations,
            }
            if pool_offset:
                evidence["poolOffset"] = pool_offset
            decision = self._save_decision(
                project_id=project_id,
                character_id=spec.character_id,
                role="character",
                voice_catalog_entry_id=chosen.id,
                prominence_class=spec.prominence_class,
                score=score,
                candidate_scores=candidate_scores,
                evidence=evidence,
                catalog_version=catalog_version,
            )
            self.container.casting.assign(
                spec.character_id,
                voice_profile_id,
                user_locked=False,
                casting_decision_id=decision.id,
            )
            assigned[spec.character_id] = chosen
            decisions.append(decision)
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "automatic_casting",
                        "current": index,
                        "total": len(specs),
                        "characterId": spec.character_id,
                    },
                )
        self._write_manifest(
            project_id,
            decisions,
            locked_character_ids=sorted(locked_character_ids),
            catalog_version=catalog_version,
        )
        return decisions

    def override_character_voice(
        self,
        character_id: str,
        voice_profile_id: str,
        *,
        lock_assignment: bool,
        allow_narrator_reuse: bool,
    ) -> CastingDecision | None:
        character = self.container.casting.character(character_id)
        if not character:
            raise KeyError(character_id)
        voice = self.container.casting.voice(voice_profile_id)
        if not voice or voice.project_id != character.project_id:
            raise ValueError("Voice profile must belong to the same project.")
        settings = self.container.production.get(character.project_id)
        if (
            settings.narrator_voice_profile_id == voice_profile_id
            and not allow_narrator_reuse
        ):
            raise ValueError(
                "Narrator voice reuse is blocked unless allowNarratorReuse is true."
            )
        if not voice.voice_catalog_entry_id:
            self.container.casting.assign(
                character_id,
                voice_profile_id,
                user_locked=True,
                locked_reason="Manual custom-voice override preserved outside the catalog.",
            )
            return None
        entry = VoiceCatalogService(self.container).entry(voice.voice_catalog_entry_id)
        if not entry:
            raise ValueError("The selected voice catalog entry was not found.")
        decision = self._save_decision(
            project_id=character.project_id,
            character_id=character_id,
            role="character",
            voice_catalog_entry_id=entry.id,
            prominence_class=None,
            score=0.0,
            candidate_scores=[{"voiceId": entry.id, "score": 0.0, "source": "user_override"}],
            evidence={"source": "user_override", "voiceProfileId": voice_profile_id},
            catalog_version=_catalog_snapshot_version(
                VoiceCatalogService(self.container).entries()
            ),
            user_locked=lock_assignment,
            locked_reason="Manual voice override." if lock_assignment else None,
        )
        self.container.casting.assign(
            character_id,
            voice_profile_id,
            user_locked=lock_assignment,
            locked_reason=decision.locked_reason,
            casting_decision_id=decision.id,
        )
        return decision

    def derive_casting_specs(self, project_id: str) -> list[CastingSpec]:
        with self.container.structure.database.session() as session:
            characters = list(
                session.scalars(
                    select(CharacterRecord)
                    .where(
                        CharacterRecord.project_id == project_id,
                        CharacterRecord.merged_into_character_id.is_(None),
                    )
                    .order_by(CharacterRecord.id)
                )
            )
            rows = list(
                session.execute(
                    select(SpeakerAttributionRecord, SegmentRecord, SceneRecord.id)
                    .join(
                        SegmentRecord,
                        SpeakerAttributionRecord.segment_id == SegmentRecord.id,
                    )
                    .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                    .where(
                        SpeakerAttributionRecord.project_id == project_id,
                        SpeakerAttributionRecord.character_id.is_not(None),
                        or_(
                            SpeakerAttributionRecord.status == "approved",
                            SpeakerAttributionRecord.auto_accepted.is_(True),
                        ),
                    )
                )
            )
        words: dict[str, int] = {character.id: 0 for character in characters}
        segments: dict[str, int] = {character.id: 0 for character in characters}
        scene_characters: dict[str, set[str]] = {}
        for attribution, segment, scene_id in rows:
            character_id = attribution.character_id
            if not character_id or character_id not in words:
                continue
            words[character_id] += len(re.findall(r"[\w']+", segment.text_content))
            segments[character_id] += 1
            scene_characters.setdefault(scene_id, set()).add(character_id)
        partners: dict[str, set[str]] = {character.id: set() for character in characters}
        for members in scene_characters.values():
            for character_id in members:
                partners[character_id].update(members - {character_id})
        positive = sorted(
            (character_id for character_id, count in words.items() if count >= MIN_DIALOGUE_WORDS),
            key=lambda character_id: (-words[character_id], character_id),
        )
        major_count = max(1, math.ceil(len(positive) * 0.15)) if positive else 0
        major_ids = set(positive[:major_count]) | {
            character_id for character_id in positive if words[character_id] >= 1000
        }
        specs = [
            _casting_spec(
                character,
                dialogue_word_count=words[character.id],
                dialogue_segment_count=segments[character.id],
                partners=sorted(partners[character.id]),
                is_major=character.id in major_ids,
            )
            for character in characters
        ]
        return sorted(
            specs,
            key=lambda spec: (
                {"major": 0, "minor": 1, "walk_on": 2}[spec.prominence_class],
                -spec.dialogue_word_count,
                spec.character_id,
            ),
        )

    def decision(self, character_id: str) -> CastingDecision | None:
        with self.container.structure.database.session() as session:
            record = session.scalar(
                select(CastingDecisionRecord).where(
                    CastingDecisionRecord.character_id == character_id,
                    CastingDecisionRecord.role == "character",
                    CastingDecisionRecord.superseded_by_id.is_(None),
                )
            )
        return _decision_model(record) if record else None

    def _decision_record(self, decision_id: str | None) -> CastingDecisionRecord | None:
        if not decision_id:
            return None
        with self.container.structure.database.session() as session:
            return session.get(CastingDecisionRecord, decision_id)

    def _existing_narrator_selection(
        self,
        project_id: str,
        voice_profile_id: str,
        style_preset: str,
        catalog: list[VoiceCatalogEntry],
    ) -> dict[str, object]:
        voice = self.container.casting.voice(voice_profile_id)
        if not voice or voice.project_id != project_id:
            raise ValueError("The preserved narrator voice is not available in this project.")
        entry = next(
            (
                item
                for item in catalog
                if item.id == voice.voice_catalog_entry_id
                or (
                    item.engine == voice.backend
                    and item.engine_voice_id == voice.provider_voice_id
                )
            ),
            None,
        )
        if not entry:
            raise ValueError(
                "The preserved narrator has no commercially eligible catalog identity."
            )
        if voice.voice_catalog_entry_id != entry.id:
            with self.container.structure.database.session() as session:
                record = session.get(VoiceProfileRecord, voice.id)
                assert record is not None
                record.voice_catalog_entry_id = entry.id
                session.commit()
        pov = detect_point_of_view(self._narration(project_id))
        return asdict(
            NarratorSelection(
                projectId=project_id,
                voiceProfileId=voice.id,
                voiceCatalogEntryId=entry.id,
                pointOfView=pov.classification,
                firstPersonPronounRatio=pov.first_person_pronoun_ratio,
                stylePreset=style_preset,
                score=_narrator_score(entry.facets, style_preset),
                evidence={
                    "narrationWordCount": pov.narration_word_count,
                    "catalogVersion": entry.catalog_version,
                    "facets": entry.facets,
                },
            )
        )

    def _assign_majors(
        self,
        majors: list[CastingSpec],
        assignable: list[VoiceCatalogEntry],
        assigned: dict[str, VoiceCatalogEntry],
    ) -> dict[str, _MajorAssignment]:
        """Greedy-with-bounded-backtracking assignment for major characters.

        Majors are processed in the deterministic order the caller supplies
        (prominence/word-count/id, per `derive_casting_specs`). A purely
        greedy pass can lock in a locally-good but globally-poor arrangement,
        since scene co-occurrence penalties are inherently a joint, not
        incremental, optimization. When a major's best available score falls
        below `BACKTRACK_SCORE_THRESHOLD`, this backtracks the immediately
        preceding major's assignment to its second-best candidate and
        retries the current major -- bounded to `MAX_BACKTRACK_DEPTH` total
        backtracks so the pass stays roughly linear even on a large cast.
        Ordering/tie-breaks stay deterministic throughout: `_rank_candidates`
        always sorts by `(-score, voiceId)`. Mutates `assigned` in place so
        callers processing minors afterward see majors' final choices.
        """
        history: list[_MajorAssignment] = []
        backtracks_used = 0
        index = 0
        while index < len(majors):
            spec = majors[index]
            scored, relaxations = self._rank_candidates(spec, assignable, assigned)
            used_by_major = {item.voice.id for item in history}
            preferred = [item for item in scored if item[0].id not in used_by_major]
            effective = preferred if preferred else scored
            best_voice, best_score, best_candidates = effective[0]
            can_backtrack = (
                best_score < BACKTRACK_SCORE_THRESHOLD
                and bool(history)
                and backtracks_used < MAX_BACKTRACK_DEPTH
                and len(history[-1].scored) > 1
            )
            if can_backtrack:
                previous = history[-1]
                alt_voice, alt_score, alt_candidates = previous.scored[1]
                history[-1] = _MajorAssignment(
                    spec=previous.spec,
                    voice=alt_voice,
                    score=alt_score,
                    candidate_scores=alt_candidates,
                    relaxations=previous.relaxations,
                    scored=previous.scored,
                )
                assigned[previous.spec.character_id] = alt_voice
                backtracks_used += 1
                continue
            assigned[spec.character_id] = best_voice
            history.append(
                _MajorAssignment(
                    spec=spec,
                    voice=best_voice,
                    score=best_score,
                    candidate_scores=best_candidates,
                    relaxations=relaxations,
                    scored=scored,
                )
            )
            index += 1
        return {item.spec.character_id: item for item in history}

    def _rank_candidates(
        self,
        spec: CastingSpec,
        catalog: list[VoiceCatalogEntry],
        assigned: dict[str, VoiceCatalogEntry],
    ) -> tuple[list[tuple[VoiceCatalogEntry, float, list[dict[str, object]]]], list[str]]:
        """Score every candidate voice against a casting spec.

        Casting must never abort mid-run -- a character always ends with a
        voice. If the hard constraints (required facets) leave zero
        candidates, this relaxes constraints in a fixed, recorded order
        rather than raising: drop the timbre preference, then re-score while
        no longer penalizing a reused non-narrator voice, then drop the
        gender requirement (relaxed only as a last resort), and finally drop
        any other remaining required facet (e.g. age) so a non-empty catalog
        always yields at least one candidate. Every relaxation actually
        applied is returned for the decision's evidence trail.
        """
        relaxations: list[str] = []
        working_spec = spec
        scored = self._score_candidates(working_spec, catalog, assigned)

        if not scored and working_spec.timbre_preference:
            working_spec = replace(working_spec, timbre_preference=[])
            relaxations.append(RELAXATION_DROP_TIMBRE)
            scored = self._score_candidates(working_spec, catalog, assigned)

        if not scored:
            relaxations.append(RELAXATION_ALLOW_REUSE)
            scored = self._score_candidates(
                working_spec, catalog, assigned, ignore_repeat_penalty=True
            )

        if not scored and "gender" in working_spec.required_facets:
            working_spec = replace(
                working_spec,
                required_facets={
                    key: value
                    for key, value in working_spec.required_facets.items()
                    if key != "gender"
                },
            )
            relaxations.append(RELAXATION_DROP_GENDER)
            scored = self._score_candidates(
                working_spec, catalog, assigned, ignore_repeat_penalty=True
            )

        if not scored and working_spec.required_facets:
            relaxations.append(RELAXATION_DROP_REMAINING)
            working_spec = replace(working_spec, required_facets={})
            scored = self._score_candidates(
                working_spec, catalog, assigned, ignore_repeat_penalty=True
            )

        if not scored:
            # Every caller guarantees `catalog` is non-empty before reaching
            # this method (an exhausted/empty catalog falls back to the
            # narrator voice earlier); this is a defensive invariant check,
            # not a normal casting outcome.
            raise ValueError(f"Voice catalog is empty; cannot cast {spec.character_id}.")

        scored.sort(key=lambda item: (-item[1], item[0].id))
        top = [item[2] for item in scored[:3]]
        return [(voice, score, top) for voice, score, _components in scored], relaxations

    def _score_candidates(
        self,
        spec: CastingSpec,
        catalog: list[VoiceCatalogEntry],
        assigned: dict[str, VoiceCatalogEntry],
        *,
        ignore_repeat_penalty: bool = False,
    ) -> list[tuple[VoiceCatalogEntry, float, dict[str, object]]]:
        scored: list[tuple[VoiceCatalogEntry, float, dict[str, object]]] = []
        for voice in catalog:
            components = _score_voice(
                voice, spec, assigned, ignore_repeat_penalty=ignore_repeat_penalty
            )
            if components is not None:
                scored.append((voice, cast(float, components["score"]), components))
        return scored

    def _save_decision(
        self,
        *,
        project_id: str,
        character_id: str | None,
        role: str,
        voice_catalog_entry_id: str,
        prominence_class: str | None,
        score: float,
        candidate_scores: list[dict[str, object]],
        evidence: dict[str, object],
        catalog_version: str,
        user_locked: bool = False,
        locked_reason: str | None = None,
    ) -> CastingDecision:
        new_id = f"castdecision_{uuid4().hex[:16]}"
        with self.container.structure.database.session() as session:
            filters = [
                CastingDecisionRecord.project_id == project_id,
                CastingDecisionRecord.role == role,
                CastingDecisionRecord.superseded_by_id.is_(None),
            ]
            filters.append(
                CastingDecisionRecord.character_id == character_id
                if character_id is not None
                else CastingDecisionRecord.character_id.is_(None)
            )
            previous = session.scalar(select(CastingDecisionRecord).where(*filters))
            record = CastingDecisionRecord(
                id=new_id,
                project_id=project_id,
                character_id=character_id,
                role=role,
                voice_catalog_entry_id=voice_catalog_entry_id,
                prominence_class=prominence_class,
                score=score,
                candidate_scores_json=json.dumps(candidate_scores, sort_keys=True),
                evidence_json=json.dumps(evidence, sort_keys=True),
                algorithm_version=CASTING_ALGORITHM_VERSION,
                catalog_version=catalog_version,
                user_locked=user_locked,
                locked_reason=locked_reason,
                superseded_by_id=new_id if previous else None,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            session.flush()
            if previous:
                previous.superseded_by_id = new_id
                session.flush()
                record.superseded_by_id = None
            session.commit()
            return _decision_model(record)

    def _narration(self, project_id: str) -> str:
        with self.container.structure.database.session() as session:
            rows = session.scalars(
                select(SegmentRecord)
                .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                .where(
                    ChapterRecord.project_id == project_id,
                    SegmentRecord.segment_type != "dialogue",
                )
                .order_by(
                    ChapterRecord.order_index,
                    SceneRecord.order_index,
                    SegmentRecord.order_index,
                )
            )
            return " ".join(row.text_content for row in rows)

    def _project_voice(
        self, project_id: str, catalog_id: str, engine: str, provider_voice_id: str
    ) -> str:
        with self.container.structure.database.session() as session:
            existing = session.scalar(
                select(VoiceProfileRecord).where(
                    VoiceProfileRecord.project_id == project_id,
                    VoiceProfileRecord.voice_catalog_entry_id == catalog_id,
                )
            )
        if existing:
            return existing.id
        created = self.container.casting.create_voice(
            project_id,
            f"Auto cast ({provider_voice_id})",
            engine,
            provider_voice_id,
            None,
        )
        with self.container.structure.database.session() as session:
            record = session.get(VoiceProfileRecord, created.id)
            assert record is not None
            record.voice_catalog_entry_id = catalog_id
            session.commit()
            return record.id

    def _write_manifest(
        self,
        project_id: str,
        decisions: list[CastingDecision],
        *,
        locked_character_ids: list[str],
        catalog_version: str,
    ) -> None:
        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")
        root = self.container.settings.artifact_root / project_id / "manifests"
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "manifestType": "casting_manifest",
            "schemaVersion": "0.2.0",
            "projectId": project_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "algorithmVersion": CASTING_ALGORITHM_VERSION,
            "catalogVersion": catalog_version,
            "lockedCharacterIds": locked_character_ids,
            "decisions": [decision.model_dump(by_alias=True, mode="json") for decision in decisions],
        }
        versioned = root / f"casting_manifest.{uuid4().hex[:12]}.json"
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        versioned.write_text(serialized, encoding="utf-8")
        (root / "casting_manifest.json").write_text(serialized, encoding="utf-8")


def detect_point_of_view(narration: str) -> PointOfViewEvidence:
    words = re.findall(r"[a-z']+", narration.casefold())
    first_person = sum(
        word in {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours"}
        for word in words
    )
    ratio = first_person / max(1, len(words))
    return PointOfViewEvidence(
        classification="first_person" if ratio >= 0.015 else "third_person",
        first_person_pronoun_ratio=round(ratio, 6),
        narration_word_count=len(words),
    )


def _casting_spec(
    character: CharacterRecord,
    *,
    dialogue_word_count: int,
    dialogue_segment_count: int,
    partners: list[str],
    is_major: bool,
) -> CastingSpec:
    traits = _trait_map(character.traits_json)
    required = {key: value for key, value in traits.items() if key in {"gender", "age"}}
    preferred = {key: value for key, value in traits.items() if key not in required}
    styles = [str(item).casefold() for item in _json_list(character.speaking_style_json)]
    timbre = set(_role_timbre(character.role_type))
    for style in styles:
        for keyword, values in {
            "warm": {"warm", "soft"},
            "soft": {"soft"},
            "bright": {"bright", "clear"},
            "authoritative": {"clear"},
            "gentle": {"warm", "soft"},
            "raspy": {"raspy"},
        }.items():
            if keyword in style:
                timbre.update(values)
    prominence = (
        "walk_on"
        if dialogue_word_count < MIN_DIALOGUE_WORDS
        else "major" if is_major else "minor"
    )
    return CastingSpec(
        character_id=character.id,
        required_facets=required,
        preferred_facets=preferred,
        timbre_preference=sorted(timbre),
        prominence_class=prominence,
        dialogue_word_count=dialogue_word_count,
        dialogue_segment_count=dialogue_segment_count,
        scene_co_occurrence=partners,
        confidence=character.confidence,
        evidence_refs=[f"trait:{key}:{value}" for key, value in sorted(traits.items())],
    )


def _trait_map(payload: str) -> dict[str, str]:
    traits: dict[str, str] = {}
    for item in _json_list(payload):
        key, separator, value = str(item).casefold().partition(":")
        if separator and key and value:
            traits[key.strip()] = value.strip()
    return traits


def _score_voice(
    voice: VoiceCatalogEntry,
    spec: CastingSpec,
    assigned: dict[str, VoiceCatalogEntry],
    *,
    ignore_repeat_penalty: bool = False,
) -> dict[str, object] | None:
    matched_required: list[str] = []
    for key, expected in spec.required_facets.items():
        actual = _voice_facet(voice, key)
        if actual not in {"unknown", _normalize_facet(expected)}:
            return None
        if actual == _normalize_facet(expected):
            matched_required.append(f"{key}:{expected}")
    preferred_matches = [
        f"{key}:{expected}"
        for key, expected in spec.preferred_facets.items()
        if _voice_facet(voice, key) == _normalize_facet(expected)
    ]
    facet_match = float(len(matched_required) * 2 + len(preferred_matches))
    voice_timbre = {item.casefold() for item in voice.timbre}
    target_timbre = {item.casefold() for item in spec.timbre_preference}
    timbre_match = (
        len(voice_timbre & target_timbre) / len(voice_timbre | target_timbre)
        if voice_timbre and target_timbre
        else 0.5
    )
    reused = sum(assigned_voice.id == voice.id for assigned_voice in assigned.values())
    repeat_penalty = (
        0.0
        if ignore_repeat_penalty
        else reused * (4.0 if spec.prominence_class == "major" else 0.5)
    )
    distinctiveness_penalty = 0.0
    conflicts: list[str] = []
    for partner_id in spec.scene_co_occurrence:
        partner_voice = assigned.get(partner_id)
        if not partner_voice:
            continue
        distance = _voice_distance(voice, partner_voice)
        if distance < DISTINCT_THRESHOLD:
            distinctiveness_penalty += (DISTINCT_THRESHOLD - distance) * 4
            conflicts.append(partner_id)
    score = facet_match * 2 + timbre_match * 1.5 - repeat_penalty - distinctiveness_penalty
    return {
        "voiceId": voice.id,
        "score": round(score, 6),
        "facetMatch": facet_match,
        "timbreMatch": round(timbre_match, 6),
        "repeatPenalty": round(repeat_penalty, 6),
        "distinctivenessPenalty": round(distinctiveness_penalty, 6),
        "matchedRequiredFacets": matched_required,
        "matchedPreferredFacets": preferred_matches,
        "coOccurrenceConflicts": conflicts,
    }


def _voice_distance(left: VoiceCatalogEntry, right: VoiceCatalogEntry) -> float:
    if left.id == right.id:
        return 0.0
    left_pitch = _float_value(left.acoustics.get("pitchMedianHz"))
    right_pitch = _float_value(right.acoustics.get("pitchMedianHz"))
    pitch_delta = min(1.0, abs(left_pitch - right_pitch) / max(100.0, left_pitch, right_pitch))
    left_brightness = _float_value(left.acoustics.get("spectralBrightness"))
    right_brightness = _float_value(right.acoustics.get("spectralBrightness"))
    brightness_delta = min(1.0, abs(left_brightness - right_brightness))
    timbre_left = {item.casefold() for item in left.timbre}
    timbre_right = {item.casefold() for item in right.timbre}
    timbre_distance = (
        1 - len(timbre_left & timbre_right) / len(timbre_left | timbre_right)
        if timbre_left or timbre_right
        else 0.0
    )
    return round((pitch_delta + brightness_delta + timbre_distance) / 3, 6)


def _voice_facet(voice: VoiceCatalogEntry, key: str) -> str:
    value = {
        "gender": voice.gender,
        "age": voice.age_range,
        "accent": voice.accent,
        "locale": voice.locale,
        "energy": voice.energy_default,
    }.get(key, "unknown")
    return _normalize_facet(value)


def _normalize_facet(value: str) -> str:
    return {
        "female": "feminine",
        "woman": "feminine",
        "male": "masculine",
        "man": "masculine",
        "young": "young_adult",
        "adult": "adult",
        "elderly": "elder",
    }.get(value.casefold(), value.casefold())


def _role_timbre(role_type: str) -> set[str]:
    return {
        "major": {"clear"},
        "protagonist": {"clear", "warm"},
        "antagonist": {"clear"},
        "supporting": {"neutral"},
    }.get(role_type.casefold(), set())


def _catalog_entry_is_eligible(entry: VoiceCatalogEntry) -> bool:
    if entry.license.get("commercialUse") is not True:
        return False
    if entry.synthesis_kind == "cloned" and not entry.license.get("consentRecordId"):
        return False
    return True


def _catalog_snapshot_version(catalog: list[VoiceCatalogEntry]) -> str:
    payload = "\n".join(
        f"{entry.id}:{entry.catalog_version}" for entry in sorted(catalog, key=lambda item: item.id)
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _decision_model(record: CastingDecisionRecord) -> CastingDecision:
    return CastingDecision.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "characterId": record.character_id,
            "role": record.role,
            "chosenVoiceId": record.voice_catalog_entry_id,
            "prominenceClass": record.prominence_class,
            "score": record.score,
            "candidateScores": _json_list(record.candidate_scores_json),
            "evidence": _json_object(record.evidence_json),
            "algorithmVersion": record.algorithm_version,
            "catalogVersion": record.catalog_version,
            "userLocked": record.user_locked,
            "lockedReason": record.locked_reason,
            "supersededById": record.superseded_by_id,
            "createdAt": record.created_at,
        }
    )


def _json_list(payload: str) -> list[object]:
    try:
        value = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _json_object(payload: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _float_value(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _narrator_score(facets: list[str], preset: str) -> int:
    targets = {
        "warm_neutral": {"timbre:warm", "timbre:clear", "energy:medium"},
        "brisk": {"timbre:bright", "energy:medium"},
        "literary": {"timbre:warm", "timbre:soft"},
        "theatrical": {"timbre:bright"},
        "protagonist_pov": {"timbre:clear", "energy:medium"},
    }.get(preset, {"timbre:warm", "energy:medium"})
    return len(targets & set(facets))
