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
from .cast_discovery import CastDiscoveryService
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
SPEECH_VERBS = {
    "answered",
    "asked",
    "called",
    "cried",
    "muttered",
    "replied",
    "said",
    "shouted",
    "whispered",
}
IGNORED_CAST_SPEAKER_NAMES = {"narrator", "unknown", "speaker"}


@dataclass(frozen=True)
class CharacterIndex:
    by_name: dict[str, CharacterRecord]

    def add(self, character: CharacterRecord) -> None:
        for name in _character_names(character):
            key = _name_key(name)
            if key and key not in self.by_name:
                self.by_name[key] = character


@dataclass(frozen=True)
class SpeakerAttributionWindow:
    segments: list[SegmentRecord]
    target_segment_ids: set[str]
    active_speakers: list[str]


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
        for position, segment in enumerate(segments):
            self._upsert_deterministic(
                project_id, segment, character_index, segments, position
            )
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "speaker_attribution",
                        "current": position + 1,
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
        segments: list[SegmentRecord],
        position: int,
    ) -> SpeakerAttribution:
        explicit_candidate = segment.speaker_candidate.strip() if segment.speaker_candidate else None
        candidate = explicit_candidate
        context_hint = (
            _speaker_context_hint(segment, segments, position, character_index)
            if not candidate and _looks_like_dialogue(segment.text_content)
            else None
        )
        if context_hint:
            candidate = str(context_hint["speakerName"])
        character = character_index.by_name.get(_name_key(candidate)) if candidate else None
        proposed_cast = False
        if (
            explicit_candidate
            and not character
            and segment.speaker_confidence >= 0.8
            and _can_propose_cast(explicit_candidate)
        ):
            character = CastDiscoveryService(self.container).propose_from_speaker_attribution(
                project_id,
                speaker_name=explicit_candidate,
                segment_id=segment.id,
                chapter_id=None,
                text=segment.text_content,
                confidence=segment.speaker_confidence,
            )
            if character:
                character_index.add(character)
                proposed_cast = True
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
                "reason": str(context_hint["reason"])
                if context_hint
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
            if context_hint:
                evidence.update(context_hint)
                confidence = _confidence(context_hint.get("confidence"))
                status = "needs_review"
            if proposed_cast:
                evidence["castProposal"] = "proposed_cast_from_speaker_attribution"
                evidence["proposedCharacterId"] = character.id if character else None
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
        windows = list(_scene_context_windows(segments, unresolved_segments))
        for batch_index, window in enumerate(windows, 1):
            scene_window_segment_ids = [segment.id for segment in window.segments]
            target_segment_ids = [
                segment.id for segment in window.segments if segment.id in window.target_segment_ids
            ]
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "llm_speaker_attribution",
                        "current": batch_index,
                        "total": len(windows),
                    },
                )
            try:
                result = LocalLlmService(self.container).extract(
                    project_id,
                    LlmExtractionRequest(
                        model=model,
                        task="speaker_attribution",
                        schema=SPEAKER_ATTRIBUTION_SCHEMA,
                        prompt=self._llm_prompt(
                            window.segments,
                            character_index,
                            exemplars,
                            target_segment_ids=window.target_segment_ids,
                            active_speakers=window.active_speakers,
                        ),
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
                    metadata={"error": str(error)[:500], "segmentIds": target_segment_ids},
                    dedupe_key=f"speaker-llm:{project_id}:{target_segment_ids[0]}",
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
                if segment_id not in window.target_segment_ids:
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
                        "sceneWindowSegmentIds": scene_window_segment_ids,
                        "targetSegmentIds": target_segment_ids,
                        "activeSpeakers": window.active_speakers,
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
        *,
        target_segment_ids: set[str] | None = None,
        active_speakers: list[str] | None = None,
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
            f"- {'TARGET' if not target_segment_ids or segment.id in target_segment_ids else 'CONTEXT'} "
            f"{segment.id}: {segment.text_content[:500].replace(chr(10), ' ')}"
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
        active_speaker_line = ", ".join(active_speakers or []) or "Unknown"
        return (
            "Assign likely speakers for this bounded audiobook segment window. Use only the supplied "
            "Character Bible cast when linking a character. Leave uncertain speakers in review by "
            "returning low confidence. Return attributions only for TARGET segment IDs; CONTEXT lines "
            "are same-scene evidence only. Return JSON that matches the supplied schema.\n\n"
            f"{exemplar_block}"
            f"Cast: {'; '.join(character_lines) if character_lines else 'No cast records yet'}\n\n"
            f"Active speakers in this scene: {active_speaker_line}\n\n"
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


def _character_names(character: CharacterRecord) -> list[str]:
    return [character.display_name, character.canonical_name or "", *_aliases(character)]


def _evidence(payload: str | None) -> dict[str, object]:
    try:
        loaded = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], loaded if isinstance(loaded, dict) else {})


def _speaker_context_hint(
    segment: SegmentRecord,
    segments: list[SegmentRecord],
    position: int,
    character_index: CharacterIndex,
) -> dict[str, object] | None:
    previous_segment = segments[position - 1] if position >= 1 else None
    next_segment = segments[position + 1] if position + 1 < len(segments) else None
    named_cue, cue_position = _adjacent_named_speech_cue(
        segment, previous_segment, next_segment, character_index
    )
    if named_cue:
        return {
            "reason": "speech_action_cue",
            "speakerName": named_cue,
            "speechCue": named_cue,
            "cuePosition": cue_position,
            "confidence": 0.76,
        }

    pronoun_hint = _pronoun_coreference_hint(
        segment, segments, previous_segment, next_segment, character_index
    )
    if pronoun_hint:
        return pronoun_hint

    nearby_hint = _nearby_turn_hint(segment, previous_segment, next_segment)
    if nearby_hint:
        return nearby_hint

    exchange_hint = _active_speaker_exchange_hint(segment, segments, position, character_index)
    if exchange_hint:
        return exchange_hint

    return _alternation_hint(segment, segments, position)


def _adjacent_named_speech_cue(
    segment: SegmentRecord,
    previous_segment: SegmentRecord | None,
    next_segment: SegmentRecord | None,
    character_index: CharacterIndex,
) -> tuple[str | None, str]:
    for candidate, position in (
        (segment, "current"),
        (next_segment, "next"),
        (previous_segment, "previous"),
    ):
        if not candidate or candidate.scene_id != segment.scene_id:
            continue
        named_cue = _named_speech_cue(candidate.text_content, character_index)
        if named_cue:
            return named_cue, position
    return None, ""


def _nearby_turn_hint(
    segment: SegmentRecord,
    previous_segment: SegmentRecord | None,
    next_segment: SegmentRecord | None,
) -> dict[str, object] | None:
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
        "confidence": 0.66,
    }


