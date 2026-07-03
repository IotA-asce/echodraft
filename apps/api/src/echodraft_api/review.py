import json
import wave
from pathlib import Path

from echodraft_domain import (
    Comment,
    Issue,
    SegmentPatchRequest,
    SegmentPatchResult,
    SegmentRenderRequest,
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

from .audio_analysis import AudioAnalysis, analyze_wav
from .container import AppContainer

# Isolated inter-sample rounding is not audible clipping; only a real run of clipped
# samples counts.
CLIPPING_SAMPLE_THRESHOLD = 8
# "Excessive" silence is judged against genuine dead air (see `audio_analysis`'s 3s/
# boundary-excluding rules), not brief natural pauses between sentences.
EXCESSIVE_SILENCE_RATIO = 0.20
EXCESSIVE_SILENCE_SINGLE_RANGE_MS = 5000
# Rough segment-level RMS bounds; exact LUFS gating arrives with mastering (Phase 2 task
# B1 per docs/plans/2026-07-04-phase-2-publishable-audio.md).
LOW_LOUDNESS_DBFS = -30.0
HIGH_LOUDNESS_DBFS = -14.0
# 30 chars/sec is fast speech; audio much shorter than that floor for its text length is
# probably truncated, not just terse.
TRUNCATION_CHARS_PER_SECOND = 30
TRUNCATION_MIN_TEXT_CHARS = 40
# Mastered chapter loudness target and QA tolerance (Phase 2 task B1). Only meaningful for
# chapter-level audio that has actually been mastered (ffmpeg present); segment RMS bounds
# above stay the rough proxy for un-mastered segment renders.
MASTER_TARGET_LUFS = -19.0
MASTER_LUFS_TOLERANCE = 1.0


class ReviewService:
    """Persist deterministic local QA findings instead of relying on transient logs."""

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def qa_segment(
        self,
        project_id: str,
        render: SegmentRenderRecord,
        analysis: AudioAnalysis | None = None,
    ) -> None:
        with self.container.structure.database.session() as session:
            segment = session.get(SegmentRecord, render.segment_id)
            if not segment:
                return
            scene = session.get(SceneRecord, segment.scene_id)
            chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
        payload = json.loads(render.request_json)
        rules = self._audio_rules(
            Path(render.audio_path),
            render.duration_ms,
            payload.get("synthesisText"),
            analysis=analysis,
        )
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
        self,
        project_id: str,
        chapter_id: str,
        render_id: str,
        path: str,
        duration: int,
        analysis: AudioAnalysis | None = None,
        mastered_lufs: float | None = None,
    ) -> None:
        findings = list(self._audio_rules(Path(path), duration, analysis=analysis))
        # When the chapter was mastered (ffmpeg present) its measured integrated loudness
        # gates against the -19 LUFS target directly, tightening the rough RMS bounds that
        # apply to un-mastered segment audio.
        if (
            mastered_lufs is not None
            and abs(mastered_lufs - MASTER_TARGET_LUFS) > MASTER_LUFS_TOLERANCE
        ):
            findings.append(
                (
                    "chapter_loudness_out_of_range",
                    "warning",
                    f"Mastered integrated loudness {mastered_lufs:.1f} LUFS is outside "
                    f"±{MASTER_LUFS_TOLERANCE:.0f} of {MASTER_TARGET_LUFS:.0f} LUFS.",
                )
            )
        for category, severity, description in findings:
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
        from .production import ProductionService
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
        # Resolve each field independently: a caller who supplies one half (e.g. a voice
        # but no direction) must not force resolution of the other half to also require a
        # narrator voice. Only the field that is actually missing gets resolved server-side.
        production = ProductionService(self.container)
        voice = request.voice_profile_id or production.resolve_voice(project_id, segment_id)
        direction = request.direction or production.resolve_direction(project_id, segment_id)
        render_request = SegmentRenderRequest(
            voiceProfileId=voice,
            direction=direction,
            outputFormat=request.output_format,
            force=True,
        )
        render = SegmentRenderer(self.container).render(project_id, segment_id, render_request)
        chapter_render = ChapterAssembler(self.container).assemble(project_id, chapter.id)
        self.container.review.add_patch_attempt(
            request.issue_id,
            segment_id,
            previous.id if previous else None,
            render.id,
            chapter_render.id,
        )
        if request.issue_id:
            self._auto_resolve_patched_issue(request.issue_id, render.id)
        return SegmentPatchResult(
            segment=segment_model(segment), render=render, chapterRender=chapter_render
        )

    def _auto_resolve_patched_issue(self, issue_id: str, new_render_id: str) -> None:
        """Re-verify a render-QA issue after a corrective patch render.

        The new render's QA (already run by the renderer) either recreated a finding of the
        same category for the fresh render or it did not. Only render-QA issues carry a
        ``segmentRenderId`` in their metadata; when the re-render produced no open issue of
        the same category, the original finding is genuinely fixed and auto-resolves.
        """
        issue = self.container.review.issue(issue_id)
        if not issue:
            return
        metadata = json.loads(issue.metadata_json)
        if "segmentRenderId" not in metadata:
            return
        recurred = self.container.review.issue_by_dedupe_key(
            f"segment:{new_render_id}:{issue.category}"
        )
        if recurred and recurred.status == "open":
            return
        self.container.review.merge_issue_metadata(
            issue_id,
            {"resolvedBy": "rerender", "newRenderId": new_render_id},
            status="resolved",
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
    def _audio_rules(
        path: Path,
        declared_duration_ms: int,
        synthesis_text: str | None = None,
        analysis: AudioAnalysis | None = None,
    ) -> list[tuple[str, str, str]]:
        """Derive QA findings for one audio artifact.

        Callers that already ran ``analyze_wav`` on the same file (rendering, assembly)
        pass their result via ``analysis`` so the WAV is decoded exactly once; when it is
        omitted this decodes internally and keeps the missing/corrupt guards.
        """
        if not path.is_file():
            return [("missing_audio", "blocking", "Expected audio artifact is missing.")]
        if analysis is None:
            try:
                analysis = analyze_wav(path)
            except (EOFError, wave.Error, ValueError):
                return [
                    ("corrupt_audio", "blocking", "Audio artifact cannot be decoded as WAV.")
                ]
        duration = analysis.duration_ms
        rules: list[tuple[str, str, str]] = []
        if duration < 250:
            rules.append(("very_short_duration", "warning", "Audio is shorter than 250 ms."))
        if abs(duration - declared_duration_ms) > 50:
            rules.append(
                ("duration_mismatch", "warning", "Stored duration differs from WAV duration.")
            )
        if analysis.clipped_sample_count > CLIPPING_SAMPLE_THRESHOLD:
            rules.append(("clipping", "warning", "PCM samples approach the clipping threshold."))

        total_dead_air_ms = sum(end - start for start, end in analysis.dead_air_ranges)
        longest_dead_air_ms = max(
            (end - start for start, end in analysis.dead_air_ranges), default=0
        )
        if duration and (
            total_dead_air_ms / duration > EXCESSIVE_SILENCE_RATIO
            or longest_dead_air_ms >= EXCESSIVE_SILENCE_SINGLE_RANGE_MS
        ):
            rules.append(
                (
                    "excessive_silence",
                    "warning",
                    "Audio contains excessive silence relative to its length.",
                )
            )
        if analysis.dead_air_ranges:
            rules.append(
                (
                    "dead_air",
                    "warning",
                    f"Detected {len(analysis.dead_air_ranges)} dead-air stretch(es) totalling "
                    f"{total_dead_air_ms} ms (longest {longest_dead_air_ms} ms).",
                )
            )

        if analysis.rms_dbfs < LOW_LOUDNESS_DBFS:
            rules.append(
                ("low_loudness", "warning", "Audio is quieter than the expected loudness range.")
            )
        elif analysis.rms_dbfs > HIGH_LOUDNESS_DBFS:
            rules.append(
                ("high_loudness", "warning", "Audio is louder than the expected loudness range.")
            )

        if synthesis_text and len(synthesis_text) > TRUNCATION_MIN_TEXT_CHARS:
            expected_floor_ms = len(synthesis_text) / TRUNCATION_CHARS_PER_SECOND * 1000
            if duration < 0.5 * expected_floor_ms:
                rules.append(
                    (
                        "truncation_suspected",
                        "warning",
                        "Audio is much shorter than the text length would suggest; "
                        "the render may be truncated.",
                    )
                )
        return rules
