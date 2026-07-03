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
class CharacterIndex:
    by_name: dict[str, CharacterRecord] = field(default_factory=dict)

    def exact(self, candidate: CharacterCandidate) -> CharacterRecord | None:
        for name in [candidate.display_name, candidate.canonical_name or "", *candidate.aliases]:
            match = self.by_name.get(_name_key(name))
            if match:
                return match
        return None

    def possible_matches(self, candidate: CharacterCandidate) -> list[CharacterRecord]:
        candidate_keys = {
            _name_key(name)
            for name in [candidate.display_name, candidate.canonical_name or "", *candidate.aliases]
            if _name_key(name)
        }
        matches: dict[str, CharacterRecord] = {}
        for key, character in self.by_name.items():
            if key in candidate_keys:
                matches[character.id] = character
                continue
            if any(_soft_name_match(key, candidate_key) for candidate_key in candidate_keys):
                matches[character.id] = character
        return list(matches.values())


class CastDiscoveryService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

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
        exact = index.exact(candidate)
        if exact:
            self._merge_aliases(exact, candidate)
            return
        possible = index.possible_matches(candidate)
        if possible:
            reason = (
                "Multiple existing characters could match."
                if len(possible) > 1
                else "A similar existing character may already represent this candidate."
            )
            self._create_ambiguous_issue(project_id, candidate, reason, possible)
            return
        if decision and decision.action == "match_existing" and decision.target_name:
            target = index.by_name.get(_name_key(decision.target_name))
            if target:
                self._merge_aliases(target, candidate, decision.aliases)
                return
        if decision and decision.action == "ambiguous":
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
                aliases=[*candidate.aliases, *(decision.aliases if decision else [])],
                role=candidate.role_guess,
                confidence=candidate.confidence,
                notes=json.dumps(
                    {
                        "source": candidate.source,
                        "evidenceGraph": evidence_graph,
                        "evidence": candidate.evidence,
                        "decision": decision.reason if decision else "deterministic_unique_candidate",
                    },
                    sort_keys=True,
                ),
                canonical_name=candidate.canonical_name,
                traits=[],
                first_seen_source_id=source_id,
                first_seen_chapter_id=candidate.first_seen_chapter_id,
                first_seen_segment_id=candidate.first_seen_segment_id,
            )
            for name in _character_names(record):
                key = _name_key(name)
                if key:
                    index.by_name[key] = record
            return
        self._create_low_confidence_issue(project_id, candidate)

    def _merge_aliases(
        self,
        character: CharacterRecord,
        candidate: CharacterCandidate,
        extra_aliases: list[str] | None = None,
    ) -> None:
        if character.user_locked:
            return
        aliases = _clean_strings(json.loads(character.aliases_json or "[]"))
        additions = [
            candidate.display_name,
            *(candidate.aliases or []),
            *(extra_aliases or []),
        ]
        merged = _clean_strings([*aliases, *additions])
        if merged != aliases:
            self.container.casting.update_character(character.id, aliases=merged)

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
                "displayName": candidate.display_name,
                "aliases": candidate.aliases,
                "confidence": candidate.confidence,
                "source": candidate.source,
                "reason": reason,
                "evidence": candidate.evidence,
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
                "source": candidate.source,
                "reason": "Candidate confidence was too low.",
                "evidence": candidate.evidence,
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
            for name in _character_names(character):
                key = _name_key(name)
                if key:
                    index.by_name[key] = character
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
                f"- {candidate.display_name}; aliases={', '.join(candidate.aliases)}; "
                f"confidence={candidate.confidence:.2f}; evidence={' | '.join(candidate.evidence[:2])}"
            )
            for candidate in candidates
        )
        return (
            "Verify cast candidates against existing Character Bible records and prior candidates. "
            "Choose action match_existing, merge_candidate, create_new, or ambiguous. "
            "Use match_existing for canonical names or aliases that already exist. "
            "Use create_new only when a candidate is high-confidence and unique. "
            "Return only JSON matching the schema.\n\n"
            f"Existing Character Bible records:\n{character_lines or 'None'}\n\n"
            f"Candidates:\n{candidate_lines}"
        )

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
            existing.evidence = _clean_strings([*existing.evidence, *candidate.evidence])[:5]
            existing.confidence = max(existing.confidence, candidate.confidence)
            if existing.source != candidate.source:
                existing.source = "deterministic_parser+llm_cast_discovery"
        return list(by_key.values())


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
    names = [character.display_name, character.canonical_name or ""]
    names.extend(_clean_strings(json.loads(character.aliases_json or "[]")))
    return names


def _candidate_evidence_graph(candidate: CharacterCandidate) -> dict[str, object]:
    evidence_items = [_evidence(item) for item in candidate.evidence]
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
        "aliases": _clean_strings([candidate.display_name, candidate.canonical_name or "", *candidate.aliases]),
        "speakerEvidenceCount": len(candidate.evidence),
        "mentionEvidenceCount": 0,
        "firstSeenOffset": min(offsets) if offsets else None,
        "lastSeenOffset": max(end_offsets) if end_offsets else None,
        "confidence": candidate.confidence,
        "sources": sources or [candidate.source],
    }


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
    left_tokens = left.split()
    right_tokens = right.split()
    if len(left_tokens) >= 2 and len(right_tokens) >= 2 and left_tokens[-1] == right_tokens[-1]:
        return left_tokens[0] == right_tokens[0] and left_tokens[0] in {"dr", "captain", "capt", "prof"}
    return False


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
