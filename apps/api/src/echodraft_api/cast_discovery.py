from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import cast

from echodraft_db.models import ChapterRecord, CharacterRecord, SceneRecord, SegmentRecord
from echodraft_domain import LlmExtractionRequest
from sqlalchemy import select

from .container import AppContainer
from .local_llm import LocalLlmService
from .structure import DEFAULT_REFINEMENT_MODEL, DEFAULT_REFINEMENT_MODEL_KEY

CAST_DISCOVERY_BATCH_CHARS = 5000
CAST_DISCOVERY_BATCH_SEGMENTS = 12
AUTO_CREATE_CONFIDENCE = 0.72
CAST_DISCOVERY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "displayName": {"type": "string"},
                    "canonicalName": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "firstSeenSegmentId": {"type": "string"},
                    "roleGuess": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "displayName",
                    "aliases",
                    "firstSeenSegmentId",
                    "roleGuess",
                    "confidence",
                    "evidence",
                ],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["characters", "warnings"],
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
                    "targetName": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["displayName", "action", "targetName", "confidence", "reason"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decisions", "warnings"],
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


@dataclass(frozen=True)
class ObservedSegment:
    id: str
    chapter_id: str
    text: str
    segment_type: str
    start_offset: int
    end_offset: int
    speaker_candidate: str | None
    speaker_confidence: float
    parser_evidence: dict[str, object]


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
    generated_aliases: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return _name_key(self.display_name)


@dataclass(frozen=True)
class MergeDecision:
    action: str
    target_name: str | None
    aliases: list[str]
    confidence: float
    reason: str


@dataclass
class NameIndexEntry:
    character: CharacterRecord
    source: str


@dataclass(frozen=True)
class CharacterMatch:
    character: CharacterRecord
    reason: str


@dataclass
class CharacterIndex:
    by_name: dict[str, list[NameIndexEntry]] = field(default_factory=dict)

    def add_character(self, character: CharacterRecord) -> None:
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
                reason = "generated_alias" if source == "generated_alias" else entry.source
                existing = matches.get(entry.character.id)
                if not existing or _match_reason_priority(reason) > _match_reason_priority(existing.reason):
                    matches[entry.character.id] = CharacterMatch(entry.character, reason)
        return list(matches.values())

    def first_by_name(self, name: str | None) -> CharacterRecord | None:
        key = _name_key(name)
        if not key:
            return None
        entries = self.by_name.get(key, [])
        return entries[0].character if len(entries) == 1 else None

    def possible_matches(self, candidate: CharacterCandidate) -> list[CharacterRecord]:
        candidate_keys = {
            _name_key(name)
            for name, _source in _candidate_index_names(candidate)
            if _name_key(name)
        }
        matches: dict[str, CharacterRecord] = {}
        for key, entries in self.by_name.items():
            if key in candidate_keys:
                for entry in entries:
                    matches[entry.character.id] = entry.character
                continue
            if any(_soft_name_match(key, candidate_key) for candidate_key in candidate_keys):
                for entry in entries:
                    matches[entry.character.id] = entry.character
        return list(matches.values())


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
        candidate = CharacterCandidate(
            display_name=speaker_name,
            canonical_name=speaker_name,
            aliases=[],
            first_seen_segment_id=segment_id,
            first_seen_chapter_id=chapter_id,
            evidence=[
                json.dumps(
                    {
                        "textPreview": text[:220],
                        "sources": ["speaker_attribution"],
                        "confidence": confidence,
                        "segmentId": segment_id,
                        "chapterId": chapter_id,
                    },
                    sort_keys=True,
                )
            ],
            role_guess="supporting",
            confidence=confidence,
            source="speaker_attribution",
            traits=_extract_traits(speaker_name, [text]),
            generated_aliases=_alias_candidates(speaker_name),
        )
        index = self._character_index(project_id)
        self._apply_candidate(project_id, None, candidate, None, index)
        return _unique_active_character(self.container.casting.characters(project_id), speaker_name)

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
        segments = self._segments(project_id)
        candidates = self._deterministic_candidates(segments)
        ready = use_local_llm and self._local_llm_ready()
        if ready:
            candidates.extend(self._llm_candidates(project_id, segments, job_id))
        candidates = self._consolidate(candidates)
        candidates = self._with_mention_evidence(candidates, segments)
        decisions = self._llm_merge_decisions(project_id, candidates, job_id) if ready else {}
        index = self._character_index(project_id)
        for candidate in candidates:
            self._apply_candidate(project_id, source_id, candidate, decisions.get(candidate.key), index)
        return self.container.casting.characters(project_id)

    def _deterministic_candidates(
        self, segments: list[ObservedSegment]
    ) -> list[CharacterCandidate]:
        candidates: list[CharacterCandidate] = []
        for segment in segments:
            if not segment.speaker_candidate or _ignored_name(segment.speaker_candidate):
                continue
            sources = _clean_strings(segment.parser_evidence.get("sources"))
            speaker_rule = str(segment.parser_evidence.get("speakerRule") or "speaker_candidate")
            production_type = str(segment.parser_evidence.get("productionType") or segment.segment_type)
            candidates.append(
                CharacterCandidate(
                    display_name=segment.speaker_candidate,
                    canonical_name=segment.speaker_candidate,
                    aliases=[],
                    first_seen_segment_id=segment.id,
                    first_seen_chapter_id=segment.chapter_id,
                    evidence=[
                        json.dumps(
                            {
                                "textPreview": segment.text[:220],
                                "speakerRule": speaker_rule,
                                "productionType": production_type,
                                "sources": sources or ["structure_parser"],
                                "confidence": segment.speaker_confidence,
                                "segmentId": segment.id,
                                "chapterId": segment.chapter_id,
                                "startOffset": segment.start_offset,
                                "endOffset": segment.end_offset,
                            },
                            sort_keys=True,
                        )
                    ],
                    role_guess="supporting",
                    confidence=segment.speaker_confidence,
                    source="+".join(sources) if sources else "structure_parser",
                    traits=_extract_traits(segment.speaker_candidate, [segment.text]),
                    generated_aliases=_alias_candidates(segment.speaker_candidate),
                )
            )
        return candidates

    def _llm_candidates(
        self, project_id: str, segments: list[ObservedSegment], job_id: str | None
    ) -> list[CharacterCandidate]:
        llm = LocalLlmService(self.container)
        candidates: list[CharacterCandidate] = []
        segment_map = {segment.id: segment for segment in segments}
        batches = list(_segment_batches(segments))
        for index, batch in enumerate(batches, 1):
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "llm_cast_discovery",
                        "current": index,
                        "total": len(batches),
                        "message": "Extracting observed cast candidates with local Ollama.",
                    },
                )
            try:
                result = llm.extract(
                    project_id,
                    LlmExtractionRequest(
                        model=DEFAULT_REFINEMENT_MODEL,
                        task="cast_discovery",
                        schema=CAST_DISCOVERY_SCHEMA,
                        prompt=self._cast_prompt(batch),
                    ),
                    job_id,
                )
            except ValueError as error:
                self.container.review.create_issue(
                    project_id=project_id,
                    category="cast_discovery",
                    severity="warning",
                    title="LLM cast discovery skipped a segment window",
                    description="Local Ollama failed while extracting cast candidates; deterministic hints were kept.",
                    metadata={"error": str(error)[:500], "segmentIds": [segment.id for segment in batch]},
                    dedupe_key=f"cast-discovery-llm:{project_id}:{batch[0].id}",
                )
                continue
            raw_candidates = result.result.get("characters")
            if not isinstance(raw_candidates, list):
                continue
            for item in raw_candidates:
                if not isinstance(item, dict):
                    continue
                candidate = self._candidate_from_llm(cast(dict[str, object], item), segment_map)
                if candidate:
                    candidates.append(candidate)
        return candidates

    def _candidate_from_llm(
        self, payload: dict[str, object], segment_map: dict[str, ObservedSegment]
    ) -> CharacterCandidate | None:
        display_name = str(payload.get("displayName") or "").strip()
        if not display_name or _ignored_name(display_name):
            return None
        first_seen_segment_id = str(payload.get("firstSeenSegmentId") or "").strip()
        first_seen = segment_map.get(first_seen_segment_id) or next(iter(segment_map.values()), None)
        aliases = _clean_strings(payload.get("aliases"))
        canonical_name = str(payload.get("canonicalName") or display_name).strip() or display_name
        evidence = _clean_strings(payload.get("evidence"))
        generated_aliases = _alias_candidates(display_name)
        return CharacterCandidate(
            display_name=display_name,
            canonical_name=canonical_name,
            aliases=[alias for alias in aliases if _name_key(alias) != _name_key(display_name)],
            first_seen_segment_id=first_seen.id if first_seen else None,
            first_seen_chapter_id=first_seen.chapter_id if first_seen else None,
            evidence=evidence[:5],
            role_guess=_role_type(str(payload.get("roleGuess") or "supporting")),
            confidence=_clamp_float(payload.get("confidence"), 0.0, 1.0),
            source="llm_cast_discovery",
            traits=_extract_traits(display_name, evidence),
            generated_aliases=generated_aliases,
        )

    def _llm_merge_decisions(
        self,
        project_id: str,
        candidates: list[CharacterCandidate],
        job_id: str | None,
    ) -> dict[str, MergeDecision]:
        if not candidates:
            return {}
        llm = LocalLlmService(self.container)
        try:
            result = llm.extract(
                project_id,
                LlmExtractionRequest(
                    model=DEFAULT_REFINEMENT_MODEL,
                    task="cast_merge_verification",
                    schema=CAST_MERGE_SCHEMA,
                    prompt=self._merge_prompt(project_id, candidates),
                ),
                job_id,
            )
        except ValueError as error:
            self.container.review.create_issue(
                project_id=project_id,
                category="cast_discovery",
                severity="warning",
                title="LLM cast merge verification was skipped",
                description="Local Ollama failed while checking whether cast candidates should merge.",
                metadata={"error": str(error)[:500]},
                dedupe_key=f"cast-merge-llm:{project_id}",
            )
            return {}
        raw_decisions = result.result.get("decisions")
        if not isinstance(raw_decisions, list):
            return {}
        decisions: dict[str, MergeDecision] = {}
        for item in raw_decisions:
            if not isinstance(item, dict):
                continue
            payload = cast(dict[str, object], item)
            display_name = str(payload.get("displayName") or "").strip()
            key = _name_key(display_name)
            if not key:
                continue
            decisions[key] = MergeDecision(
                action=str(payload.get("action") or "ambiguous").strip(),
                target_name=str(payload.get("targetName") or "").strip() or None,
                aliases=_clean_strings(payload.get("aliases")),
                confidence=_clamp_float(payload.get("confidence"), 0.0, 1.0),
                reason=str(payload.get("reason") or "").strip(),
            )
        return decisions

    def _apply_candidate(
        self,
        project_id: str,
        source_id: str | None,
        candidate: CharacterCandidate,
        decision: MergeDecision | None,
        index: CharacterIndex,
    ) -> None:
        exact_matches = [
            match
            for match in index.exact(candidate)
            if not self._pair_rejected(
                project_id, candidate.display_name, match.character.display_name
            )
        ]
        if exact_matches:
            if len(exact_matches) > 1:
                self._create_ambiguous_issue(
                    project_id,
                    candidate,
                    "Multiple existing characters share this candidate name or alias.",
                    [match.character for match in exact_matches],
                )
                return
            exact = exact_matches[0]
            conflicts = _trait_conflicts(
                json.loads(exact.character.traits_json or "[]"), candidate.traits
            )
            if exact.reason == "generated_alias":
                self._create_ambiguous_issue(
                    project_id,
                    candidate,
                    "A generated alias matched an existing character and needs review.",
                    [exact.character],
                )
                return
            if conflicts:
                self._create_ambiguous_issue(
                    project_id,
                    candidate,
                    "Existing character has conflicting observed traits: "
                    + ", ".join(conflicts),
                    [exact.character],
                )
                return
            updated = self._merge_aliases(exact.character, candidate)
            if updated:
                index.add_character(updated)
            return
        possible = [
            match
            for match in index.possible_matches(candidate)
            if not self._pair_rejected(project_id, candidate.display_name, match.display_name)
        ]
        if possible:
            reason = (
                "Multiple existing characters could match."
                if len(possible) > 1
                else "A similar existing character may already represent this candidate."
            )
            self._create_ambiguous_issue(project_id, candidate, reason, possible)
            return
        if decision and decision.action == "match_existing" and decision.target_name:
            target = index.first_by_name(decision.target_name)
            if target and not self._pair_rejected(
                project_id, candidate.display_name, target.display_name
            ):
                updated = self._merge_aliases(target, candidate, decision.aliases)
                if updated:
                    index.add_character(updated)
                return
        if (
            decision
            and decision.action == "ambiguous"
            and not (
                decision.target_name
                and self._pair_rejected(
                    project_id, candidate.display_name, decision.target_name
                )
            )
        ):
            self._create_ambiguous_issue(project_id, candidate, decision.reason)
            return
        if decision and decision.action == "merge_candidate":
            self._create_ambiguous_issue(
                project_id,
                candidate,
                decision.reason or "Candidate should merge with another candidate before creation.",
            )
            return
        if candidate.confidence >= AUTO_CREATE_CONFIDENCE:
            evidence_graph = _candidate_evidence_graph(candidate)
            record = self.container.casting.create_character(
                project_id=project_id,
                name=candidate.display_name,
                aliases=[
                    *candidate.aliases,
                    *candidate.generated_aliases,
                    *(decision.aliases if decision else []),
                ],
                role=candidate.role_guess,
                confidence=candidate.confidence,
                notes=json.dumps(
                    {
                        "source": candidate.source,
                        "evidenceGraph": evidence_graph,
                        "evidence": candidate.evidence,
                        "mentionEvidence": candidate.mention_evidence,
                        "decision": decision.reason if decision else "deterministic_unique_candidate",
                    },
                    sort_keys=True,
                ),
                canonical_name=candidate.canonical_name,
                traits=candidate.traits,
                first_seen_source_id=source_id,
                first_seen_chapter_id=candidate.first_seen_chapter_id,
                first_seen_segment_id=candidate.first_seen_segment_id,
            )
            index.add_character(record)
            return
        self._create_low_confidence_issue(project_id, candidate)

    def _merge_aliases(
        self,
        character: CharacterRecord,
        candidate: CharacterCandidate,
        extra_aliases: list[str] | None = None,
    ) -> CharacterRecord | None:
        if character.user_locked:
            return character
        aliases = _clean_strings(json.loads(character.aliases_json or "[]"))
        traits = _clean_strings(json.loads(character.traits_json or "[]"))
        additions = [
            candidate.display_name,
            *(candidate.aliases or []),
            *(candidate.generated_aliases or []),
            *(extra_aliases or []),
        ]
        merged = _clean_strings([*aliases, *additions])
        merged_traits = _clean_strings([*traits, *candidate.traits])
        if merged != aliases or merged_traits != traits:
            return self.container.casting.update_character(
                character.id, aliases=merged, traits=merged_traits
            )
        return character

    def _pair_rejected(self, project_id: str, name_a: str, name_b: str) -> bool:
        """True when a reviewer already ruled this name pair is NOT a duplicate."""
        return self.container.cast_merge_decisions.is_rejected(project_id, name_a, name_b)

    def _create_ambiguous_issue(
        self,
        project_id: str,
        candidate: CharacterCandidate,
        reason: str,
        possible_matches: list[CharacterRecord] | None = None,
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
                "possibleMatches": [match.display_name for match in matches],
                "possibleMatchIds": [match.id for match in matches],
                "displayName": candidate.display_name,
                "aliases": _clean_strings([*candidate.aliases, *candidate.generated_aliases]),
                "generatedAliases": candidate.generated_aliases,
                "traits": candidate.traits,
                "confidence": candidate.confidence,
                "source": candidate.source,
                "reason": reason,
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
        self, project_id: str, candidate: CharacterCandidate
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
                "confidence": candidate.confidence,
                "traits": candidate.traits,
                "source": candidate.source,
                "reason": "Candidate confidence was too low.",
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
                select(SegmentRecord, SceneRecord.chapter_id)
                .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                .where(ChapterRecord.project_id == project_id)
                .order_by(ChapterRecord.order_index, SceneRecord.order_index, SegmentRecord.order_index)
            )
            return [
                ObservedSegment(
                    id=segment.id,
                    chapter_id=chapter_id,
                    text=segment.text_content,
                    segment_type=segment.segment_type,
                    start_offset=segment.start_offset,
                    end_offset=segment.end_offset,
                    speaker_candidate=segment.speaker_candidate,
                    speaker_confidence=segment.speaker_confidence,
                    parser_evidence=_evidence(segment.parser_evidence_json),
                )
                for segment, chapter_id in rows
            ]

    def _character_index(self, project_id: str) -> CharacterIndex:
        index = CharacterIndex()
        for character in self.container.casting.characters(project_id):
            if character.merged_into_character_id:
                continue
            index.add_character(character)
        return index

    def _local_llm_ready(self) -> bool:
        installation = self.container.local_ai.installation(DEFAULT_REFINEMENT_MODEL_KEY)
        return bool(installation and installation.status == "installed")

    @staticmethod
    def _cast_prompt(batch: list[ObservedSegment]) -> str:
        segment_lines = "\n".join(
            (
                f"- {segment.id} [{segment.segment_type}] "
                f"speakerHint={segment.speaker_candidate or ''}: "
                f"{segment.text[:700].replace(chr(10), ' ')}"
            )
            for segment in batch
        )
        return (
            "Extract only observed audiobook cast candidates from these bounded manuscript "
            "segments. Do not infer characters that are not present in the text. Include speaker "
            "labels, named dialogue participants, and named characters mentioned in nearby narration. "
            "Use exact segment IDs for firstSeenSegmentId. Return only JSON matching the schema.\n\n"
            f"Segments:\n{segment_lines}"
        )

    def _merge_prompt(self, project_id: str, candidates: list[CharacterCandidate]) -> str:
        characters = self.container.casting.characters(project_id)
        character_lines = "\n".join(
            (
                f"- {character.display_name}; canonical={character.canonical_name or ''}; "
                f"aliases={', '.join(_clean_strings(json.loads(character.aliases_json or '[]')))}"
            )
            for character in characters
            if not character.merged_into_character_id
        )
        candidate_lines = "\n".join(
            (
                f"- {candidate.display_name}; "
                f"aliases={', '.join(_clean_strings([*candidate.aliases, *candidate.generated_aliases]))}; "
                f"confidence={candidate.confidence:.2f}; evidence={' | '.join(candidate.evidence[:2])}"
            )
            for candidate in candidates
        )
        decision_block = self._merge_decision_block(project_id)
        return (
            "Verify cast candidates against existing Character Bible records and prior candidates. "
            "Choose action match_existing, merge_candidate, create_new, or ambiguous. "
            "Use match_existing for canonical names or aliases that already exist. "
            "Use create_new only when a candidate is high-confidence and unique. "
            "Return only JSON matching the schema.\n\n"
            f"{decision_block}"
            f"Existing Character Bible records:\n{character_lines or 'None'}\n\n"
            f"Candidates:\n{candidate_lines}"
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

    @staticmethod
    def _consolidate(candidates: list[CharacterCandidate]) -> list[CharacterCandidate]:
        by_key: dict[str, CharacterCandidate] = {}
        for candidate in candidates:
            if not candidate.key:
                continue
            existing = by_key.get(candidate.key)
            if not existing:
                by_key[candidate.key] = candidate
                continue
            existing.aliases = _clean_strings([*existing.aliases, *candidate.aliases])
            existing.generated_aliases = _clean_strings(
                [*existing.generated_aliases, *candidate.generated_aliases]
            )
            existing.evidence = _clean_strings([*existing.evidence, *candidate.evidence])[:5]
            existing.mention_evidence = _clean_strings(
                [*existing.mention_evidence, *candidate.mention_evidence]
            )
            existing.traits = _clean_strings([*existing.traits, *candidate.traits])
            existing.confidence = max(existing.confidence, candidate.confidence)
            if existing.source != candidate.source:
                existing.source = "deterministic_parser+llm_cast_discovery"
        return list(by_key.values())

    @staticmethod
    def _with_mention_evidence(
        candidates: list[CharacterCandidate], segments: list[ObservedSegment]
    ) -> list[CharacterCandidate]:
        for candidate in candidates:
            candidate_keys = _candidate_name_keys(candidate)
            mention_evidence = list(candidate.mention_evidence)
            for segment in segments:
                if _name_key(segment.speaker_candidate) in candidate_keys:
                    candidate.traits = _clean_strings(
                        [*candidate.traits, *_extract_traits(candidate.display_name, [segment.text])]
                    )
                    continue
                if _role_mentioned(candidate, segment.text):
                    candidate.traits = _clean_strings(
                        [*candidate.traits, *_extract_traits(candidate.display_name, [segment.text])]
                    )
                for start, end, matched_text in _mention_spans(candidate, segment.text):
                    absolute_start = segment.start_offset + start
                    absolute_end = segment.start_offset + end
                    mention_evidence.append(
                        json.dumps(
                            {
                                "textPreview": segment.text[:220],
                                "matchedText": matched_text,
                                "sources": ["mention"],
                                "confidence": min(candidate.confidence, 0.74),
                                "segmentId": segment.id,
                                "chapterId": segment.chapter_id,
                                "startOffset": absolute_start,
                                "endOffset": absolute_end,
                            },
                            sort_keys=True,
                        )
                    )
                    candidate.traits = _clean_strings(
                        [*candidate.traits, *_extract_traits(candidate.display_name, [segment.text])]
                    )
            candidate.mention_evidence = _clean_strings(mention_evidence)
        return candidates


def _segment_batches(segments: list[ObservedSegment]) -> list[list[ObservedSegment]]:
    batches: list[list[ObservedSegment]] = []
    current: list[ObservedSegment] = []
    current_chars = 0
    for segment in segments:
        length = len(segment.text)
        if (
            current
            and (current_chars + length > CAST_DISCOVERY_BATCH_CHARS)
            or len(current) >= CAST_DISCOVERY_BATCH_SEGMENTS
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += length
    if current:
        batches.append(current)
    return batches


def _character_names(character: CharacterRecord) -> list[str]:
    return [name for name, _source in _character_index_names(character)]


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
        and key in {_name_key(item) for item in _character_names(character)}
    ]
    return matches[0] if len(matches) == 1 else None


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


def _match_reason_priority(reason: str) -> int:
    if reason in {"display_name", "canonical_name"}:
        return 3
    if reason in {"persisted_alias", "observed_alias"}:
        return 2
    if reason == "generated_alias":
        return 1
    return 0


def _candidate_name_keys(candidate: CharacterCandidate) -> set[str]:
    return {
        key
        for name, _source in _candidate_index_names(candidate)
        if (key := _name_key(name))
    }


def _mention_spans(candidate: CharacterCandidate, text: str) -> list[tuple[int, int, str]]:
    names = _clean_strings(
        [
            candidate.display_name,
            candidate.canonical_name or "",
            *candidate.aliases,
            *candidate.generated_aliases,
        ]
    )
    spans: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for name in sorted(names, key=len, reverse=True):
        pattern = re.compile(rf"(?<![\w'-]){re.escape(name)}(?![\w'-])", re.IGNORECASE)
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied):
                continue
            spans.append((start, end, text[start:end]))
            occupied.append((start, end))
    return sorted(spans)


