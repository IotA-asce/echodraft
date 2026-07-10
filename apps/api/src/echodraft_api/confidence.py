from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from echodraft_db.models import (
    ChapterRecord,
    IssueRecord,
    ReviewTaskRecord,
    SceneRecord,
    SegmentRecord,
    SpeakerAttributionRecord,
)
from echodraft_domain import ReviewTask
from sqlalchemy import select

if TYPE_CHECKING:
    from .container import AppContainer

CONFIDENCE_POLICY_VERSION = "extraction-confidence-v2-0.1.0"
STAGE_THRESHOLDS: dict[str, tuple[float, float]] = {
    "attribution": (0.9, 0.65),
    "cast": (0.9, 0.72),
    "direction": (0.88, 0.65),
    "structure": (0.85, 0.65),
}


@dataclass(frozen=True)
class DecisionClassification:
    tier: str | None
    calibrated_confidence: float
    auto_accepted: bool
    should_queue: bool


def classify_decision(
    stage: str,
    confidence: float,
    *,
    user_locked: bool = False,
    vote_tally: dict[str, int] | None = None,
) -> DecisionClassification:
    calibrated = _calibrated_confidence(confidence, vote_tally)
    if user_locked:
        return DecisionClassification(
            tier=None,
            calibrated_confidence=calibrated,
            auto_accepted=False,
            should_queue=False,
        )
    high, mid = STAGE_THRESHOLDS.get(stage, (0.9, 0.65))
    if calibrated >= high:
        tier = "high"
    elif calibrated >= mid:
        tier = "mid"
    else:
        tier = "flag"
    return DecisionClassification(
        tier=tier,
        calibrated_confidence=calibrated,
        auto_accepted=tier in {"high", "mid"},
        should_queue=tier == "flag",
    )


def _calibrated_confidence(
    confidence: float, vote_tally: dict[str, int] | None
) -> float:
    bounded = max(0.0, min(1.0, float(confidence)))
    if not vote_tally:
        return bounded
    counts = [count for count in vote_tally.values() if count > 0]
    if not counts:
        return bounded
    agreement = max(counts) / sum(counts)
    return round(agreement, 6)


