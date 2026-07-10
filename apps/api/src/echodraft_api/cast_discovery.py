from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from echodraft_db.models import ChapterRecord, CharacterRecord, SceneRecord, SegmentRecord
from echodraft_domain import EmbeddingRequest, LlmExtractionRequest, LlmExtractionResult
from sqlalchemy import select

from .cast_v2 import CAST_V2_VERSION, ClusterMention, ClusterResult, cluster_mentions
from .container import AppContainer
from .local_llm import CheckpointContext, LocalLlmService
from .structure import DEFAULT_REFINEMENT_MODEL, DEFAULT_REFINEMENT_MODEL_KEY

CAST_WINDOW_MAX_CHARS = 6000
CAST_WINDOW_OVERLAP_SEGMENTS = 1
AUTO_CREATE_CONFIDENCE = 0.72
SAFE_SHORTLIST_SCORE = 100
CAST_EMBEDDING_MODEL = "qwen3-embedding"
CAST_EMBEDDING_MODEL_KEY = "qwen3_embedding_ollama"
CAST_MENTION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "surfaceName": {"type": "string"},
                    "canonicalGuess": {"type": "string"},
                    "entityType": {"type": "string"},
                    "roleInScene": {"type": "string"},
                    "evidenceText": {"type": "string"},
                    "segmentIds": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "traitsObserved": {"type": "array", "items": {"type": "string"}},
                    "relationshipsObserved": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target": {"type": "string"},
                                "relation": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                            "required": ["target", "relation", "confidence"],
                        },
                    },
                    "speakingStyleObserved": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "surfaceName",
                    "evidenceText",
                    "segmentIds",
                    "confidence",
                ],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["mentions", "warnings"],
}
CAST_MERGE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "displayName": {"type": "string"},
                    "action": {"type": "string"},
                    "targetCharacterId": {"type": "string"},
                    "targetName": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                    "evidenceSegmentIds": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["displayName", "action", "confidence", "reason"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decisions", "warnings"],
}
CAST_PROFILE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "profile": {
            "type": "object",
            "properties": {
                "displayName": {"type": "string"},
                "role": {"type": "string"},
                "gender": {"type": "string"},
                "ageBand": {"type": "string"},
                "traits": {"type": "array", "items": {"type": "string"}},
                "speechStyle": {
                    "type": "object",
                    "properties": {
                        "register": {"type": "string"},
                        "verbosity": {"type": "string"},
                        "accentHint": {"type": "string"},
                        "tics": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["register", "verbosity", "accentHint", "tics"],
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string"},
                            "relation": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["target", "relation", "confidence"],
                    },
                },
                "confidence": {"type": "number"},
            },
            "required": [
                "displayName",
                "role",
                "gender",
                "ageBand",
                "traits",
                "speechStyle",
                "relationships",
                "confidence",
            ],
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["profile", "warnings"],
}
IGNORED_CHARACTER_NAMES = {
    "he",
    "she",
    "they",
    "we",
    "you",
    "i",
    "it",
    "narrator",
    "chapter",
    "scene",
    "someone",
    "everyone",
    "no one",
    "this",
    "that",
    "there",
    "what",
    "when",
    "where",
    "why",
    "how",
}
NON_CHARACTER_ENTITY_TYPES = {
    "place",
    "location",
    "organization",
    "org",
    "publisher",
    "author",
    "book",
    "title",
    "object",
}
GENERIC_ROLE_NAMES = {
    "the man",
    "the woman",
    "the boy",
    "the girl",
    "the child",
    "the captain",
    "the doctor",
    "the professor",
    "the driver",
    "the guard",
}
NON_CHARACTER_PHRASES = {
    "library of congress",
    "cataloging in publication data",
    "all rights reserved",
    "andy weir",
    "project hail mary",
    "copyright",
    "first edition",
}


@dataclass(frozen=True)
class ObservedSegment:
    id: str
    scene_id: str
    chapter_id: str
    chapter_status: str
    chapter_title: str | None
    chapter_order: int
    scene_order: int
    text: str
    segment_type: str
    start_offset: int
    end_offset: int
    speaker_candidate: str | None
    speaker_confidence: float
    parser_evidence: dict[str, object]


@dataclass(frozen=True)
class CastWindow:
    id: str
    scene_id: str
    chapter_id: str
    chapter_status: str
    segment_ids: list[str]
    atom_ids: list[str]
    text: str


@dataclass
class CharacterMention:
    id: str
    source_document_id: str | None
    scene_id: str | None
    window_id: str
    surface_name: str
    canonical_guess: str | None
    normalized_key: str
    entity_type: str
    role_in_scene: str
    evidence_text: str
    segment_ids: list[str]
    atom_ids: list[str]
    confidence: float
    traits_observed: list[str] = field(default_factory=list)
    relationships_observed: list[dict[str, object]] = field(default_factory=list)
    speaking_style_observed: list[str] = field(default_factory=list)
    llm_run_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class CharacterCandidate:
    display_name: str
    canonical_name: str | None
    aliases: list[str]
    first_seen_segment_id: str | None
    first_seen_chapter_id: str | None
    evidence: list[str]
    role_guess: str
    confidence: float
    source: str
    mention_evidence: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    relationships: list[dict[str, object]] = field(default_factory=list)
    speaking_style: list[str] = field(default_factory=list)
    generated_aliases: list[str] = field(default_factory=list)
    window_ids: list[str] = field(default_factory=list)
    scene_ids: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return _name_key(self.canonical_name or self.display_name)


@dataclass(frozen=True)
class MergeDecision:
    id: str
    action: str
    target_character_id: str | None
    target_name: str | None
    aliases: list[str]
    confidence: float
    reason: str
    evidence_segment_ids: list[str]
    llm_run_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class NameIndexEntry:
    character: CharacterRecord
    source: str


@dataclass(frozen=True)
class CharacterMatch:
    character: CharacterRecord
    reason: str
    score: int


@dataclass
class CharacterIndex:
    characters: list[CharacterRecord]
    by_name: dict[str, list[NameIndexEntry]] = field(default_factory=dict)

    def add_character(self, character: CharacterRecord) -> None:
        self.characters = [
            existing for existing in self.characters if existing.id != character.id
        ] + [character]
        for name, source in _character_index_names(character):
            key = _name_key(name)
            if not key:
                continue
            entries = self.by_name.setdefault(key, [])
            if not any(entry.character.id == character.id for entry in entries):
                entries.append(NameIndexEntry(character=character, source=source))

    def exact(self, candidate: CharacterCandidate) -> list[CharacterMatch]:
        matches: dict[str, CharacterMatch] = {}
        for name, source in _candidate_index_names(candidate):
            key = _name_key(name)
            if not key:
                continue
            for entry in self.by_name.get(key, []):
                reason = (
                    "generated_alias_exact"
                    if source == "generated_alias"
                    else f"{entry.source}_exact"
                )
                score = 120 if source != "generated_alias" else 55
                existing = matches.get(entry.character.id)
                if not existing or score > existing.score:
                    matches[entry.character.id] = CharacterMatch(
                        character=entry.character,
                        reason=reason,
                        score=score,
                    )
        return list(matches.values())

    def first_by_name(self, name: str | None) -> CharacterRecord | None:
        key = _name_key(name)
        if not key:
            return None
        entries = self.by_name.get(key, [])
        return entries[0].character if len(entries) == 1 else None

    def shortlist(self, candidate: CharacterCandidate, limit: int = 5) -> list[CharacterMatch]:
        matches: dict[str, CharacterMatch] = {}
        for character in self.characters:
            if character.merged_into_character_id:
                continue
            score, reason = _candidate_match_score(candidate, character)
            if score <= 0:
                continue
            matches[character.id] = CharacterMatch(character=character, reason=reason, score=score)
        return sorted(
            matches.values(),
            key=lambda item: (-item.score, item.character.display_name.casefold()),
        )[:limit]