def _candidate_evidence_graph(candidate: CharacterCandidate) -> dict[str, object]:
    speaker_items = [_evidence(item) for item in candidate.evidence]
    mention_items = [_evidence(item) for item in candidate.mention_evidence]
    evidence_items = [*speaker_items, *mention_items]
    offsets = [
        start
        for item in evidence_items
        if isinstance((start := item.get("startOffset")), int)
    ]
    end_offsets = [
        end
        for item in evidence_items
        if isinstance((end := item.get("endOffset")), int)
    ]
    sources = sorted(
        {
            source
            for item in evidence_items
            for source in _clean_strings(item.get("sources"))
        }
    )
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
        "speakerEvidenceCount": len(speaker_items),
        "mentionEvidenceCount": len(mention_items),
        "firstSeenOffset": min(offsets) if offsets else None,
        "lastSeenOffset": max(end_offsets) if end_offsets else None,
        "confidence": candidate.confidence,
        "sources": sources or [candidate.source],
    }


TITLE_PREFIXES = {
    "captain": "role:captain",
    "capt": "role:captain",
    "dr": "role:doctor",
    "doctor": "role:doctor",
    "prof": "role:professor",
    "professor": "role:professor",
    "sir": "role:nobility",
    "lady": "role:nobility",
}
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


def _role_mentioned(candidate: CharacterCandidate, text: str) -> bool:
    tokens = _name_key(candidate.display_name).split()
    role_tokens = {token for token in tokens if token in TITLE_PREFIXES}
    if not role_tokens:
        return False
    text_tokens = set(re.findall(r"[a-z]+", text.casefold()))
    return bool(role_tokens & text_tokens)


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


def _role_type(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized in {"major", "supporting", "minor", "narrator"}:
        return normalized
    return "supporting"


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
    left_tokens = left.split()
    right_tokens = right.split()
    if len(left_tokens) >= 2 and len(right_tokens) >= 2 and left_tokens[-1] == right_tokens[-1]:
        return left_tokens[0] == right_tokens[0] and left_tokens[0] in {"dr", "captain", "capt", "prof"}
    return False


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


def _clamp_float(value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, (int, float, str)):
        try:
            numeric = float(value)
        except ValueError:
            numeric = minimum
    else:
        numeric = minimum
    return min(max(numeric, minimum), maximum)
