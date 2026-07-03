import json
import wave
from pathlib import Path

from echodraft_domain import (
    Comment,
    Issue,
    SegmentPatchRequest,
    SegmentPatchResult,
)
from echodraft_db.models import (
    ChapterRecord,
    CommentRecord,
    IssueRecord,
    SceneRecord,
    SegmentRecord,
    SegmentRenderRecord,
)
from sqlalchemy import select

from .container import AppContainer


class ReviewService:
    """Persist deterministic local QA findings instead of relying on transient logs."""

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def qa_segment(self, project_id: str, render: SegmentRenderRecord) -> None:
        with self.container.structure.database.session() as session:
            segment = session.get(SegmentRecord, render.segment_id)
            if not segment:
                return
            scene = session.get(SceneRecord, segment.scene_id)
            chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
        rules = self._audio_rules(Path(render.audio_path), render.duration_ms)
        payload = json.loads(render.request_json)
        if segment.normalized_text != payload.get("text"):
            rules.append(
                ("render_source_mismatch", "error", "Render request does not match segment text.")
            )
        for category, severity, description in rules:
            self.container.review.create_issue(
                project_id=project_id,
                chapter_id=chapter.id if chapter else None,
                segment_id=render.segment_id,
                category=category,
                severity=severity,
                title=category.replace("_", " ").title(),
                description=description,
                metadata={"segmentRenderId": render.id},
                dedupe_key=f"segment:{render.id}:{category}",
            )

    def qa_chapter(
        self, project_id: str, chapter_id: str, render_id: str, path: str, duration: int
    ) -> None:
        for category, severity, description in self._audio_rules(Path(path), duration):
            self.container.review.create_issue(
                project_id=project_id,
                chapter_id=chapter_id,
                category=category,
                severity=severity,
                title=category.replace("_", " ").title(),
                description=description,
                metadata={"chapterRenderId": render_id},
                dedupe_key=f"chapter:{render_id}:{category}",
            )

    def patch_segment(
        self, project_id: str, segment_id: str, request: SegmentPatchRequest
    ) -> SegmentPatchResult:
        from .assembly import ChapterAssembler
        from .rendering import SegmentRenderer
        from .structure import segment_model

        segment = self.container.structure.segment(segment_id)
        if not segment:
            raise ValueError("Segment not found.")
        with self.container.structure.database.session() as session:
            scene = session.get(SceneRecord, segment.scene_id)
            chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
            previous = session.scalar(
                select(SegmentRenderRecord)
                .where(
                    SegmentRenderRecord.segment_id == segment_id,
                    SegmentRenderRecord.status == "succeeded",
                )
                .order_by(SegmentRenderRecord.created_at.desc(), SegmentRenderRecord.id.desc())
            )
        if not chapter or chapter.project_id != project_id:
            raise ValueError("Segment or project not found.")
        if request.text_content and request.text_content.strip() != segment.text_content:
            segment = self.container.structure.update_segment(segment_id, request.text_content)
            assert segment
        render = SegmentRenderer(self.container).render(project_id, segment_id, request)
        chapter_render = ChapterAssembler(self.container).assemble(project_id, chapter.id)
        self.container.review.add_patch_attempt(
            request.issue_id,
            segment_id,
            previous.id if previous else None,
            render.id,
            chapter_render.id,
        )
        return SegmentPatchResult(
            segment=segment_model(segment), render=render, chapterRender=chapter_render
        )

    @staticmethod
    def issue_model(record: IssueRecord) -> Issue:
        return Issue(
            id=record.id,
            projectId=record.project_id,
            chapterId=record.chapter_id,
            segmentId=record.segment_id,
            severity=record.severity,
            category=record.category,
            title=record.title,
            description=record.description,
            status=record.status,
            metadata=json.loads(record.metadata_json),
        )

    @staticmethod
    def comment_model(record: CommentRecord) -> Comment:
        return Comment(
            id=record.id,
            issueId=record.issue_id,
            body=record.body,
            author=record.author,
            createdAt=record.created_at,
        )

    @staticmethod
    def _audio_rules(path: Path, declared_duration_ms: int) -> list[tuple[str, str, str]]:
        if not path.is_file():
            return [("missing_audio", "blocking", "Expected audio artifact is missing.")]
        try:
            with wave.open(str(path), "rb") as audio:
                frames = audio.readframes(audio.getnframes())
                duration = int(audio.getnframes() / audio.getframerate() * 1000)
                width = audio.getsampwidth()
        except (EOFError, wave.Error):
            return [("corrupt_audio", "blocking", "Audio artifact cannot be decoded as WAV.")]
        rules: list[tuple[str, str, str]] = []
        if duration < 250:
            rules.append(("very_short_duration", "warning", "Audio is shorter than 250 ms."))
        if abs(duration - declared_duration_ms) > 50:
            rules.append(
                ("duration_mismatch", "warning", "Stored duration differs from WAV duration.")
            )
        if width == 2 and any(
            abs(int.from_bytes(frames[i : i + 2], "little", signed=True)) >= 32_760
            for i in range(0, len(frames), 2)
        ):
            rules.append(("clipping", "warning", "PCM samples approach the clipping threshold."))
        if frames and not any(frames):
            rules.append(("excessive_silence", "warning", "Audio contains only silence."))
        return rules