def _pronoun_coreference_hint(
    segment: SegmentRecord,
    segments: list[SegmentRecord],
    previous_segment: SegmentRecord | None,
    next_segment: SegmentRecord | None,
    character_index: CharacterIndex,
) -> dict[str, object] | None:
    pronoun = _adjacent_pronoun_cue(segment, previous_segment, next_segment)
    gender = _pronoun_gender(pronoun)
    if not gender:
        return None
    active_speakers = _scene_active_speakers(segment, segments)
    matches: list[CharacterRecord] = []
    for speaker in active_speakers:
        character = character_index.by_name.get(_name_key(speaker))
        if character and _character_has_gender(character, gender):
            matches.append(character)
    unique = {character.id: character for character in matches}
    if len(unique) != 1:
        return None
    character = next(iter(unique.values()))
    return {
        "reason": "pronoun_coreference",
        "speakerName": character.display_name,
        "pronounCue": pronoun or "",
        "genderTrait": f"gender:{gender}",
        "activeSpeakers": active_speakers,
        "confidence": 0.7,
    }


def _adjacent_pronoun_cue(
    segment: SegmentRecord,
    previous_segment: SegmentRecord | None,
    next_segment: SegmentRecord | None,
) -> str | None:
    for candidate in (segment, next_segment, previous_segment):
        if not candidate or candidate.scene_id != segment.scene_id:
            continue
        pronoun = _pronoun_cue(candidate.text_content)
        if pronoun:
            return pronoun
    return None


def _scene_active_speakers(segment: SegmentRecord, segments: list[SegmentRecord]) -> list[str]:
    speakers: list[str] = []
    for candidate in segments:
        if candidate.scene_id != segment.scene_id:
            continue
        speaker = _confident_dialogue_speaker(candidate)
        if speaker and speaker not in speakers:
            speakers.append(speaker)
    return speakers


def _active_speakers_for_segments(segments: list[SegmentRecord]) -> list[str]:
    speakers: list[str] = []
    for segment in segments:
        speaker = _confident_dialogue_speaker(segment)
        if speaker and speaker not in speakers:
            speakers.append(speaker)
    return speakers