class CastDiscoveryService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def propose_from_speaker_attribution(
        self,
        project_id: str,
        *,
        speaker_name: str,
        segment_id: str | None,
        chapter_id: str | None,
        text: str,
        confidence: float,
    ) -> CharacterRecord | None:
        if not _can_propose_cast(speaker_name):
            return None
        mention = CharacterMention(
            id=f"mention_{uuid4().hex[:16]}",
            source_document_id=self._latest_source_id(project_id),
            scene_id=None,
            window_id=f"speaker_{segment_id or 'project'}",
            surface_name=speaker_name,
            canonical_guess=speaker_name,
            normalized_key=_name_key(speaker_name),
            entity_type="person",
            role_in_scene="speaker",
            evidence_text=text[:220],
            segment_ids=[segment_id] if segment_id else [],
            atom_ids=[],
            confidence=confidence,
            traits_observed=_extract_traits(speaker_name, [text]),
            metadata={
                "source": "speaker_attribution",
                "chapterId": chapter_id,
                "filteredOut": False,
            },
        )
        candidate = self._candidate_from_mentions([mention], chapter_id)
        if not candidate:
            return None
        index = self._character_index(project_id)
        decision = self._decision_for_candidate(
            project_id, candidate, index, use_local_llm=self._local_llm_ready()
        )
        self.container.cast_graph.record_mention(project_id, self._mention_payload(mention))
        self.container.cast_graph.record_decision(project_id, self._decision_payload(decision))
        self._apply_candidate(project_id, None, candidate, decision, index)
        return _unique_active_character(
            self.container.casting.characters(project_id), speaker_name
        ) or _unique_active_character(
            self.container.casting.characters(project_id), candidate.canonical_name
        )

    def discover(
        self,
        project_id: str,
        *,
        source_id: str | None = None,
        use_local_llm: bool = True,
        job_id: str | None = None,
    ) -> list[CharacterRecord]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        source_id = source_id or self._latest_source_id(project_id)
        segments = self._segments(project_id)
        windows = _cast_windows(segments)
        ready = use_local_llm and self._local_llm_ready()

        mentions = self._deterministic_mentions(source_id, segments)
        if ready:
            mentions.extend(self._llm_mentions(project_id, source_id, windows, segments, job_id))

        persisted_mentions, accepted_mentions, diagnostics = self._filter_mentions(mentions, segments)
        self.container.cast_graph.replace_mentions(
            project_id,
            [self._mention_payload(mention) for mention in persisted_mentions],
        )

        cast_v2_enabled = self.container.settings.cast_v2_enabled
        cluster_result: ClusterResult | None = None
        if cast_v2_enabled:
            candidates, cluster_result = self._v2_candidates(
                project_id, accepted_mentions, segments
            )
            diagnostics.extend(cluster_result.diagnostics)
        else:
            candidates = self._candidates_from_mentions(accepted_mentions, segments)
        index = self._character_index(project_id)
        decisions: list[MergeDecision] = []
        profiles: list[dict[str, object]] = []
        for candidate_index, candidate in enumerate(candidates):
            decision = (
                self._decision_for_cluster(
                    project_id,
                    candidate,
                    index,
                    use_local_llm=ready,
                    job_id=job_id,
                )
                if cast_v2_enabled
                else self._decision_for_candidate(
                    project_id,
                    candidate,
                    index,
                    use_local_llm=ready,
                    job_id=job_id,
                )
            )
            profile: dict[str, object] | None = None
            if cast_v2_enabled and decision.action in {"merge", "new"}:
                candidate, profile = self._profile_candidate(
                    project_id,
                    candidate,
                    use_local_llm=ready,
                    job_id=job_id,
                )
            decisions.append(decision)
            self._apply_candidate(project_id, source_id, candidate, decision, index)
            if profile is not None:
                character = self._resolved_character(candidate, decision, index)
                profile["characterId"] = character.id if character else None
                if cluster_result and candidate_index < len(cluster_result.clusters):
                    profile["clusterId"] = cluster_result.clusters[candidate_index].id
                profiles.append(profile)
        self.container.cast_graph.replace_decisions(
            project_id,
            [self._decision_payload(decision) for decision in decisions],
        )
        self._write_manifest(
            project_id,
            source_id,
            windows,
            persisted_mentions,
            candidates,
            decisions,
            diagnostics,
            cluster_result=cluster_result,
            profiles=profiles,
        )
        return self.container.casting.characters(project_id)

    def _deterministic_mentions(
        self, source_id: str | None, segments: list[ObservedSegment]
    ) -> list[CharacterMention]:
        mentions: list[CharacterMention] = []
        for segment in segments:
            atom_ids = _string_list(segment.parser_evidence.get("atomIds"))
            if segment.speaker_candidate and not _ignored_name(segment.speaker_candidate):
                mentions.append(
                    CharacterMention(
                        id=f"mention_{uuid4().hex[:16]}",
                        source_document_id=source_id,
                        scene_id=segment.scene_id,
                        window_id=f"det_{segment.scene_id}",
                        surface_name=segment.speaker_candidate,
                        canonical_guess=segment.speaker_candidate,
                        normalized_key=_name_key(segment.speaker_candidate),
                        entity_type="person",
                        role_in_scene="speaker",
                        evidence_text=segment.text[:220],
                        segment_ids=[segment.id],
                        atom_ids=atom_ids,
                        confidence=segment.speaker_confidence,
                        traits_observed=_extract_traits(segment.speaker_candidate, [segment.text]),
                        metadata={
                            "source": "deterministic_speaker_candidate",
                            "chapterId": segment.chapter_id,
                            "chapterStatus": segment.chapter_status,
                            "speakerRule": segment.parser_evidence.get("speakerRule"),
                        },
                    )
                )
            mentions.extend(self._deterministic_text_mentions(source_id, segment))
        return mentions

    def _deterministic_text_mentions(
        self, source_id: str | None, segment: ObservedSegment
    ) -> list[CharacterMention]:
        names: list[str] = []
        for match in TITLE_NAME_RE.finditer(segment.text):
            names.append(match.group(0))
        for match in LEADING_NAME_RE.finditer(segment.text):
            names.append(match.group(1))
        seen: set[str] = set()
        mentions: list[CharacterMention] = []
        for name in names:
            key = _name_key(name)
            if (
                not key
                or key in seen
                or _ignored_name(name)
                or segment.speaker_candidate and _name_key(segment.speaker_candidate) == key
            ):
                continue
            seen.add(key)
            mentions.append(
                CharacterMention(
                    id=f"mention_{uuid4().hex[:16]}",
                    source_document_id=source_id,
                    scene_id=segment.scene_id,
                    window_id=f"det_{segment.scene_id}",
                    surface_name=name.strip(),
                    canonical_guess=name.strip(),
                    normalized_key=key,
                    entity_type="unknown",
                    role_in_scene="mentioned",
                    evidence_text=segment.text[:220],
                    segment_ids=[segment.id],
                    atom_ids=_string_list(segment.parser_evidence.get("atomIds")),
                    confidence=min(0.7, max(0.45, segment.speaker_confidence or 0.45)),
                    traits_observed=_extract_traits(name, [segment.text]),
                    metadata={
                        "source": "deterministic_text_mention",
                        "chapterId": segment.chapter_id,
                        "chapterStatus": segment.chapter_status,
                    },
                )
            )
        return mentions

    def _llm_mentions(
        self,
        project_id: str,
        source_id: str | None,
        windows: list[CastWindow],
        segments: list[ObservedSegment],
        job_id: str | None,
    ) -> list[CharacterMention]:
        llm = LocalLlmService(self.container)
        segment_map = {segment.id: segment for segment in segments}
        mentions: list[CharacterMention] = []
        max_workers = min(len(windows), self.container.orchestrator_pools.llm.max_workers)

        def extract_window(
            index: int,
            window: CastWindow,
        ) -> tuple[int, CastWindow, LlmExtractionRequest, LlmExtractionResult | ValueError]:
            request = LlmExtractionRequest(
                model=DEFAULT_REFINEMENT_MODEL,
                task="cast_discovery",
                schema=CAST_MENTION_SCHEMA,
                prompt=self._cast_prompt(window, segment_map),
            )
            checkpoint = (
                CheckpointContext(
                    job_id=job_id,
                    project_id=project_id,
                    stage="cast.discovery.mentions",
                    scope={"windowId": window.id, "segmentIds": sorted(window.segment_ids)},
                )
                if job_id
                else None
            )
            try:
                return (
                    index,
                    window,
                    request,
                    llm.extract(project_id, request, job_id, checkpoint=checkpoint),
                )
            except ValueError as error:
                return index, window, request, error

        results: list[tuple[int, CastWindow, LlmExtractionRequest, LlmExtractionResult | ValueError]] = []
        with ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="echodraft-cast-llm",
        ) as executor:
            futures = [
                executor.submit(extract_window, index, window)
                for index, window in enumerate(windows, 1)
            ]
            for future in futures:
                results.append(future.result())

        for index, window, _request, outcome in sorted(results, key=lambda item: item[0]):
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "llm_cast_discovery",
                        "current": index,
                        "total": len(windows),
                        "message": "Extracting character mentions from scene windows.",
                    },
                )
            if isinstance(outcome, ValueError):
                self.container.review.create_issue(
                    project_id=project_id,
                    category="cast_discovery",
                    severity="warning",
                    title="LLM cast discovery skipped a structure window",
                    description="Local Ollama failed while extracting cast mentions; deterministic evidence was kept.",
                    metadata={"error": str(outcome)[:500], "segmentIds": window.segment_ids},
                    dedupe_key=f"cast-discovery-llm:{project_id}:{window.id}",
                )
                continue
            result = outcome
            raw_mentions = result.result.get("mentions")
            if not isinstance(raw_mentions, list):
                continue
            for item in raw_mentions:
                if not isinstance(item, dict):
                    continue
                mention = self._mention_from_llm(
                    source_id,
                    window,
                    segment_map,
                    cast(dict[str, object], item),
                    result.run.id,
                )
                if mention:
                    mentions.append(mention)
        return mentions

    def _mention_from_llm(
        self,
        source_id: str | None,
        window: CastWindow,
        segment_map: dict[str, ObservedSegment],
        payload: dict[str, object],
        llm_run_id: str,
    ) -> CharacterMention | None:
        surface_name = str(payload.get("surfaceName") or "").strip()
        segment_ids = [
            item for item in _clean_strings(payload.get("segmentIds")) if item in segment_map
        ]
        if not surface_name or not segment_ids:
            return None
        key = _name_key(surface_name)
        if not key:
            return None
        related_segments = [segment_map[item] for item in segment_ids]
        atom_ids = sorted(
            {
                atom_id
                for segment in related_segments
                for atom_id in _string_list(segment.parser_evidence.get("atomIds"))
            }
        )
        chapter_ids = {segment.chapter_id for segment in related_segments}
        chapter_statuses = {segment.chapter_status for segment in related_segments}
        speaking_style = _clean_strings(payload.get("speakingStyleObserved"))
        mention = CharacterMention(
            id=f"mention_{uuid4().hex[:16]}",
            source_document_id=source_id,
            scene_id=window.scene_id,
            window_id=window.id,
            surface_name=surface_name,
            canonical_guess=str(payload.get("canonicalGuess") or surface_name).strip() or surface_name,
            normalized_key=key,
            entity_type=str(payload.get("entityType") or "unknown").strip().casefold() or "unknown",
            role_in_scene=str(payload.get("roleInScene") or "unknown").strip().casefold() or "unknown",
            evidence_text=str(payload.get("evidenceText") or "")[:400],
            segment_ids=segment_ids,
            atom_ids=atom_ids,
            confidence=_clamp_float(payload.get("confidence"), 0.0, 1.0),
            traits_observed=_clean_strings(payload.get("traitsObserved")),
            relationships_observed=_relationship_rows(payload.get("relationshipsObserved")),
            speaking_style_observed=speaking_style,
            llm_run_id=llm_run_id,
            metadata={
                "source": "llm_cast_discovery",
                "chapterIds": sorted(chapter_ids),
                "chapterStatuses": sorted(chapter_statuses),
                "speakingStyleObserved": speaking_style,
            },
        )
        return mention

    def _filter_mentions(
        self, mentions: list[CharacterMention], segments: list[ObservedSegment]
    ) -> tuple[list[CharacterMention], list[CharacterMention], list[dict[str, object]]]:
        segment_map = {segment.id: segment for segment in segments}
        counts: dict[str, int] = {}
        for mention in mentions:
            counts[mention.normalized_key] = counts.get(mention.normalized_key, 0) + 1
        persisted: list[CharacterMention] = []
        accepted: list[CharacterMention] = []
        diagnostics: list[dict[str, object]] = []
        for mention in mentions:
            filtered_out, reasons = _filter_reasons(mention, counts, segment_map)
            metadata = dict(mention.metadata)
            metadata["filteredOut"] = filtered_out
            metadata["filterReasons"] = reasons
            persisted_mention = CharacterMention(
                id=mention.id,
                source_document_id=mention.source_document_id,
                scene_id=mention.scene_id,
                window_id=mention.window_id,
                surface_name=mention.surface_name,
                canonical_guess=mention.canonical_guess,
                normalized_key=mention.normalized_key,
                entity_type=mention.entity_type,
                role_in_scene=mention.role_in_scene,
                evidence_text=mention.evidence_text,
                segment_ids=mention.segment_ids,
                atom_ids=mention.atom_ids,
                confidence=mention.confidence,
                traits_observed=mention.traits_observed,
                relationships_observed=mention.relationships_observed,
                speaking_style_observed=mention.speaking_style_observed,
                llm_run_id=mention.llm_run_id,
                metadata=metadata,
            )
            persisted.append(persisted_mention)
            if filtered_out:
                diagnostics.append(
                    {
                        "severity": "info",
                        "type": "mention_filtered",
                        "surfaceName": mention.surface_name,
                        "windowId": mention.window_id,
                        "segmentIds": mention.segment_ids,
                        "reasons": reasons,
                    }
                )
            else:
                accepted.append(persisted_mention)
        return persisted, accepted, diagnostics

    def _candidates_from_mentions(
        self, mentions: list[CharacterMention], segments: list[ObservedSegment]
    ) -> list[CharacterCandidate]:
        segment_map = {segment.id: segment for segment in segments}
        groups: list[list[CharacterMention]] = []
        for mention in sorted(
            mentions,
            key=lambda item: _mention_sort_key(item, segment_map),
        ):
            placed = False
            for group in groups:
                if _mentions_belong_together(group, mention):
                    group.append(mention)
                    placed = True
                    break
            if not placed:
                groups.append([mention])
        by_chapter: dict[str, str] = {segment.id: segment.chapter_id for segment in segments}
        candidates = [
            candidate
            for group in groups
            if (
                candidate := self._candidate_from_mentions(
                    group,
                    _first_chapter_id(group, by_chapter),
                    segment_map,
                )
            )
        ]
        return candidates

    def _v2_candidates(
        self,
        project_id: str,
        mentions: list[CharacterMention],
        segments: list[ObservedSegment],
    ) -> tuple[list[CharacterCandidate], ClusterResult]:
        cluster_mentions_input = [
            ClusterMention(
                id=mention.id,
                surface_name=mention.surface_name,
                canonical_guess=mention.canonical_guess,
                evidence_text=mention.evidence_text,
                window_id=mention.window_id,
                role_in_scene=mention.role_in_scene,
            )
            for mention in mentions
        ]
        embeddings, embedding_diagnostics = self._cast_embeddings(mentions)
        confirmed_pairs: set[frozenset[str]] = set()
        rejected_pairs: set[frozenset[str]] = set()
        for ruling in self.container.cast_merge_decisions.recent(project_id, limit=10_000):
            pair = frozenset({ruling.name_a, ruling.name_b})
            if len(pair) != 2:
                continue
            if ruling.decision == "confirmed":
                confirmed_pairs.add(pair)
            elif ruling.decision == "rejected":
                rejected_pairs.add(pair)
        result = cluster_mentions(
            cluster_mentions_input,
            embeddings=embeddings,
            confirmed_pairs=confirmed_pairs,
            rejected_pairs=rejected_pairs,
        )
        if embedding_diagnostics:
            result = replace(
                result,
                diagnostics=[*result.diagnostics, *embedding_diagnostics],
            )
        mention_by_id = {mention.id: mention for mention in mentions}
        segment_map = {segment.id: segment for segment in segments}
        by_chapter = {segment.id: segment.chapter_id for segment in segments}
        candidates: list[CharacterCandidate] = []
        for cluster in result.clusters:
            cluster_items = [
                mention_by_id[mention_id]
                for mention_id in cluster.mention_ids
                if mention_id in mention_by_id
            ]
            candidate = self._candidate_from_mentions(
                cluster_items,
                _first_chapter_id(cluster_items, by_chapter),
                segment_map,
            )
            if candidate:
                candidate.source = "+".join(
                    _clean_strings([candidate.source, "cast_v2_cluster"])
                )
                candidates.append(candidate)
        return candidates, result

    def _cast_embeddings(
        self, mentions: list[CharacterMention]
    ) -> tuple[dict[str, list[float]], list[dict[str, object]]]:
        installation = self.container.local_ai.installation(CAST_EMBEDDING_MODEL_KEY)
        if not installation or installation.status != "installed":
            return {}, [
                {
                    "severity": "info",
                    "type": "embedding_model_unavailable",
                    "message": (
                        "Cast v2 used conservative string clustering because the local "
                        "embedding model is not installed."
                    ),
                    "model": CAST_EMBEDDING_MODEL,
                }
            ]
        contexts: dict[str, list[str]] = {}
        display_names: dict[str, str] = {}
        for mention in mentions:
            key = _name_key(mention.surface_name)
            if not key:
                continue
            display_names.setdefault(key, mention.surface_name)
            if mention.evidence_text:
                contexts.setdefault(key, []).append(mention.evidence_text[:240])
        ordered_keys = sorted(display_names)
        inputs = [
            f"{display_names[key]} ‖ {' | '.join(contexts.get(key, [])[:3])}"
            for key in ordered_keys
        ]
        if not inputs:
            return {}, []
        try:
            result = LocalLlmService(self.container).embed(
                EmbeddingRequest(model=CAST_EMBEDDING_MODEL, input=inputs)
            )
        except ValueError as error:
            return {}, [
                {
                    "severity": "warning",
                    "type": "embedding_request_failed",
                    "message": "Cast v2 embedding failed; conservative string clustering was kept.",
                    "model": CAST_EMBEDDING_MODEL,
                    "error": str(error)[:500],
                }
            ]
        if len(result.embeddings) != len(ordered_keys):
            return {}, [
                {
                    "severity": "warning",
                    "type": "embedding_count_mismatch",
                    "message": "Cast v2 embedding count was incomplete; string clustering was kept.",
                    "expected": len(ordered_keys),
                    "actual": len(result.embeddings),
                }
            ]
        return dict(zip(ordered_keys, result.embeddings, strict=True)), []

    def _candidate_from_mentions(
        self,
        mentions: list[CharacterMention],
        first_chapter_id: str | None,
        segment_map: dict[str, ObservedSegment] | None = None,
    ) -> CharacterCandidate | None:
        if not mentions:
            return None
        canonical_name = _best_canonical_name(mentions)
        display_name = canonical_name or mentions[0].surface_name
        aliases = _clean_strings(
            [
                mention.surface_name
                for mention in mentions[1:]
                if _name_key(mention.surface_name) != _name_key(display_name)
            ]
            + [
                mention.canonical_guess or ""
                for mention in mentions
                if _name_key(mention.canonical_guess) not in {"", _name_key(display_name)}
            ]
        )
        mention_evidence = [
            json.dumps(
                {
                    "textPreview": mention.evidence_text,
                    "matchedText": mention.surface_name,
                    "sources": [str(mention.metadata.get("source") or "mention")],
                    "confidence": mention.confidence,
                    "segmentId": mention.segment_ids[0] if mention.segment_ids else None,
                    "windowId": mention.window_id,
                    "sceneId": mention.scene_id,
                    "startOffset": _segment_start_offset(mention.segment_ids, segment_map or {}),
                    "endOffset": _segment_end_offset(mention.segment_ids, segment_map or {}),
                },
                sort_keys=True,
            )
            for mention in mentions
        ]
        relationships = _merge_relationships(
            [item for mention in mentions for item in mention.relationships_observed]
        )
        speaking_style = _clean_strings(
            [item for mention in mentions for item in mention.speaking_style_observed]
        )
        candidate = CharacterCandidate(
            display_name=display_name,
            canonical_name=canonical_name,
            aliases=aliases,
            first_seen_segment_id=mentions[0].segment_ids[0] if mentions[0].segment_ids else None,
            first_seen_chapter_id=first_chapter_id,
            evidence=mention_evidence[:5],
            role_guess="narrator" if _name_key(display_name) == "narrator" else "supporting",
            confidence=max(mention.confidence for mention in mentions),
            source="+".join(
                sorted(
                    {
                        str(mention.metadata.get("source") or "mention")
                        for mention in mentions
                    }
                )
            ),
            mention_evidence=mention_evidence,
            traits=_clean_strings(
                [item for mention in mentions for item in mention.traits_observed]
            ),
            relationships=relationships,
            speaking_style=speaking_style,
            generated_aliases=_alias_candidates(canonical_name or display_name),
            window_ids=sorted({mention.window_id for mention in mentions}),
            scene_ids=sorted({mention.scene_id for mention in mentions if mention.scene_id}),
        )
        return candidate

    def _decision_for_candidate(
        self,
        project_id: str,
        candidate: CharacterCandidate,
        index: CharacterIndex,
        *,
        use_local_llm: bool,
        job_id: str | None = None,
    ) -> MergeDecision:
        exact_matches = [
            match
            for match in index.exact(candidate)
            if not self._pair_rejected(
                project_id, candidate.display_name, match.character.display_name
            )
        ]
        if len(exact_matches) == 1:
            exact = exact_matches[0]
            conflicts = _trait_conflicts(
                json.loads(exact.character.traits_json or "[]"), candidate.traits
            )
            if exact.reason != "generated_alias_exact" and not conflicts:
                return self._annotate_decision(
                    candidate,
                    MergeDecision(
                        id=f"castdec_{uuid4().hex[:16]}",
                        action="merge",
                        target_character_id=exact.character.id,
                        target_name=exact.character.display_name,
                        aliases=[],
                        confidence=max(candidate.confidence, 0.9),
                        reason=f"Deterministic exact match ({exact.reason}).",
                        evidence_segment_ids=_candidate_segment_ids(candidate),
                        metadata={"matchReason": exact.reason},
                    ),
                )

        shortlist = [
            match
            for match in index.shortlist(candidate)
            if not self._pair_rejected(project_id, candidate.display_name, match.character.display_name)
        ]
        if len(shortlist) == 1 and shortlist[0].score >= SAFE_SHORTLIST_SCORE:
            conflicts = _trait_conflicts(
                json.loads(shortlist[0].character.traits_json or "[]"), candidate.traits
            )
            if not conflicts:
                return self._annotate_decision(
                    candidate,
                    MergeDecision(
                        id=f"castdec_{uuid4().hex[:16]}",
                        action="merge",
                        target_character_id=shortlist[0].character.id,
                        target_name=shortlist[0].character.display_name,
                        aliases=[],
                        confidence=max(candidate.confidence, 0.84),
                        reason=f"Deterministic shortlist winner ({shortlist[0].reason}).",
                        evidence_segment_ids=_candidate_segment_ids(candidate),
                        metadata={
                            "shortlist": _shortlist_payload(shortlist),
                            "matchReason": shortlist[0].reason,
                        },
                    ),
                )

        if shortlist and use_local_llm:
            decision = self._llm_merge_decision(
                project_id, candidate, shortlist, job_id=job_id
            )
            if decision:
                return self._annotate_decision(candidate, decision)

        if not shortlist and candidate.confidence >= AUTO_CREATE_CONFIDENCE:
            return self._annotate_decision(
                candidate,
                MergeDecision(
                    id=f"castdec_{uuid4().hex[:16]}",
                    action="new",
                    target_character_id=None,
                    target_name=None,
                    aliases=[],
                    confidence=candidate.confidence,
                    reason="Filtered candidate is unique and above auto-create confidence.",
                    evidence_segment_ids=_candidate_segment_ids(candidate),
                    metadata={},
                ),
            )

        return self._annotate_decision(
            candidate,
            MergeDecision(
                id=f"castdec_{uuid4().hex[:16]}",
                action="unsure",
                target_character_id=None,
                target_name=None,
                aliases=[],
                confidence=candidate.confidence,
                reason=(
                    "Candidate remains ambiguous after deterministic shortlisting."
                    if shortlist
                    else "Candidate confidence was too low for automatic creation."
                ),
                evidence_segment_ids=_candidate_segment_ids(candidate),
                metadata={"shortlist": _shortlist_payload(shortlist)},
            ),
        )

    def _decision_for_cluster(
        self,
        project_id: str,
        candidate: CharacterCandidate,
        index: CharacterIndex,
        *,
        use_local_llm: bool,
        job_id: str | None = None,
    ) -> MergeDecision:
        deterministic = self._decision_for_candidate(
            project_id,
            candidate,
            index,
            use_local_llm=False,
            job_id=job_id,
        )
        if deterministic.action == "merge" or not use_local_llm:
            return replace(
                deterministic,
                metadata={**deterministic.metadata, "reconcileMode": "cluster"},
            )
        shortlist = [
            match
            for match in index.shortlist(candidate)
            if not self._pair_rejected(
                project_id, candidate.display_name, match.character.display_name
            )
        ]
        reconciled = self._llm_merge_decision(
            project_id,
            candidate,
            shortlist,
            task="cast_cluster_reconcile",
            job_id=job_id,
        )
        if reconciled is None or (not shortlist and reconciled.action == "unsure"):
            return replace(
                deterministic,
                metadata={
                    **deterministic.metadata,
                    "reconcileMode": "cluster",
                    "reconcileFallback": True,
                },
            )
        return self._annotate_decision(
            candidate,
            replace(
                reconciled,
                metadata={**reconciled.metadata, "reconcileMode": "cluster"},
            ),
        )

    def _llm_merge_decision(
        self,
        project_id: str,
        candidate: CharacterCandidate,
        shortlist: list[CharacterMatch],
        *,
        task: str = "cast_merge_verification",
        job_id: str | None = None,
    ) -> MergeDecision | None:
        llm = LocalLlmService(self.container)
        checkpoint = (
            CheckpointContext(
                job_id=job_id,
                project_id=project_id,
                stage="cast.discovery.merge-decision",
                scope={
                    "candidateKey": candidate.key,
                    "task": task,
                    "shortlist": sorted(match.character.id for match in shortlist),
                },
            )
            if job_id
            else None
        )
        try:
            result = llm.extract(
                project_id,
                LlmExtractionRequest(
                    model=DEFAULT_REFINEMENT_MODEL,
                    task=task,
                    schema=CAST_MERGE_SCHEMA,
                    prompt=(
                        self._cluster_reconcile_prompt(project_id, candidate, shortlist)
                        if task == "cast_cluster_reconcile"
                        else self._merge_prompt(project_id, candidate, shortlist)
                    ),
                ),
                checkpoint=checkpoint,
            )
        except ValueError as error:
            return MergeDecision(
                id=f"castdec_{uuid4().hex[:16]}",
                action="unsure",
                target_character_id=None,
                target_name=None,
                aliases=[],
                confidence=candidate.confidence,
                reason="LLM shortlist adjudication failed; deterministic review fallback was kept.",
                evidence_segment_ids=_candidate_segment_ids(candidate),
                metadata={
                    "shortlist": _shortlist_payload(shortlist),
                    "llmError": str(error)[:500],
                },
            )
        raw_decisions = result.result.get("decisions")
        if not isinstance(raw_decisions, list):
            return MergeDecision(
                id=f"castdec_{uuid4().hex[:16]}",
                action="unsure",
                target_character_id=None,
                target_name=None,
                aliases=[],
                confidence=candidate.confidence,
                reason="LLM shortlist adjudication returned no usable decision.",
                evidence_segment_ids=_candidate_segment_ids(candidate),
                llm_run_id=result.run.id,
                metadata={"shortlist": _shortlist_payload(shortlist)},
            )
        for item in raw_decisions:
            if not isinstance(item, dict):
                continue
            payload = cast(dict[str, object], item)
            display_name = str(payload.get("displayName") or "").strip()
            if _name_key(display_name) != candidate.key:
                continue
            action = str(payload.get("action") or "unsure").strip().casefold()
            target_character_id = str(payload.get("targetCharacterId") or "").strip() or None
            target_name = str(payload.get("targetName") or "").strip() or None
            if action == "merge_existing":
                action = "merge"
            if action not in {"merge", "new", "split", "unsure"}:
                action = "unsure"
            return MergeDecision(
                id=f"castdec_{uuid4().hex[:16]}",
                action=action,
                target_character_id=target_character_id,
                target_name=target_name,
                aliases=_clean_strings(payload.get("aliases")),
                confidence=_clamp_float(payload.get("confidence"), candidate.confidence, 1.0),
                reason=str(payload.get("reason") or "").strip()
                or "LLM shortlist adjudication returned no explanation.",
                evidence_segment_ids=_clean_strings(payload.get("evidenceSegmentIds"))
                or _candidate_segment_ids(candidate),
                llm_run_id=result.run.id,
                metadata={"shortlist": _shortlist_payload(shortlist)},
            )
        return MergeDecision(
            id=f"castdec_{uuid4().hex[:16]}",
            action="unsure",
            target_character_id=None,
            target_name=None,
            aliases=[],
            confidence=candidate.confidence,
            reason="LLM shortlist adjudication did not return a matching candidate decision.",
            evidence_segment_ids=_candidate_segment_ids(candidate),
            llm_run_id=result.run.id,
            metadata={"shortlist": _shortlist_payload(shortlist)},
        )

    def _profile_candidate(
        self,
        project_id: str,
        candidate: CharacterCandidate,
        *,
        use_local_llm: bool,
        job_id: str | None = None,
    ) -> tuple[CharacterCandidate, dict[str, object]]:
        profile = self._deterministic_profile(candidate)
        if use_local_llm:
            checkpoint = (
                CheckpointContext(
                    job_id=job_id,
                    project_id=project_id,
                    stage="cast.discovery.profile",
                    scope={"candidateKey": candidate.key},
                )
                if job_id
                else None
            )
            try:
                result = LocalLlmService(self.container).extract(
                    project_id,
                    LlmExtractionRequest(
                        model=DEFAULT_REFINEMENT_MODEL,
                        task="cast_profile_synthesis",
                        schema=CAST_PROFILE_SCHEMA,
                        prompt=self._profile_prompt(candidate),
                    ),
                    checkpoint=checkpoint,
                )
            except ValueError as error:
                profile["fallbackReason"] = str(error)[:500]
            else:
                raw_profile = result.result.get("profile")
                if isinstance(raw_profile, dict):
                    profile = self._normalized_profile(
                        candidate,
                        cast(dict[str, object], raw_profile),
                    )
                    profile["llmRunId"] = result.run.id
        gender = str(profile.get("gender") or "unknown")
        age_band = str(profile.get("ageBand") or "unknown")
        profile_traits = _clean_strings(profile.get("traits"))
        traits = _clean_strings(
            [
                *candidate.traits,
                *profile_traits,
                *([f"gender:{gender}"] if gender != "unknown" else []),
                *([f"age:{age_band}"] if age_band != "unknown" else []),
            ]
        )
        speech_style = _clean_strings(
            [*candidate.speaking_style, *_speech_style_strings(profile.get("speechStyle"))]
        )
        relationships = _merge_relationships(
            [*candidate.relationships, *_relationship_rows(profile.get("relationships"))]
        )
        updated = replace(
            candidate,
            role_guess=str(profile.get("role") or candidate.role_guess),
            confidence=max(
                candidate.confidence,
                _clamp_float(profile.get("confidence"), candidate.confidence, 1.0),
            ),
            traits=traits,
            relationships=relationships,
            speaking_style=speech_style,
        )
        profile["aliases"] = _clean_strings(
            [*candidate.aliases, *candidate.generated_aliases]
        )
        profile["evidenceWindowIds"] = candidate.window_ids
        return updated, profile

    @staticmethod
    def _deterministic_profile(candidate: CharacterCandidate) -> dict[str, object]:
        gender = _trait_value(candidate.traits, "gender") or "unknown"
        age_band = _trait_value(candidate.traits, "age") or "unknown"
        return {
            "displayName": candidate.display_name,
            "role": candidate.role_guess,
            "gender": gender,
            "ageBand": age_band,
            "traits": candidate.traits,
            "speechStyle": _speech_style_payload(candidate.speaking_style),
            "relationships": candidate.relationships,
            "confidence": candidate.confidence,
            "source": "deterministic_fallback",
        }

    @staticmethod
    def _normalized_profile(
        candidate: CharacterCandidate, payload: dict[str, object]
    ) -> dict[str, object]:
        return {
            "displayName": str(payload.get("displayName") or candidate.display_name).strip()
            or candidate.display_name,
            "role": str(payload.get("role") or candidate.role_guess).strip().casefold()
            or candidate.role_guess,
            "gender": str(payload.get("gender") or "unknown").strip().casefold()
            or "unknown",
            "ageBand": str(payload.get("ageBand") or "unknown").strip().casefold()
            or "unknown",
            "traits": _clean_strings(payload.get("traits")),
            "speechStyle": _speech_style_object(payload.get("speechStyle")),
            "relationships": _relationship_rows(payload.get("relationships")),
            "confidence": _clamp_float(
                payload.get("confidence"), candidate.confidence, 1.0
            ),
            "source": "llm_profile_synthesis",
        }

    @staticmethod
    def _resolved_character(
        candidate: CharacterCandidate,
        decision: MergeDecision,
        index: CharacterIndex,
    ) -> CharacterRecord | None:
        if decision.target_character_id:
            return next(
                (
                    character
                    for character in index.characters
                    if character.id == decision.target_character_id
                ),
                None,
            )
        matches = index.exact(candidate)
        active = [match.character for match in matches if not match.character.merged_into_character_id]
        return active[0] if len({character.id for character in active}) == 1 else None

    def _apply_candidate(
        self,
        project_id: str,
        source_id: str | None,
        candidate: CharacterCandidate,
        decision: MergeDecision,
        index: CharacterIndex,
    ) -> None:
        if decision.action == "merge":
            target = (
                self.container.casting.character(decision.target_character_id)
                if decision.target_character_id
                else index.first_by_name(decision.target_name)
            )
            if target and not self._pair_rejected(
                project_id, candidate.display_name, target.display_name
            ):
                updated = self._merge_character_observations(target, candidate, decision.aliases)
                if updated:
                    index.add_character(updated)
                return
        if decision.action == "new" and candidate.confidence >= AUTO_CREATE_CONFIDENCE:
            evidence_graph = _candidate_evidence_graph(candidate)
            record = self.container.casting.create_character(
                project_id=project_id,
                name=candidate.display_name,
                aliases=[
                    *candidate.aliases,
                    *candidate.generated_aliases,
                    *decision.aliases,
                ],
                role=candidate.role_guess,
                confidence=max(candidate.confidence, decision.confidence),
                notes=json.dumps(
                    {
                        "source": candidate.source,
                        "evidenceGraph": evidence_graph,
                        "evidence": candidate.evidence,
                        "mentionEvidence": candidate.mention_evidence,
                        "decision": decision.reason,
                        "relationships": candidate.relationships,
                        "speakingStyle": candidate.speaking_style,
                    },
                    sort_keys=True,
                ),
                canonical_name=candidate.canonical_name,
                traits=candidate.traits,
                relationships=candidate.relationships,
                speaking_style=candidate.speaking_style,
                first_seen_source_id=source_id,
                first_seen_chapter_id=candidate.first_seen_chapter_id,
                first_seen_segment_id=candidate.first_seen_segment_id,
            )
            index.add_character(record)
            return
        if decision.action == "split":
            self._create_ambiguous_issue(
                project_id,
                candidate,
                decision.reason or "Candidate cluster should split before creation.",
                [],
                decision,
            )
            return
        if decision.action == "unsure" and decision.confidence < AUTO_CREATE_CONFIDENCE:
            self._create_low_confidence_issue(project_id, candidate, decision)
            return
        shortlist = []
        for match in cast(list[dict[str, object]], decision.metadata.get("shortlist") or []):
            if not isinstance(match, dict):
                continue
            character_id = match.get("characterId")
            if not isinstance(character_id, str):
                continue
            shortlist.append(self.container.casting.character(character_id))
        possible = [item for item in shortlist if item]
        if possible or decision.action == "unsure":
            self._create_ambiguous_issue(
                project_id,
                candidate,
                decision.reason or "Candidate was not confidently safe to create or merge automatically.",
                possible,
                decision,
            )
            return
        self._create_low_confidence_issue(project_id, candidate, decision)

    @staticmethod
    def _annotate_decision(candidate: CharacterCandidate, decision: MergeDecision) -> MergeDecision:
        return replace(
            decision,
            metadata={
                **decision.metadata,
                "candidateKey": candidate.key,
                "candidateDisplayName": candidate.display_name,
                "candidateCanonicalName": candidate.canonical_name,
                "candidateAliases": _clean_strings(
                    [*candidate.aliases, *candidate.generated_aliases]
                ),
                "candidateSource": candidate.source,
                "mentionCount": len(candidate.mention_evidence),
                "windowIds": candidate.window_ids,
                "sceneIds": candidate.scene_ids,
            },
        )

    def _merge_character_observations(
        self,
        character: CharacterRecord,
        candidate: CharacterCandidate,
        extra_aliases: list[str] | None = None,
    ) -> CharacterRecord | None:
        if character.user_locked:
            return character
        aliases = _clean_strings(json.loads(character.aliases_json or "[]"))
        traits = _clean_strings(json.loads(character.traits_json or "[]"))
        relationships = _relationship_rows(json.loads(character.relationships_json or "[]"))
        speaking_style = _clean_strings(json.loads(character.speaking_style_json or "[]"))
        additions = [
            candidate.display_name,
            *(candidate.aliases or []),
            *(candidate.generated_aliases or []),
            *(extra_aliases or []),
        ]
        merged_aliases = _clean_strings([*aliases, *additions])
        merged_traits = _clean_strings([*traits, *candidate.traits])
        merged_relationships = _merge_relationships(
            [*relationships, *candidate.relationships]
        )
        merged_speaking_style = _clean_strings([*speaking_style, *candidate.speaking_style])
        next_confidence = max(character.confidence, candidate.confidence)
        notes = _merge_character_notes(character.notes, candidate)
        if (
            merged_aliases != aliases
            or merged_traits != traits
            or merged_relationships != relationships
            or merged_speaking_style != speaking_style
            or next_confidence != character.confidence
            or notes != character.notes
        ):
            return self.container.casting.update_character(
                character.id,
                aliases=merged_aliases,
                traits=merged_traits,
                relationships=merged_relationships,
                speaking_style=merged_speaking_style,
                confidence=next_confidence,
                notes=notes,
            )
        return character

    def _pair_rejected(self, project_id: str, name_a: str, name_b: str) -> bool:
        return self.container.cast_merge_decisions.is_rejected(project_id, name_a, name_b)

    def _create_ambiguous_issue(
        self,
        project_id: str,
        candidate: CharacterCandidate,
        reason: str,
        possible_matches: list[CharacterRecord] | None = None,
        decision: MergeDecision | None = None,
    ) -> None:
        matches = possible_matches or []
        self.container.review.create_issue(
            project_id=project_id,
            category="cast_discovery",
            severity="warning",
            title="Possible duplicate cast candidate",
            description=(
                f"{candidate.display_name} was observed in the manuscript but was not "
                "confidently safe to create or merge automatically."
            ),
            chapter_id=candidate.first_seen_chapter_id,
            segment_id=candidate.first_seen_segment_id,
            metadata={
                "code": "cast.possible_duplicate",
                "reviewAction": "merge_cast",
                "candidateName": candidate.display_name,
                "canonicalName": candidate.canonical_name,
                "possibleMatches": [match.display_name for match in matches],
                "possibleMatchIds": [match.id for match in matches],
                "displayName": candidate.display_name,
                "aliases": _clean_strings([*candidate.aliases, *candidate.generated_aliases]),
                "generatedAliases": candidate.generated_aliases,
                "traits": candidate.traits,
                "relationships": candidate.relationships,
                "speakingStyle": candidate.speaking_style,
                "mentionCount": len(candidate.mention_evidence),
                "windowIds": candidate.window_ids,
                "confidence": candidate.confidence,
                "source": candidate.source,
                "reason": reason,
                "decisionId": decision.id if decision else None,
                "evidence": candidate.evidence,
                "mentionEvidence": candidate.mention_evidence,
                "evidenceGraph": _candidate_evidence_graph(candidate),
            },
            dedupe_key=(
                f"cast-candidate:{project_id}:{candidate.key}:"
                f"{candidate.first_seen_segment_id or 'project'}"
            ),
        )

    def _create_low_confidence_issue(
        self, project_id: str, candidate: CharacterCandidate, decision: MergeDecision | None = None
    ) -> None:
        self.container.review.create_issue(
            project_id=project_id,
            category="cast_discovery",
            severity="warning",
            title="Low-confidence cast candidate",
            description=(
                f"{candidate.display_name} was observed in the manuscript but needs "
                "confirmation before creating a Character Bible record."
            ),
            chapter_id=candidate.first_seen_chapter_id,
            segment_id=candidate.first_seen_segment_id,
            metadata={
                "code": "cast.low_confidence_candidate",
                "reviewAction": "confirm_cast",
                "candidateName": candidate.display_name,
                "canonicalName": candidate.canonical_name,
                "confidence": candidate.confidence,
                "traits": candidate.traits,
                "relationships": candidate.relationships,
                "speakingStyle": candidate.speaking_style,
                "windowIds": candidate.window_ids,
                "mentionCount": len(candidate.mention_evidence),
                "source": candidate.source,
                "reason": (
                    decision.reason if decision else "Candidate confidence was too low."
                ),
                "decisionId": decision.id if decision else None,
                "evidence": candidate.evidence,
                "mentionEvidence": candidate.mention_evidence,
                "evidenceGraph": _candidate_evidence_graph(candidate),
            },
            dedupe_key=(
                f"cast-candidate-low-confidence:{project_id}:{candidate.key}:"
                f"{candidate.first_seen_segment_id or 'project'}"
            ),
        )

    def _segments(self, project_id: str) -> list[ObservedSegment]:
        with self.container.structure.database.session() as session:
            rows = session.execute(
                select(SegmentRecord, SceneRecord, ChapterRecord)
                .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                .where(ChapterRecord.project_id == project_id)
                .order_by(ChapterRecord.order_index, SceneRecord.order_index, SegmentRecord.order_index)
            )
            return [
                ObservedSegment(
                    id=segment.id,
                    scene_id=scene.id,
                    chapter_id=chapter.id,
                    chapter_status=chapter.status,
                    chapter_title=chapter.title,
                    chapter_order=chapter.order_index,
                    scene_order=scene.order_index,
                    text=segment.text_content,
                    segment_type=segment.segment_type,
                    start_offset=segment.start_offset,
                    end_offset=segment.end_offset,
                    speaker_candidate=segment.speaker_candidate,
                    speaker_confidence=segment.speaker_confidence,
                    parser_evidence=_evidence(segment.parser_evidence_json),
                )
                for segment, scene, chapter in rows
            ]

    def _character_index(self, project_id: str) -> CharacterIndex:
        characters = [
            character
            for character in self.container.casting.characters(project_id)
            if not character.merged_into_character_id
        ]
        index = CharacterIndex(characters=characters)
        for character in characters:
            index.add_character(character)
        return index

    def _local_llm_ready(self) -> bool:
        installation = self.container.local_ai.installation(DEFAULT_REFINEMENT_MODEL_KEY)
        return bool(installation and installation.status == "installed")

    def _cast_prompt(
        self, window: CastWindow, segment_map: dict[str, ObservedSegment]
    ) -> str:
        segment_lines = "\n".join(
            (
                f"- {segment.id} [{segment.segment_type}] "
                f"speakerHint={segment.speaker_candidate or ''}: "
                f"{segment.text[:700].replace(chr(10), ' ')}"
            )
            for segment in (segment_map[segment_id] for segment_id in window.segment_ids)
        )
        return (
            "Extract only person-like character mentions from this bounded manuscript window. "
            "Do not create final cast rows. Return mentions that are speakers, present in-scene, "
            "mentioned in nearby narration, or referenced in dialogue. Exclude places, "
            "organizations, book metadata, headings, and non-character entities. "
            "Use exact segment IDs from the provided list. Return only JSON matching the schema.\n\n"
            f"Window: {window.id}\n"
            f"Chapter status: {window.chapter_status}\n\n"
            f"Segments:\n{segment_lines}"
        )

    def _merge_prompt(
        self,
        project_id: str,
        candidate: CharacterCandidate,
        shortlist: list[CharacterMatch],
    ) -> str:
        shortlist_lines = "\n".join(
            (
                f"- id={match.character.id}; name={match.character.display_name}; "
                f"canonical={match.character.canonical_name or ''}; "
                f"aliases={', '.join(_clean_strings(json.loads(match.character.aliases_json or '[]')))}; "
                f"traits={', '.join(_clean_strings(json.loads(match.character.traits_json or '[]')))}; "
                f"reason={match.reason}"
            )
            for match in shortlist
        )
        decision_block = self._merge_decision_block(project_id)
        return (
            "Compare one cast candidate against a short deterministic shortlist of possible "
            "existing Character Bible matches. Choose exactly one action: merge_existing, new, "
            "split, or unsure. Use merge_existing only when the evidence clearly points to one "
            "shortlisted character. Use new only when the candidate is unique. Return only JSON "
            "matching the schema.\n\n"
            f"{decision_block}"
            f"Candidate:\n"
            f"- displayName={candidate.display_name}\n"
            f"- canonicalName={candidate.canonical_name or ''}\n"
            f"- aliases={', '.join(_clean_strings([*candidate.aliases, *candidate.generated_aliases]))}\n"
            f"- confidence={candidate.confidence:.2f}\n"
            f"- evidence={' | '.join(candidate.mention_evidence[:2])}\n\n"
            f"Possible matches:\n{shortlist_lines}"
        )

    def _cluster_reconcile_prompt(
        self,
        project_id: str,
        candidate: CharacterCandidate,
        shortlist: list[CharacterMatch],
    ) -> str:
        base = self._merge_prompt(project_id, candidate, shortlist)
        return (
            "Reconcile one already-clustered set of character mentions. Confirm that its aliases "
            "describe one character, split only when pooled evidence proves distinct people, and "
            "choose a canonical display name. Prior human rulings are hard constraints. This is one "
            "decision for the whole cluster, never a pairwise mention adjudication.\n\n"
            f"Cluster windows: {', '.join(candidate.window_ids)}\n"
            f"Cluster scenes: {', '.join(candidate.scene_ids)}\n\n"
            f"{base}"
        )

    @staticmethod
    def _profile_prompt(candidate: CharacterCandidate) -> str:
        return (
            "Synthesize one conservative audiobook casting profile from pooled evidence for a "
            "confirmed character cluster. Do not infer protected or demographic traits without "
            "textual evidence; use 'unknown' when absent. Keep speech style production-useful and "
            "relationships evidence-bound. Return only JSON matching the schema.\n\n"
            f"Display name: {candidate.display_name}\n"
            f"Aliases: {', '.join(_clean_strings([*candidate.aliases, *candidate.generated_aliases]))}\n"
            f"Observed traits: {', '.join(candidate.traits)}\n"
            f"Observed speaking style: {', '.join(candidate.speaking_style)}\n"
            f"Observed relationships: {json.dumps(candidate.relationships, sort_keys=True)}\n"
            f"Evidence: {' | '.join(candidate.mention_evidence[:8])}"
        )

    def _merge_decision_block(self, project_id: str) -> str:
        decisions = self.container.cast_merge_decisions.recent(project_id, limit=10)
        if not decisions:
            return ""
        lines: list[str] = []
        for decision in decisions:
            verdict = (
                "confirmed same person"
                if decision.decision == "confirmed"
                else "different people"
            )
            lines.append(f'- "{decision.name_a}" and "{decision.name_b}": {verdict}')
        return "Previously confirmed decisions (respect these):\n" + "\n".join(lines) + "\n\n"

    def _write_manifest(
        self,
        project_id: str,
        source_id: str | None,
        windows: list[CastWindow],
        mentions: list[CharacterMention],
        candidates: list[CharacterCandidate],
        decisions: list[MergeDecision],
        diagnostics: list[dict[str, object]],
        *,
        cluster_result: ClusterResult | None = None,
        profiles: list[dict[str, object]] | None = None,
    ) -> None:
        project = self.container.projects.get(project_id)
        if not project:
            return
        filtered_mentions = [
            mention for mention in mentions if bool(mention.metadata.get("filteredOut"))
        ]
        manifest = {
            "manifestType": "casting_manifest",
            "schemaVersion": "0.2.0" if cluster_result else "0.1.0",
            "manifestVersion": "cast-v2" if cluster_result else "cast-v1",
            "projectId": project_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "status": "completed",
            "diagnostics": diagnostics,
            "payload": {
                "sourceDocumentId": source_id,
                "windowCount": len(windows),
                "mentionCount": len(mentions),
                "filteredMentionCount": len(filtered_mentions),
                "candidateCount": len(candidates),
                "decisionCount": len(decisions),
                "castV2": (
                    {
                        "version": CAST_V2_VERSION,
                        "embeddingModel": CAST_EMBEDDING_MODEL,
                        "embeddingUsed": cluster_result.embedding_used,
                        "threshold": cluster_result.threshold,
                    }
                    if cluster_result
                    else None
                ),
                "clusters": (
                    [
                        {
                            "id": cluster.id,
                            "mentionIds": cluster.mention_ids,
                            "normalizedKeys": cluster.normalized_keys,
                            "surfaceForms": cluster.surface_forms,
                            "confidence": cluster.confidence,
                        }
                        for cluster in cluster_result.clusters
                    ]
                    if cluster_result
                    else []
                ),
                "clusterDiagnostics": (
                    {
                        "merges": [
                            {
                                "leftKey": merge.left_key,
                                "rightKey": merge.right_key,
                                "score": merge.score,
                                "reason": merge.reason,
                            }
                            for merge in cluster_result.merges
                        ],
                        "cannotLinkPairs": cluster_result.cannot_link_pairs,
                    }
                    if cluster_result
                    else None
                ),
                "profiles": profiles or [],
                "mentions": [
                    {
                        "id": mention.id,
                        "surfaceName": mention.surface_name,
                        "canonicalGuess": mention.canonical_guess,
                        "windowId": mention.window_id,
                        "sceneId": mention.scene_id,
                        "segmentIds": mention.segment_ids,
                        "confidence": mention.confidence,
                        "filteredOut": bool(mention.metadata.get("filteredOut")),
                        "filterReasons": mention.metadata.get("filterReasons") or [],
                    }
                    for mention in mentions
                ],
                "candidates": [
                    {
                        "key": candidate.key,
                        "displayName": candidate.display_name,
                        "canonicalName": candidate.canonical_name,
                        "aliases": _clean_strings([*candidate.aliases, *candidate.generated_aliases]),
                        "mentionCount": len(candidate.mention_evidence),
                        "windowIds": candidate.window_ids,
                        "confidence": candidate.confidence,
                    }
                    for candidate in candidates
                ],
                "decisions": [
                    {
                        "id": decision.id,
                        "sourceKey": next(
                            (
                                candidate.key
                                for candidate in candidates
                                if candidate.display_name
                                == cast(str, decision.metadata.get("candidateDisplayName"))
                            ),
                            None,
                        ),
                        "action": decision.action,
                        "targetCharacterId": decision.target_character_id,
                        "targetName": decision.target_name,
                        "confidence": decision.confidence,
                        "reason": decision.reason,
                        "evidenceSegmentIds": decision.evidence_segment_ids,
                    }
                    for decision in decisions
                ],
                "characterUpdates": [
                    {
                        "id": character.id,
                        "displayName": character.display_name,
                        "canonicalName": character.canonical_name,
                        "aliases": _clean_strings(json.loads(character.aliases_json or "[]")),
                    }
                    for character in self.container.casting.characters(project_id)
                    if not character.merged_into_character_id
                ],
            },
        }
        root = Path(project.artifact_path) / "manifests"
        root.mkdir(parents=True, exist_ok=True)
        version = root / f"casting_manifest.{uuid4().hex[:12]}.json"
        version.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (root / "casting_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _latest_source_id(self, project_id: str) -> str | None:
        source = self.container.sources.latest(project_id)
        return source.id if source else None

    @staticmethod
    def _mention_payload(mention: CharacterMention) -> dict[str, object]:
        return {
            "id": mention.id,
            "sourceDocumentId": mention.source_document_id,
            "sceneId": mention.scene_id,
            "windowId": mention.window_id,
            "surfaceName": mention.surface_name,
            "canonicalGuess": mention.canonical_guess,
            "normalizedKey": mention.normalized_key,
            "entityType": mention.entity_type,
            "roleInScene": mention.role_in_scene,
            "evidenceText": mention.evidence_text,
            "segmentIds": mention.segment_ids,
            "atomIds": mention.atom_ids,
            "confidence": mention.confidence,
            "traitsObserved": mention.traits_observed,
            "relationshipsObserved": mention.relationships_observed,
            "llmRunId": mention.llm_run_id,
            "metadata": {
                **mention.metadata,
                "speakingStyleObserved": mention.speaking_style_observed,
            },
        }

    @staticmethod
    def _decision_payload(decision: MergeDecision) -> dict[str, object]:
        return {
            "id": decision.id,
            "sourceKey": cast(str, decision.metadata.get("candidateKey") or ""),
            "sourceName": cast(str, decision.metadata.get("candidateDisplayName") or ""),
            "decision": decision.action,
            "targetCharacterId": decision.target_character_id,
            "targetName": decision.target_name,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "evidenceSegmentIds": decision.evidence_segment_ids,
            "llmRunId": decision.llm_run_id,
            "metadata": decision.metadata,
        }


def _cast_windows(segments: list[ObservedSegment]) -> list[CastWindow]:
    by_scene: dict[str, list[ObservedSegment]] = {}
    for segment in segments:
        by_scene.setdefault(segment.scene_id, []).append(segment)
    windows: list[CastWindow] = []
    for scene_segments in by_scene.values():
        current: list[ObservedSegment] = []
        current_chars = 0
        index = 1
        for segment in scene_segments:
            length = len(segment.text)
            if current and current_chars + length > CAST_WINDOW_MAX_CHARS:
                windows.append(_window_from_segments(current, index))
                overlap = current[-CAST_WINDOW_OVERLAP_SEGMENTS :]
                current = [*overlap, segment]
                current_chars = sum(len(item.text) for item in current)
                index += 1
                continue
            current.append(segment)
            current_chars += length
        if current:
            windows.append(_window_from_segments(current, index))
    return windows


def _window_from_segments(segments: list[ObservedSegment], index: int) -> CastWindow:
    atom_ids = sorted(
        {
            atom_id
            for segment in segments
            for atom_id in _string_list(segment.parser_evidence.get("atomIds"))
        }
    )
    return CastWindow(
        id=f"castwin_{segments[0].scene_id}_{index:03d}",
        scene_id=segments[0].scene_id,
        chapter_id=segments[0].chapter_id,
        chapter_status=segments[0].chapter_status,
        segment_ids=[segment.id for segment in segments],
        atom_ids=atom_ids,
        text="\n\n".join(segment.text for segment in segments),
    )


def _character_index_names(character: CharacterRecord) -> list[tuple[str, str]]:
    names = [
        (character.display_name, "display_name"),
        (character.canonical_name or "", "canonical_name"),
    ]
    names.extend(
        (alias, "persisted_alias")
        for alias in _clean_strings(json.loads(character.aliases_json or "[]"))
    )
    return names


def _candidate_index_names(candidate: CharacterCandidate) -> list[tuple[str, str]]:
    names = [
        (candidate.display_name, "display_name"),
        (candidate.canonical_name or "", "canonical_name"),
    ]
    names.extend((alias, "observed_alias") for alias in candidate.aliases)
    names.extend((alias, "generated_alias") for alias in candidate.generated_aliases)
    return names


def _candidate_match_score(
    candidate: CharacterCandidate, character: CharacterRecord
) -> tuple[int, str]:
    candidate_keys = {
        _name_key(name)
        for name, _source in _candidate_index_names(candidate)
        if _name_key(name)
    }
    character_names = _character_index_names(character)
    character_keys = {_name_key(name) for name, _source in character_names if _name_key(name)}
    if not candidate_keys or not character_keys:
        return 0, ""

    for name, source in character_names:
        key = _name_key(name)
        if key in candidate_keys:
            return 120, f"{source}_exact"

    if any(_honorific_surname_match(left, right) for left in candidate_keys for right in character_keys):
        return 70, "honorific_surname"
    if any(_nickname_match(left, right) for left in candidate_keys for right in character_keys):
        return 80, "nickname"
    if any(_soft_name_match(left, right) for left in candidate_keys for right in character_keys):
        return 65, "soft_name"

    relationship_overlap = _relationship_overlap(
        candidate.relationships, _relationship_rows(_json_load(character.relationships_json))
    )
    if relationship_overlap:
        return 40, "relationship_overlap"

    if candidate.first_seen_chapter_id and candidate.first_seen_chapter_id == character.first_seen_chapter_id:
        return 10, "nearby_chapter"
    return 0, ""


def _mentions_belong_together(group: list[CharacterMention], mention: CharacterMention) -> bool:
    group_keys = {
        _name_key(item.canonical_guess or item.surface_name)
        for item in group
        if _name_key(item.canonical_guess or item.surface_name)
    }
    mention_keys = {
        _name_key(mention.surface_name),
        _name_key(mention.canonical_guess),
    } - {""}
    for left in group_keys:
        for right in mention_keys:
            if left == right or _soft_name_match(left, right) or _honorific_surname_match(left, right):
                return True
    return False


def _mention_sort_key(
    mention: CharacterMention,
    segment_map: dict[str, ObservedSegment],
) -> tuple[int, int, int, str, str]:
    for segment_id in mention.segment_ids:
        segment = segment_map.get(segment_id)
        if segment:
            return (
                segment.chapter_order,
                segment.scene_order,
                segment.start_offset,
                mention.window_id,
                mention.id,
            )
    return (
        sys.maxsize,
        sys.maxsize,
        sys.maxsize,
        mention.window_id,
        mention.id,
    )


def _first_chapter_id(mentions: list[CharacterMention], by_segment: dict[str, str]) -> str | None:
    for mention in mentions:
        for segment_id in mention.segment_ids:
            if segment_id in by_segment:
                return by_segment[segment_id]
    return None


def _best_canonical_name(mentions: list[CharacterMention]) -> str | None:
    raw_candidates = [
        (
            candidate.strip(),
            mention.segment_ids[0] if mention.segment_ids else mention.id,
        )
        for mention in mentions
        for candidate in [mention.canonical_guess, mention.surface_name]
        if isinstance(candidate, str) and candidate.strip()
    ]
    bare_form_segments: dict[str, set[str]] = {}
    for candidate, segment_ref in raw_candidates:
        bare_form_segments.setdefault(_name_key(candidate), set()).add(segment_ref)
    explicit = [
        canonical
        for candidate, segment_ref in raw_candidates
        if (canonical := _canonical_person_name(candidate, segment_ref, bare_form_segments))
    ]
    multi_token = [candidate for candidate in explicit if len(_name_key(candidate).split()) >= 2]
    if multi_token:
        return max(multi_token, key=lambda item: (len(_name_key(item).split()), len(item)))
    return explicit[0] if explicit else None


def _canonical_person_name(
    value: str | None,
    segment_ref: str,
    bare_form_segments: dict[str, set[str]],
) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if stripped := _strip_honorific(text):
        stripped_key = _name_key(stripped)
        has_distinct_bare_reference = any(
            other_ref != segment_ref for other_ref in bare_form_segments.get(stripped_key, set())
        )
        if len(stripped_key.split()) >= 2 or has_distinct_bare_reference:
            return stripped
    return text


def _strip_honorific(value: str | None) -> str | None:
    if not value:
        return None
    tokens = value.strip().split()
    if len(tokens) >= 2 and _name_key(tokens[0]) in HONORIFIC_TOKENS:
        stripped = " ".join(tokens[1:]).strip()
        return stripped or None
    return None


def _segment_start_offset(
    segment_ids: list[str], segment_map: dict[str, ObservedSegment]
) -> int | None:
    offsets = [
        segment_map[segment_id].start_offset
        for segment_id in segment_ids
        if segment_id in segment_map
    ]
    return min(offsets) if offsets else None


def _segment_end_offset(
    segment_ids: list[str], segment_map: dict[str, ObservedSegment]
) -> int | None:
    offsets = [
        segment_map[segment_id].end_offset
        for segment_id in segment_ids
        if segment_id in segment_map
    ]
    return max(offsets) if offsets else None


def _candidate_segment_ids(candidate: CharacterCandidate) -> list[str]:
    ids: list[str] = []
    for item in candidate.mention_evidence:
        payload = _evidence(item)
        segment_id = payload.get("segmentId")
        if isinstance(segment_id, str) and segment_id and segment_id not in ids:
            ids.append(segment_id)
    return ids


def _shortlist_payload(shortlist: list[CharacterMatch]) -> list[dict[str, object]]:
    return [
        {
            "characterId": match.character.id,
            "displayName": match.character.display_name,
            "reason": match.reason,
            "score": match.score,
        }
        for match in shortlist
    ]


def _candidate_evidence_graph(candidate: CharacterCandidate) -> dict[str, object]:
    speaker_items = [
        _evidence(item)
        for item in candidate.evidence
        if _evidence(item).get("sources") != ["mention"]
    ]
    mention_items = [_evidence(item) for item in candidate.mention_evidence]
    evidence_items = [*speaker_items, *mention_items]
    sources = sorted(
        {
            source
            for item in evidence_items
            for source in _clean_strings(item.get("sources"))
        }
    )
    if mention_items and "mention" not in sources:
        sources.append("mention")
    start_offsets = [
        int(value)
        for item in evidence_items
        if isinstance((value := item.get("startOffset")), int | float)
    ]
    end_offsets = [
        int(value)
        for item in evidence_items
        if isinstance((value := item.get("endOffset")), int | float)
    ]
    return {
        "canonicalName": candidate.canonical_name or candidate.display_name,
        "aliases": _clean_strings(
            [
                candidate.display_name,
                candidate.canonical_name or "",
                *candidate.aliases,
                *candidate.generated_aliases,
            ]
        ),
        "traits": candidate.traits,
        "relationships": candidate.relationships,
        "speakingStyle": candidate.speaking_style,
        "speakerEvidenceCount": len(speaker_items),
        "mentionEvidenceCount": len(mention_items),
        "confidence": candidate.confidence,
        "sources": sources or [candidate.source],
        "firstSeenOffset": min(start_offsets) if start_offsets else None,
        "lastSeenOffset": max(end_offsets) if end_offsets else None,
    }


def _filter_reasons(
    mention: CharacterMention,
    counts: dict[str, int],
    segment_map: dict[str, ObservedSegment],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    chapter_statuses = {
        segment_map[segment_id].chapter_status
        for segment_id in mention.segment_ids
        if segment_id in segment_map
    }
    if chapter_statuses & {"front_matter", "back_matter"}:
        reasons.append("matter_excluded")
    if mention.entity_type in NON_CHARACTER_ENTITY_TYPES:
        reasons.append(f"entity_type:{mention.entity_type}")
    key = mention.normalized_key
    if key in IGNORED_CHARACTER_NAMES:
        reasons.append("ignored_name")
    if key in GENERIC_ROLE_NAMES and counts.get(key, 0) < 2:
        reasons.append("generic_singleton")
    if any(phrase in key for phrase in NON_CHARACTER_PHRASES):
        reasons.append("document_metadata")
    if _looks_like_heading(mention.surface_name):
        reasons.append("all_caps_heading")
    if _looks_like_punctuation_junk(mention.surface_name):
        reasons.append("punctuation_or_ocr_junk")
    if not _looks_person_like(mention.surface_name):
        reasons.append("not_person_like")
    return bool(reasons), reasons


def _looks_like_heading(value: str) -> bool:
    letters = [character for character in value if character.isalpha()]
    if not letters:
        return False
    uppercase = sum(character.isupper() for character in letters)
    return len(letters) >= 4 and uppercase / len(letters) >= 0.8


def _looks_like_punctuation_junk(value: str) -> bool:
    if not value.strip():
        return True
    punctuation = sum(not character.isalnum() and not character.isspace() for character in value)
    return punctuation / max(len(value), 1) >= 0.25


def _looks_person_like(value: str) -> bool:
    key = _name_key(value)
    if not key:
        return False
    tokens = key.split()
    if not tokens or len(tokens) > 4:
        return False
    if any(token.isdigit() for token in tokens):
        return False
    if tokens[0] in {"chapter", "scene", "page", "part"}:
        return False
    if len(tokens) == 1 and tokens[0] in {"copyright", "publisher", "author"}:
        return False
    return all(re.fullmatch(r"[a-z][a-z'-]*", token) for token in tokens)


def _relationship_overlap(
    left: list[dict[str, object]], right: list[dict[str, object]]
) -> bool:
    left_keys = {
        (_name_key(str(item.get("target") or "")), _name_key(str(item.get("relation") or "")))
        for item in left
    }
    right_keys = {
        (_name_key(str(item.get("target") or "")), _name_key(str(item.get("relation") or "")))
        for item in right
    }
    return bool({key for key in left_keys if key[0] and key[1]} & {key for key in right_keys if key[0] and key[1]})


TITLE_PREFIXES = {
    "captain": "role:captain",
    "capt": "role:captain",
    "dr": "role:doctor",
    "doctor": "role:doctor",
    "prof": "role:professor",
    "professor": "role:professor",
    "sir": "role:nobility",
    "lady": "role:nobility",
    "mrs": "role:nobility",
    "mr": "role:nobility",
    "ms": "role:nobility",
}
HONORIFIC_TOKENS = {"mr", "mrs", "ms", "dr", "captain", "capt", "prof", "professor", "sir", "lady"}
NICKNAME_ALIASES = {
    "elizabeth": ["Liz", "Beth", "Eliza"],
    "liz": ["Elizabeth", "Beth", "Eliza"],
    "beth": ["Elizabeth", "Liz", "Eliza"],
    "eliza": ["Elizabeth", "Liz", "Beth"],
    "william": ["Will", "Bill", "Billy"],
    "will": ["William", "Bill", "Billy"],
    "bill": ["William", "Will", "Billy"],
    "billy": ["William", "Will", "Bill"],
    "robert": ["Rob", "Bob", "Bobby"],
    "rob": ["Robert", "Bob", "Bobby"],
    "bob": ["Robert", "Rob", "Bobby"],
    "bobby": ["Robert", "Rob", "Bob"],
    "margaret": ["Maggie", "Meg"],
    "maggie": ["Margaret", "Meg"],
    "meg": ["Margaret", "Maggie"],
    "katherine": ["Kate", "Katie", "Kat"],
    "catherine": ["Kate", "Katie", "Cat"],
    "kate": ["Katherine", "Catherine", "Katie", "Kat", "Cat"],
    "katie": ["Katherine", "Catherine", "Kate", "Kat", "Cat"],
    "mara": [],
}
AGE_TRAITS = {"young": "age:young", "old": "age:old", "elderly": "age:old"}
ACCENT_TRAITS = {
    "irish": "accent:irish",
    "scottish": "accent:scottish",
    "british": "accent:british",
    "english": "accent:english",
    "american": "accent:american",
    "french": "accent:french",
    "spanish": "accent:spanish",
    "indian": "accent:indian",
}
FEMININE_PRONOUNS = {"she", "her", "hers"}
MASCULINE_PRONOUNS = {"he", "him", "his"}
TITLE_NAME_RE = re.compile(
    r"\b(?:Captain|Capt\.?|Dr\.?|Doctor|Prof\.?|Professor|Mrs\.?|Mr\.?|Ms\.?|Mother|Father|Sister|Brother)\s+[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?"
)
LEADING_NAME_RE = re.compile(
    r"^\s*([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)\s+(?:said|looked|walked|turned|asked|whispered|replied|smiled|laughed|told|stood|sat|nodded|waved)\b"
)


def _alias_candidates(name: str | None) -> list[str]:
    key = _name_key(name)
    if not key:
        return []
    tokens = key.split()
    aliases: list[str] = []
    if len(tokens) > 1 and tokens[0] in TITLE_PREFIXES:
        aliases.append(" ".join(tokens[1:]).title())
    for token in tokens:
        aliases.extend(NICKNAME_ALIASES.get(token, []))
    return aliases


def _extract_traits(name: str | None, texts: list[str]) -> list[str]:
    haystack = " ".join([name or "", *texts]).casefold()
    tokens = set(re.findall(r"[a-z]+", haystack))
    traits: list[str] = []
    name_tokens = _name_key(name).split()
    if name_tokens and name_tokens[0] in TITLE_PREFIXES:
        traits.append(TITLE_PREFIXES[name_tokens[0]])
    for token, trait in AGE_TRAITS.items():
        if token in tokens:
            traits.append(trait)
    for token, trait in ACCENT_TRAITS.items():
        if token in tokens:
            traits.append(trait)
    if tokens & FEMININE_PRONOUNS:
        traits.append("gender:feminine")
    if tokens & MASCULINE_PRONOUNS:
        traits.append("gender:masculine")
    return _clean_strings(traits)


def _clean_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        key = _name_key(text)
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
    return cleaned


def _trait_value(traits: list[str], prefix: str) -> str | None:
    marker = f"{prefix}:"
    for trait in traits:
        if trait.casefold().startswith(marker):
            value = trait.split(":", 1)[1].strip().casefold()
            return value or None
    return None


def _speech_style_strings(value: object) -> list[str]:
    payload = _speech_style_object(value)
    strings = [
        f"register:{payload['register']}" if payload["register"] != "unknown" else "",
        f"verbosity:{payload['verbosity']}" if payload["verbosity"] != "unknown" else "",
        f"accent:{payload['accentHint']}" if payload["accentHint"] != "none" else "",
        *cast(list[str], payload["tics"]),
    ]
    return _clean_strings(strings)


def _speech_style_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {
            "register": "unknown",
            "verbosity": "unknown",
            "accentHint": "none",
            "tics": [],
        }
    payload = cast(dict[str, object], value)
    return {
        "register": str(payload.get("register") or "unknown").strip().casefold()
        or "unknown",
        "verbosity": str(payload.get("verbosity") or "unknown").strip().casefold()
        or "unknown",
        "accentHint": str(payload.get("accentHint") or "none").strip().casefold()
        or "none",
        "tics": _clean_strings(payload.get("tics")),
    }


def _speech_style_payload(styles: list[str]) -> dict[str, object]:
    register = _trait_value(styles, "register") or "unknown"
    verbosity = _trait_value(styles, "verbosity") or "unknown"
    accent = _trait_value(styles, "accent") or "none"
    tics = [
        style
        for style in styles
        if not any(
            style.casefold().startswith(f"{prefix}:")
            for prefix in ("register", "verbosity", "accent")
        )
    ]
    return {
        "register": register,
        "verbosity": verbosity,
        "accentHint": accent,
        "tics": _clean_strings(tics),
    }


def _name_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _ignored_name(value: str | None) -> bool:
    return _name_key(value) in IGNORED_CHARACTER_NAMES


def _soft_name_match(left: str, right: str) -> bool:
    if len(left) < 4 or len(right) < 4:
        return False
    if left in right or right in left:
        return True
    if _nickname_match(left, right):
        return True
    if _fuzzy_name_match(left, right):
        return True
    if _honorific_surname_match(left, right):
        return True
    return False


def _honorific_surname_match(left: str, right: str) -> bool:
    left_tokens = left.split()
    right_tokens = right.split()
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return False
    if left_tokens[-1] != right_tokens[-1]:
        return False
    return bool(
        (left_tokens[0] in HONORIFIC_TOKENS and right_tokens[0] not in HONORIFIC_TOKENS)
        or (right_tokens[0] in HONORIFIC_TOKENS and left_tokens[0] not in HONORIFIC_TOKENS)
    )


def _nickname_match(left: str, right: str) -> bool:
    left_tokens = left.split()
    right_tokens = right.split()
    for left_token in left_tokens:
        aliases = {_name_key(alias) for alias in NICKNAME_ALIASES.get(left_token, [])}
        if any(right_token in aliases for right_token in right_tokens):
            return True
    for right_token in right_tokens:
        aliases = {_name_key(alias) for alias in NICKNAME_ALIASES.get(right_token, [])}
        if any(left_token in aliases for left_token in left_tokens):
            return True
    return False


def _fuzzy_name_match(left: str, right: str) -> bool:
    left_tokens = left.split()
    right_tokens = right.split()
    if len(left_tokens) != len(right_tokens):
        return False
    if not left_tokens or not right_tokens:
        return False
    distances = [
        _edit_distance(left_token, right_token)
        for left_token, right_token in zip(left_tokens, right_tokens, strict=True)
    ]
    return bool(distances) and sum(distances) <= 1 and max(len(left), len(right)) >= 6


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _trait_conflicts(existing: object, candidate: object) -> list[str]:
    existing_by_namespace = _traits_by_namespace(_clean_strings(existing))
    candidate_by_namespace = _traits_by_namespace(_clean_strings(candidate))
    conflicts: list[str] = []
    for namespace, candidate_values in candidate_by_namespace.items():
        existing_values = existing_by_namespace.get(namespace)
        if not existing_values:
            continue
        different = sorted(candidate_values - existing_values)
        if different:
            conflicts.append(f"{namespace}:{'/'.join(sorted(existing_values))}->{'/'.join(different)}")
    return conflicts


def _traits_by_namespace(traits: list[str]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for trait in traits:
        namespace, separator, value = trait.partition(":")
        if not separator or not namespace or not value:
            continue
        grouped.setdefault(namespace, set()).add(value)
    return grouped


def _evidence(payload: str | None) -> dict[str, object]:
    try:
        loaded = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], loaded if isinstance(loaded, dict) else {})


def _json_load(payload: str | None) -> object:
    try:
        return json.loads(payload or "[]")
    except json.JSONDecodeError:
        return []


def _clamp_float(value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, (int, float, str)):
        try:
            numeric = float(value)
        except ValueError:
            numeric = minimum
    else:
        numeric = minimum
    return min(max(numeric, minimum), maximum)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _relationship_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "").strip()
        relation = str(item.get("relation") or "").strip()
        if not target or not relation:
            continue
        rows.append(
            {
                "target": target,
                "relation": relation,
                "confidence": _clamp_float(item.get("confidence"), 0.0, 1.0),
            }
        )
    return rows


