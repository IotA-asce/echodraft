import json
from pathlib import Path
from typing import cast

from echodraft_db.models import (
    ChapterRecord,
    CharacterRecord,
    IssueRecord,
    PatchAttemptRecord,
    SceneRecord,
    SegmentRecord,
    SegmentRenderRecord,
    SpeakerAttributionRecord,
    StructureParserWarningRecord,
)
from echodraft_domain import (
    ChapterReviewTimeline,
    ChapterTimelineMarker,
    ChapterTimelineSegment,
    PatchAttempt,
    SegmentReviewInspector,
)
from sqlalchemy import select

from . import mastering
from .assembly import ChapterAssembler
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

    def chapter_timeline(self, project_id: str, chapter_id: str) -> ChapterReviewTimeline:
        chapter = self.container.structure.chapter(chapter_id)
        project = self.container.projects.get(project_id)
        if not project or not chapter or chapter.project_id != project_id:
            raise ValueError("Chapter or project not found.")
        try:
            active_render = ChapterAssembler(self.container).active(project_id, chapter_id)
        except ValueError:
            active_render = None
        manifest: dict[str, object] = {}
        waveform: list[float] = []
        if active_render:
            manifest = self._json_file(active_render.manifest_path)
            waveform_path = Path(active_render.manifest_path).with_name("waveform.json")
            waveform_payload = self._json_file(str(waveform_path))
            peaks = waveform_payload.get("peaks")
            waveform = [float(item) for item in peaks if isinstance(item, (int, float))] if isinstance(peaks, list) else []

        with self.container.structure.database.session() as session:
            scene_rows = list(
                session.scalars(
                    select(SceneRecord)
                    .where(SceneRecord.chapter_id == chapter_id)
                    .order_by(SceneRecord.order_index)
                )
            )
            scene_index = {scene.id: index + 1 for index, scene in enumerate(scene_rows)}
            segments = list(
                session.scalars(
                    select(SegmentRecord)
                    .where(SegmentRecord.scene_id.in_([scene.id for scene in scene_rows]))
                    .order_by(SegmentRecord.scene_id, SegmentRecord.order_index)
                )
            ) if scene_rows else []
            segment_ids = [segment.id for segment in segments]
            attributions = {
                row.segment_id: row
                for row in session.scalars(
                    select(SpeakerAttributionRecord).where(
                        SpeakerAttributionRecord.project_id == project_id,
                        SpeakerAttributionRecord.segment_id.in_(segment_ids),
                    )
                )
            } if segment_ids else {}
            character_ids = [
                row.character_id
                for row in attributions.values()
                if row.character_id is not None
            ]
            characters = {
                row.id: row.display_name
                for row in session.scalars(
                    select(CharacterRecord).where(CharacterRecord.id.in_(character_ids))
                )
            } if character_ids else {}
            issues = list(
                session.scalars(
                    select(IssueRecord)
                    .where(
                        IssueRecord.project_id == project_id,
                        IssueRecord.status == "open",
                    )
                    .order_by(IssueRecord.created_at.desc())
                )
            )
            render_durations = {
                row.id: row.duration_ms
                for row in session.scalars(
                    select(SegmentRenderRecord).where(
                        SegmentRenderRecord.id.in_(self._manifest_render_ids(manifest))
                    )
                )
            }
        timing = self._timeline_entries(manifest, render_durations)
        timing_by_segment = {str(item["segmentId"]): item for item in timing}
        chapter_duration = active_render.duration_ms if active_render else 0
        all_markers = [
            self._issue_marker(issue, timing_by_segment, chapter_duration)
            for issue in issues
            if issue.chapter_id in {None, chapter_id} or issue.segment_id in segment_ids
        ]
        segment_models: list[ChapterTimelineSegment] = []
        for segment in segments:
            attribution = attributions.get(segment.id)
            character_name = characters.get(attribution.character_id) if attribution and attribution.character_id else None
            timing_entry = timing_by_segment.get(segment.id, {})
            markers = [marker for marker in all_markers if marker.segment_id == segment.id]
            segment_models.append(
                ChapterTimelineSegment(
                    id=segment.id,
                    sceneId=segment.scene_id,
                    sceneIndex=scene_index.get(segment.scene_id, 0),
                    orderIndex=segment.order_index,
                    text=segment.normalized_text,
                    segmentType=segment.segment_type,
                    speaker=character_name or (attribution.speaker_name if attribution else None) or segment.speaker_candidate or "Narration",
                    characterId=attribution.character_id if attribution else None,
                    speakerStatus=attribution.status if attribution else None,
                    startMs=self._int_value(timing_entry.get("startMs")),
                    endMs=self._int_value(timing_entry.get("endMs")),
                    renderId=str(timing_entry["segmentRenderId"]) if timing_entry.get("segmentRenderId") else None,
                    issueMarkers=markers,
                )
            )
        return ChapterReviewTimeline(
            projectId=project_id,
            chapterId=chapter_id,
            chapterTitle=chapter.title,
            chapterRender=active_render,
            durationMs=chapter_duration,
            waveform=waveform,
            segments=segment_models,
            issueMarkers=all_markers,
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
    def _json_file(path: str) -> dict[str, object]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return cast(dict[str, object], payload if isinstance(payload, dict) else {})

    @staticmethod
    def _manifest_render_ids(manifest: dict[str, object]) -> list[str]:
        inputs = manifest.get("inputs")
        if not isinstance(inputs, list):
            return []
        return [
            str(item["segmentRenderId"])
            for item in inputs
            if isinstance(item, dict) and item.get("segmentRenderId")
        ]

    @staticmethod
    def _timeline_entries(
        manifest: dict[str, object], render_durations: dict[str, int]
    ) -> list[dict[str, object]]:
        timeline = manifest.get("timeline")
        if isinstance(timeline, list):
            return [
                cast(dict[str, object], item)
                for item in timeline
                if isinstance(item, dict) and item.get("segmentId")
            ]
        inputs = manifest.get("inputs")
        if not isinstance(inputs, list):
            return []
        pauses = cast(dict[str, object], manifest.get("pauses") if isinstance(manifest.get("pauses"), dict) else {})
        applied = pauses.get("applied")
        pause_by_segment = {
            str(item["afterSegmentId"]): int(item.get("ms", 0))
            for item in applied
            if isinstance(item, dict) and item.get("afterSegmentId") and isinstance(item.get("ms"), (int, float))
        } if isinstance(applied, list) else {}
        mastering_block = cast(
            dict[str, object],
            manifest.get("mastering") if isinstance(manifest.get("mastering"), dict) else {},
        )
        room_tone = cast(
            dict[str, object],
            mastering_block.get("roomToneMs") if isinstance(mastering_block.get("roomToneMs"), dict) else {},
        )
        cursor = ReviewWorkbenchService._int_value(
            room_tone.get("head"), default=mastering.ROOM_TONE_HEAD_MS
        )
        entries: list[dict[str, object]] = []
        for item in inputs:
            if not isinstance(item, dict) or not item.get("segmentId"):
                continue
            render_id = str(item.get("segmentRenderId") or "")
            duration = render_durations.get(render_id, 0)
            start = cursor
            end = cursor + duration
            entries.append(
                {
                    "segmentId": str(item["segmentId"]),
                    "segmentRenderId": render_id or None,
                    "sceneId": str(item.get("sceneId") or ""),
                    "startMs": start,
                    "endMs": end,
                }
            )
            cursor = end + pause_by_segment.get(str(item["segmentId"]), 0)
        return entries

    @staticmethod
    def _issue_marker(
        issue: IssueRecord,
        timing_by_segment: dict[str, dict[str, object]],
        chapter_duration_ms: int,
    ) -> ChapterTimelineMarker:
        segment_timing = timing_by_segment.get(issue.segment_id or "")
        start_ms = ReviewWorkbenchService._int_value(
            segment_timing.get("startMs") if segment_timing else None
        )
        end_ms = ReviewWorkbenchService._int_value(
            segment_timing.get("endMs") if segment_timing else None,
            default=chapter_duration_ms,
        )
        return ChapterTimelineMarker(
            id=f"marker_{issue.id}",
            issueId=issue.id,
            segmentId=issue.segment_id,
            startMs=start_ms,
            endMs=max(start_ms, end_ms),
            severity=issue.severity,
            category=issue.category,
            title=issue.title,
            status=issue.status,
        )

    @staticmethod
    def _int_value(value: object, default: int = 0) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return int(value)

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
