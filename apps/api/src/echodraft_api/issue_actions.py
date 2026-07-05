from __future__ import annotations

import json
import re
from typing import cast

from echodraft_db.models import CharacterRecord, IssueRecord
from echodraft_domain import (
    IssueApplyActionRequest,
    IssueApplyActionResponse,
    IssueApplyActionResult,
)

from .container import AppContainer
from .review import ReviewService


class IssueActionService:
    """Apply evidence-backed review actions encoded on issue metadata."""

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def apply(
        self, issue_id: str, request: IssueApplyActionRequest
    ) -> IssueApplyActionResponse:
        issue = self.container.review.issue(issue_id)
        if not issue:
            raise KeyError("Issue not found")
        metadata = _metadata(issue)
        action = _text(metadata.get("reviewAction"))
        if action == "merge_cast":
            result = self._merge_cast(issue, metadata, request)
        elif action == "confirm_cast":
            result = self._confirm_cast(issue, metadata)
        else:
            raise ValueError("Issue metadata has no supported reviewAction.")
        resolved = self.container.review.merge_issue_metadata(
            issue_id,
            {
                "resolvedBy": "apply_action",
                "appliedAction": result.action,
                "characterId": result.character_id,
                "sourceCharacterId": result.source_character_id,
            },
            status="resolved",
        )
        if not resolved:
            raise KeyError("Issue not found")
        return IssueApplyActionResponse(
            issue=ReviewService.issue_model(resolved),
            result=result,
        )

    def _merge_cast(
        self,
        issue: IssueRecord,
        metadata: dict[str, object],
        request: IssueApplyActionRequest,
    ) -> IssueApplyActionResult:
        candidate_name = _required_text(metadata, "candidateName")
        target = self._resolve_target_character(
            issue.project_id, request.target_character_id, metadata
        )
        source = self._character_by_name(issue.project_id, candidate_name)
        if not source:
            source = self._create_candidate_character(issue, metadata)
        if source.id == target.id:
            raise ValueError("The cast candidate is already the selected character.")
        merged = self.container.casting.merge_characters(
            target.id,
            source.id,
            request.reason or f"Applied cast triage issue {issue.id}.",
        )
        return IssueApplyActionResult(
            action="merge_cast",
            characterId=merged.id,
            sourceCharacterId=source.id,
        )

    def _confirm_cast(
        self, issue: IssueRecord, metadata: dict[str, object]
    ) -> IssueApplyActionResult:
        candidate_name = _required_text(metadata, "candidateName")
        existing = self._character_by_name(issue.project_id, candidate_name)
        created = existing or self._create_candidate_character(issue, metadata)
        return IssueApplyActionResult(action="confirm_cast", characterId=created.id)

    def _resolve_target_character(
        self,
        project_id: str,
        target_character_id: str | None,
        metadata: dict[str, object],
    ) -> CharacterRecord:
        if target_character_id:
            target = self.container.casting.character(target_character_id)
            if not target or target.project_id != project_id:
                raise ValueError("targetCharacterId must belong to this project.")
            if target.merged_into_character_id:
                raise ValueError("targetCharacterId must be an active character.")
            return target

        possible: list[CharacterRecord | None] = []
        possible.extend(self._characters_by_ids(project_id, metadata.get("possibleMatchIds")))
        if not possible:
            possible = [
                self._character_by_name(project_id, name)
                for name in _string_list(metadata.get("possibleMatches"))
            ]
        matches = [item for item in possible if item and not item.merged_into_character_id]
        if len(matches) == 1:
            return matches[0]
        raise ValueError("targetCharacterId is required for merge_cast.")

    def _create_candidate_character(
        self, issue: IssueRecord, metadata: dict[str, object]
    ) -> CharacterRecord:
        candidate_name = _required_text(metadata, "candidateName")
        confidence = _float(metadata.get("confidence"), 0.72)
        aliases = _string_list(metadata.get("aliases"))
        traits = _string_list(metadata.get("traits"))
        evidence_graph = metadata.get("evidenceGraph")
        if not traits and isinstance(evidence_graph, dict):
            traits = _string_list(evidence_graph.get("traits"))
        canonical_name = _text(metadata.get("canonicalName")) or candidate_name
        notes = json.dumps(
            {
                "source": "issue_apply_action",
                "issueId": issue.id,
                "reviewAction": metadata.get("reviewAction"),
                "evidenceGraph": metadata.get("evidenceGraph"),
                "evidence": metadata.get("evidence"),
                "mentionEvidence": metadata.get("mentionEvidence"),
            },
            sort_keys=True,
        )
        return self.container.casting.create_character(
            project_id=issue.project_id,
            name=candidate_name,
            aliases=aliases,
            role="supporting",
            confidence=confidence,
            notes=notes,
            canonical_name=canonical_name,
            traits=traits,
            first_seen_source_id=None,
            first_seen_chapter_id=issue.chapter_id,
            first_seen_segment_id=issue.segment_id,
        )

    def _character_by_name(self, project_id: str, name: str) -> CharacterRecord | None:
        key = _name_key(name)
        if not key:
            return None
        for character in self.container.casting.characters(project_id):
            names = [character.display_name, character.canonical_name or ""]
            names.extend(_string_list(_json_value(character.aliases_json)))
            if key in {_name_key(item) for item in names}:
                return character
        return None

    def _characters_by_ids(self, project_id: str, value: object) -> list[CharacterRecord]:
        matches: list[CharacterRecord] = []
        for character_id in _string_list(value):
            character = self.container.casting.character(character_id)
            if character and character.project_id == project_id:
                matches.append(character)
        return matches


def _metadata(issue: IssueRecord) -> dict[str, object]:
    try:
        loaded = json.loads(issue.metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], loaded if isinstance(loaded, dict) else {})


def _json_value(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _required_text(metadata: dict[str, object], key: str) -> str:
    value = _text(metadata.get(key))
    if not value:
        raise ValueError(f"Issue metadata is missing {key}.")
    return value


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _float(value: object, fallback: float) -> float:
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        try:
            return max(0.0, min(1.0, float(value)))
        except ValueError:
            return fallback
    return fallback


def _name_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