def _merge_relationships(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        target = _name_key(str(row.get("target") or ""))
        relation = _name_key(str(row.get("relation") or ""))
        if not target or not relation:
            continue
        key = (target, relation)
        confidence = _clamp_float(row.get("confidence"), 0.0, 1.0)
        candidate = {
            "target": str(row.get("target") or "").strip(),
            "relation": str(row.get("relation") or "").strip(),
            "confidence": confidence,
        }
        current = merged.get(key)
        if not current or confidence >= _clamp_float(current.get("confidence"), 0.0, 1.0):
            merged[key] = candidate
    return list(merged.values())


def _merge_character_notes(existing: str | None, candidate: CharacterCandidate) -> str:
    try:
        payload = json.loads(existing or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["source"] = payload.get("source") or "cast_graph"
    payload["evidenceGraph"] = _candidate_evidence_graph(candidate)
    payload["evidence"] = _clean_strings([*payload.get("evidence", []), *candidate.evidence])
    payload["mentionEvidence"] = _clean_strings(
        [*payload.get("mentionEvidence", []), *candidate.mention_evidence]
    )
    payload["relationships"] = _merge_relationships(
        [*_relationship_rows(payload.get("relationships")), *candidate.relationships]
    )
    payload["speakingStyle"] = _clean_strings(
        [*payload.get("speakingStyle", []), *candidate.speaking_style]
    )
    return json.dumps(payload, sort_keys=True)


def _can_propose_cast(name: str | None) -> bool:
    key = _name_key(name)
    return bool(key and key not in IGNORED_CHARACTER_NAMES)


def _unique_active_character(
    characters: list[CharacterRecord], name: str | None
) -> CharacterRecord | None:
    key = _name_key(name)
    if not key:
        return None
    matches = [
        character
        for character in characters
        if not character.merged_into_character_id
        and key in {
            _name_key(item)
            for item in [
                character.display_name,
                character.canonical_name or "",
                *_clean_strings(_json_load(character.aliases_json)),
            ]
        }
    ]
    return matches[0] if len(matches) == 1 else None