def _confident_dialogue_speaker(segment: SegmentRecord) -> str:
    speaker = segment.speaker_candidate.strip() if segment.speaker_candidate else ""
    if segment.segment_type == "dialogue" and speaker and segment.speaker_confidence >= 0.8:
        return speaker
    return ""


def _active_speaker_exchange_hint(
    segment: SegmentRecord,
    segments: list[SegmentRecord],
    position: int,
    character_index: CharacterIndex,
) -> dict[str, object] | None:
    active_speakers = _scene_active_speakers(segment, segments)
    if len(active_speakers) != 2:
        return None

    interruption_hint = _interruption_exchange_hint(
        segment, segments[:position], active_speakers
    )
    if interruption_hint:
        return interruption_hint

    return _vocative_exchange_hint(segment, active_speakers, character_index)


def _interruption_exchange_hint(
    segment: SegmentRecord,
    previous_segments: list[SegmentRecord],
    active_speakers: list[str],
) -> dict[str, object] | None:
    previous_dialogue = _previous_labeled_dialogue(segment, previous_segments)
    if not previous_dialogue or not _ends_with_interruption(previous_dialogue.text_content):
        return None
    interrupted_speaker = _confident_dialogue_speaker(previous_dialogue)
    speaker_name = _other_active_speaker(active_speakers, interrupted_speaker)
    if not speaker_name:
        return None
    return {
        "reason": "interruption_exchange",
        "speakerName": speaker_name,
        "interruptedSpeaker": interrupted_speaker,
        "activeSpeakers": active_speakers,
        "confidence": 0.68,
    }


def _vocative_exchange_hint(
    segment: SegmentRecord,
    active_speakers: list[str],
    character_index: CharacterIndex,
) -> dict[str, object] | None:
    addressed_speaker = _addressed_active_speaker(
        segment.text_content, active_speakers, character_index
    )
    if not addressed_speaker:
        return None
    speaker_name = _other_active_speaker(active_speakers, addressed_speaker)
    if not speaker_name:
        return None
    return {
        "reason": "vocative_exchange",
        "speakerName": speaker_name,
        "addressedSpeaker": addressed_speaker,
        "activeSpeakers": active_speakers,
        "confidence": 0.67,
    }


def _previous_labeled_dialogue(
    segment: SegmentRecord, previous_segments: list[SegmentRecord]
) -> SegmentRecord | None:
    for candidate in reversed(previous_segments):
        if candidate.scene_id != segment.scene_id:
            continue
        if _confident_dialogue_speaker(candidate):
            return candidate
    return None


def _ends_with_interruption(text: str) -> bool:
    stripped = text.rstrip().rstrip('"”’\'').rstrip()
    return stripped.endswith(("—", "--", "...", "-"))


def _addressed_active_speaker(
    text: str,
    active_speakers: list[str],
    character_index: CharacterIndex,
) -> str | None:
    opened = text.strip().lstrip('"“‘\'').strip()
    for speaker in active_speakers:
        names = _active_speaker_names(speaker, character_index)
        for name in sorted(names, key=len, reverse=True):
            escaped = re.escape(name.strip())
            if escaped and re.match(rf"^{escaped}\b\s*[,!?:;—-]", opened, re.IGNORECASE):
                return speaker
    return None


def _active_speaker_names(speaker: str, character_index: CharacterIndex) -> list[str]:
    character = character_index.by_name.get(_name_key(speaker))
    names = _character_names(character) if character else [speaker]
    return [name for name in names if name.strip()]


def _other_active_speaker(active_speakers: list[str], speaker: str) -> str | None:
    if len(active_speakers) != 2 or speaker not in active_speakers:
        return None
    for candidate in active_speakers:
        if candidate != speaker:
            return candidate
    return None


def _pronoun_gender(pronoun: str | None) -> str | None:
    if pronoun in {"she", "her", "hers"}:
        return "feminine"
    if pronoun in {"he", "him", "his"}:
        return "masculine"
    if pronoun in {"they", "them", "their", "theirs"}:
        return "neutral"
    return None


def _character_has_gender(character: CharacterRecord, gender: str) -> bool:
    try:
        traits = json.loads(character.traits_json or "[]")
    except json.JSONDecodeError:
        return False
    return isinstance(traits, list) and f"gender:{gender}" in {str(item) for item in traits}