class ConfidenceReviewService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def apply(self, project_id: str) -> list[ReviewTask]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        attribution_members: list[dict[str, object]] = []
        structure_members: list[dict[str, object]] = []
        flagged_attribution_ids: list[str] = []

        with self.container.structure.database.session() as session:
            chapters = list(
                session.scalars(
                    select(ChapterRecord).where(ChapterRecord.project_id == project_id)
                )
            )
            chapter_ids = {chapter.id for chapter in chapters}
            scenes = list(
                session.scalars(
                    select(SceneRecord).where(SceneRecord.chapter_id.in_(chapter_ids))
                )
            ) if chapter_ids else []
            scene_ids = {scene.id for scene in scenes}
            segments = list(
                session.scalars(
                    select(SegmentRecord).where(SegmentRecord.scene_id.in_(scene_ids))
                )
            ) if scene_ids else []
            chapter_by_scene = {scene.id: scene.chapter_id for scene in scenes}
            scene_by_segment = {segment.id: segment.scene_id for segment in segments}

            for kind, records in (
                ("chapter", chapters),
                ("scene", scenes),
                ("segment", segments),
            ):
                for record in records:
                    classified = classify_decision(
                        "structure",
                        record.confidence,
                        user_locked=record.user_locked,
                    )
                    record.auto_accepted = classified.auto_accepted
                    record.decision_tier = classified.tier
                    if classified.should_queue:
                        structure_members.append(
                            {
                                "ref": f"{kind}:{record.id}",
                                "scopeType": kind,
                                "scopeId": record.id,
                                "confidence": classified.calibrated_confidence,
                                "evidence": json.loads(record.parser_evidence_json or "{}"),
                            }
                        )

            attributions = list(
                session.scalars(
                    select(SpeakerAttributionRecord).where(
                        SpeakerAttributionRecord.project_id == project_id
                    )
                )
            )
            for row in attributions:
                evidence = json.loads(row.evidence_json or "{}")
                if not isinstance(evidence, dict):
                    evidence = {}
                tally = evidence.get("voteTally")
                vote_tally = (
                    {str(key): int(value) for key, value in tally.items()}
                    if isinstance(tally, dict)
                    else None
                )
                classified = classify_decision(
                    "attribution",
                    row.confidence,
                    user_locked=row.user_locked,
                    vote_tally=vote_tally,
                )
                row.auto_accepted = classified.auto_accepted
                row.decision_tier = classified.tier
                if classified.should_queue:
                    row.status = "needs_review"
                    flagged_attribution_ids.append(row.id)
                    scene_id = scene_by_segment.get(row.segment_id)
                    attribution_members.append(
                        {
                            "ref": f"speaker_attribution:{row.id}",
                            "attributionId": row.id,
                            "segmentId": row.segment_id,
                            "sceneId": scene_id,
                            "chapterId": chapter_by_scene.get(scene_id or ""),
                            "confidence": classified.calibrated_confidence,
                            "speakerName": row.speaker_name,
                            "evidence": evidence,
                        }
                    )
                else:
                    row.review_task_id = None
            session.commit()

        attribution_task = None
        if attribution_members:
            attribution_task = self.container.review.fold_review_task(
                project_id=project_id,
                cause_key="attribution_ambiguous",
                category="attribution",
                scope_type="project",
                scope_id=project_id,
                title=f"{len(attribution_members)} dialogue turns need speaker review",
                members=attribution_members,
                evidence={"policyVersion": CONFIDENCE_POLICY_VERSION},
            )
        if structure_members:
            self.container.review.fold_review_task(
                project_id=project_id,
                cause_key="structure_low_confidence",
                category="structure",
                scope_type="project",
                scope_id=project_id,
                title=f"{len(structure_members)} structure decisions need review",
                members=structure_members,
                evidence={"policyVersion": CONFIDENCE_POLICY_VERSION},
            )
        self._group_cast_issues(project_id)
        if attribution_task and flagged_attribution_ids:
            with self.container.structure.database.session() as session:
                rows = session.scalars(
                    select(SpeakerAttributionRecord).where(
                        SpeakerAttributionRecord.id.in_(flagged_attribution_ids)
                    )
                )
                for row in rows:
                    if not row.user_locked:
                        row.review_task_id = attribution_task.id
                session.commit()
        return self.list_tasks(project_id)

    def _group_cast_issues(self, project_id: str) -> None:
        with self.container.structure.database.session() as session:
            issues = list(
                session.scalars(
                    select(IssueRecord).where(
                        IssueRecord.project_id == project_id,
                        IssueRecord.status == "open",
                        IssueRecord.category == "cast_discovery",
                    )
                )
            )
        members = [
            {
                "ref": f"issue:{issue.id}",
                "issueId": issue.id,
                "chapterId": issue.chapter_id,
                "segmentId": issue.segment_id,
                "evidence": json.loads(issue.metadata_json or "{}"),
            }
            for issue in issues
            if _is_extraction_cast_issue(issue)
        ]
        if not members:
            return
        task = self.container.review.fold_review_task(
            project_id=project_id,
            cause_key="cast_name_confirmation",
            category="cast",
            scope_type="project",
            scope_id=project_id,
            title=f"{len(members)} cast candidates need confirmation",
            members=members,
            evidence={"policyVersion": CONFIDENCE_POLICY_VERSION},
        )
        issue_ids = [str(member["issueId"]) for member in members]
        with self.container.structure.database.session() as session:
            rows = session.scalars(select(IssueRecord).where(IssueRecord.id.in_(issue_ids)))
            for row in rows:
                row.review_task_id = task.id
            session.commit()

    def list_tasks(self, project_id: str, status: str | None = None) -> list[ReviewTask]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        return [
            _review_task(record)
            for record in self.container.review.review_tasks(project_id, status)
        ]

    def update_task(self, task_id: str, status: str) -> ReviewTask | None:
        record = self.container.review.update_review_task(task_id, status)
        return _review_task(record) if record else None


def _is_extraction_cast_issue(issue: IssueRecord) -> bool:
    try:
        metadata = json.loads(issue.metadata_json or "{}")
    except json.JSONDecodeError:
        return False
    code = str(metadata.get("code") or "") if isinstance(metadata, dict) else ""
    return code.startswith("cast.") or issue.title.startswith("LLM speaker attribution")


def _review_task(record: ReviewTaskRecord) -> ReviewTask:
    return ReviewTask.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "causeKey": record.cause_key,
            "category": record.category,
            "scopeType": record.scope_type,
            "scopeId": record.scope_id,
            "title": record.title,
            "memberCount": record.member_count,
            "memberRefs": json.loads(record.member_refs_json or "[]"),
            "evidence": json.loads(record.evidence_json or "{}"),
            "status": record.status,
            "createdAt": record.created_at,
            "updatedAt": record.updated_at,
        }
    )
