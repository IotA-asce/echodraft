import json
from pathlib import Path
from typing import cast

from echodraft_db.models import (
    ChapterRecord,
    PatchAttemptRecord,
    SceneRecord,
    SegmentRecord,
    StructureParserWarningRecord,
)
from echodraft_domain import PatchAttempt, SegmentReviewInspector
from sqlalchemy import select

from .container import AppContainer
from .rendering import SegmentRenderer
from .review import ReviewService
from .structure import segment_model


class ReviewWorkbenchService:
    """Build a local read model for segment-level review without duplicating artifacts."""

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def inspector(self, project_id: str, segment_id: str) -> SegmentReviewInspector:
        segment, scene, chapter, warnings, patch_attempts = self._segment_context(
            project_id, segment_id
        )
        renderer = SegmentRenderer(self.container)
        render_history = renderer.history(project_id, segment_id)
        comparison = renderer.compare(project_id, segment_id)
        current_render = comparison.current_render or (render_history[0] if render_history else None)
        issues = [
            ReviewService.issue_model(record)
            for record in self.container.review.issues(project_id, segment_id=segment_id)
        ]
        comments = [
            ReviewService.comment_model(comment)
            for issue in issues
            for comment in self.container.review.comments(issue.id)
        ]
        cast_item = next(
            (
                item
                for item in self.container.speaker_attributions.list_attributions(project_id)
                if item.segment_id == segment_id
            ),
            None,
        )
        return SegmentReviewInspector.model_validate(
            {
                "projectId": project_id,
                "chapterId": chapter.id,
                "chapterTitle": chapter.title,
                "sceneId": scene.id,
                "segment": segment_model(segment),
                "sourceText": segment.text_content,
                "canonicalText": segment.normalized_text,
                "structure": self._structure_payload(segment, scene, chapter, warnings),
                "cast": cast_item,
                "direction": self.container.segment_directions.get(segment_id),
                "renderHistory": render_history,
                "waveform": self._waveform(current_render.metadata_path if current_render else None),
                "qaIssues": issues,
                "comments": comments,
                "patchQueue": [self._patch_attempt_model(item) for item in patch_attempts],
            }
        )

    def _segment_context(
        self, project_id: str, segment_id: str
    ) -> tuple[
        SegmentRecord,
        SceneRecord,
        ChapterRecord,
        list[StructureParserWarningRecord],
        list[PatchAttemptRecord],
    ]:
        with self.container.structure.database.session() as session:
            row = session.execute(
                select(SegmentRecord, SceneRecord, ChapterRecord)
                .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                .where(SegmentRecord.id == segment_id)
            ).one_or_none()
            if not row:
                raise ValueError("Segment not found.")
            segment, scene, chapter = row
            if chapter.project_id != project_id:
                raise ValueError("Segment or project not found.")
            warnings = list(
                session.scalars(
                    select(StructureParserWarningRecord)
                    .where(
                        StructureParserWarningRecord.project_id == project_id,
                        StructureParserWarningRecord.scope_id.in_(
                            [chapter.id, scene.id, segment.id]
                        ),
                    )
                    .order_by(StructureParserWarningRecord.created_at.desc())
                )
            )
            patch_attempts = list(
                session.scalars(
                    select(PatchAttemptRecord)
                    .where(PatchAttemptRecord.segment_id == segment_id)
                    .order_by(PatchAttemptRecord.created_at.desc())
                )
            )
            return segment, scene, chapter, warnings, patch_attempts

    @staticmethod
    def _structure_payload(
        segment: SegmentRecord,
        scene: SceneRecord,
        chapter: ChapterRecord,
        warnings: list[StructureParserWarningRecord],
    ) -> dict[str, object]:
        return {
            "chapter": {
                "id": chapter.id,
                "title": chapter.title,
                "orderIndex": chapter.order_index,
                "status": chapter.status,
                "confidence": chapter.confidence,
                "userLocked": chapter.user_locked,
                "lockReason": chapter.lock_reason,
                "parserEvidence": _json_dict(chapter.parser_evidence_json),
            },
            "scene": {
                "id": scene.id,
                "orderIndex": scene.order_index,
                "status": scene.status,
                "confidence": scene.confidence,
                "userLocked": scene.user_locked,
                "lockReason": scene.lock_reason,
                "parserEvidence": _json_dict(scene.parser_evidence_json),
            },
            "segment": {
                "id": segment.id,
                "orderIndex": segment.order_index,
                "status": segment.status,
                "revision": segment.revision,
                "segmentType": segment.segment_type,
                "speakerCandidate": segment.speaker_candidate,
                "speakerConfidence": segment.speaker_confidence,
                "userLocked": segment.user_locked,
                "lockReason": segment.lock_reason,
                "parserEvidence": _json_dict(segment.parser_evidence_json),
            },
            "warnings": [
                {
                    "id": item.id,
                    "scopeType": item.scope_type,
                    "scopeId": item.scope_id,
                    "severity": item.severity,
                    "message": item.message,
                    "confidence": item.confidence,
                    "resolved": item.resolved,
                    "evidence": _json_dict(item.evidence_json),
                }
                for item in warnings
            ],
        }

    @staticmethod
    def _waveform(metadata_path: str | None) -> dict[str, object]:
        if not metadata_path:
            return {}
        path = Path(metadata_path)
        if not path.is_file():
            return {"metadataPath": metadata_path, "status": "missing"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"metadataPath": metadata_path, "status": "unreadable"}
        data = cast(dict[str, object], payload if isinstance(payload, dict) else {})
        return {
            "metadataPath": metadata_path,
            "durationMs": data.get("durationMs"),
            "sampleRate": data.get("sampleRate"),
            "peak": data.get("peak"),
            "silenceRanges": data.get("silenceRanges", []),
            "waveform": data.get("waveform", []),
        }

    @staticmethod
    def _patch_attempt_model(record: PatchAttemptRecord) -> PatchAttempt:
        return PatchAttempt.model_validate(
            {
                "id": record.id,
                "issueId": record.issue_id,
                "segmentId": record.segment_id,
                "oldRenderId": record.old_render_id,
                "newRenderId": record.new_render_id,
                "chapterRenderId": record.chapter_render_id,
                "createdAt": record.created_at,
            }
        )


def _json_dict(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], parsed if isinstance(parsed, dict) else {})