def _alternation_hint(
    segment: SegmentRecord, segments: list[SegmentRecord], position: int
) -> dict[str, object] | None:
    previous = _nearest_labeled_speakers(segment, segments[:position], reverse=True, limit=2)
    following = _nearest_labeled_speakers(segment, segments[position + 1 :], reverse=False, limit=1)
    if len(previous) < 2 or not following:
        return None
    previous_speaker, prior_speaker = previous[0], previous[1]
    next_speaker = following[0]
    if previous_speaker == prior_speaker or next_speaker not in {previous_speaker, prior_speaker}:
        return None
    return {
        "reason": "turn_taking_alternation",
        "speakerName": prior_speaker,
        "previousSpeaker": previous_speaker,
        "priorSpeaker": prior_speaker,
        "nextSpeaker": next_speaker,
        "confidence": 0.64,
    }


def _nearest_labeled_speakers(
    segment: SegmentRecord,
    candidates: list[SegmentRecord],
    *,
    reverse: bool,
    limit: int,
) -> list[str]:
    speakers: list[str] = []
    iterable = reversed(candidates) if reverse else iter(candidates)
    for candidate in iterable:
        if candidate.scene_id != segment.scene_id:
            continue
        speaker = candidate.speaker_candidate.strip() if candidate.speaker_candidate else ""
        if candidate.segment_type == "dialogue" and speaker and speaker not in speakers:
            speakers.append(speaker)
        if len(speakers) >= limit:
            break
    return speakers


def _named_speech_cue(text: str, character_index: CharacterIndex) -> str | None:
    characters = {
        character.id: character for character in character_index.by_name.values()
    }.values()
    verb_pattern = "|".join(sorted(SPEECH_VERBS))
    for character in sorted(characters, key=lambda item: len(item.display_name), reverse=True):
        for name in sorted(_character_names(character), key=len, reverse=True):
            if not name.strip():
                continue
            escaped = re.escape(name)
            if re.search(rf"\b{escaped}\b\s+(?:{verb_pattern})\b", text, re.IGNORECASE):
                return character.display_name
            if re.search(rf"\b(?:{verb_pattern})\s+\b{escaped}\b", text, re.IGNORECASE):
                return character.display_name
    return None


def _pronoun_cue(text: str) -> str | None:
    lowered = text.casefold()
    verb_pattern = "|".join(sorted(SPEECH_VERBS))
    for pronoun in ("she", "her", "hers", "he", "him", "his", "they", "them", "their", "theirs"):
        if re.search(rf"\b{pronoun}\b\s+(?:{verb_pattern})\b", lowered):
            return pronoun
        if re.search(rf"\b(?:{verb_pattern})\s+{pronoun}\b", lowered):
            return pronoun
    return None


def _can_propose_cast(name: str | None) -> bool:
    key = _name_key(name)
    return bool(key and key not in IGNORED_CAST_SPEAKER_NAMES)


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


def _scene_context_windows(
    segments: list[SegmentRecord],
    target_segments: list[SegmentRecord],
) -> list[SpeakerAttributionWindow]:
    if not target_segments:
        return []
    scene_segments: dict[str, list[SegmentRecord]] = {}
    for segment in segments:
        scene_segments.setdefault(segment.scene_id, []).append(segment)
    targets_by_scene: dict[str, list[SegmentRecord]] = {}
    for target in target_segments:
        targets_by_scene.setdefault(target.scene_id, []).append(target)

    windows: list[SpeakerAttributionWindow] = []
    for scene_id, targets in targets_by_scene.items():
        ordered_scene = scene_segments.get(scene_id, [])
        if not ordered_scene:
            continue
        active_speakers = _active_speakers_for_segments(ordered_scene)
        if _fits_llm_window(ordered_scene):
            windows.append(
                SpeakerAttributionWindow(
                    segments=ordered_scene,
                    target_segment_ids={target.id for target in targets},
                    active_speakers=active_speakers,
                )
            )
            continue
        for target_batch in _segment_batches(targets):
            windows.append(
                SpeakerAttributionWindow(
                    segments=_bounded_scene_window(ordered_scene, {target.id for target in target_batch}),
                    target_segment_ids={target.id for target in target_batch},
                    active_speakers=active_speakers,
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
        len(segments) <= SPEAKER_ATTRIBUTION_BATCH_SEGMENTS
        and sum(len(segment.text_content) for segment in segments) <= SPEAKER_ATTRIBUTION_BATCH_CHARS
    )


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
