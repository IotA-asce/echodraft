from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import wave
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from echodraft_db.models import (
    ChapterRecord,
    ChapterRenderRecord,
    ExportPackageRecord,
    IssueRecord,
    ReadinessReportRecord,
    SceneRecord,
    SegmentRenderRecord,
    SegmentRecord,
    SourceDocumentRecord,
)
from echodraft_domain import ExportBlocker, ExportEstimate, ExportPackage, ExportQa, ExportRequest
from sqlalchemy import and_, or_, select

from . import mastering
from .audio_analysis import analyze_wav
from .container import AppContainer

EXPORT_MANIFEST_VERSION = "0.3.0"
MP3_BITRATE_BPS = 192_000
M4B_BITRATE_BPS = 128_000
RETAIL_SAMPLE_SECONDS = 300
EXPORT_LUFS_TOLERANCE = 1.0


@dataclass(frozen=True)
class PlannedChapter:
    chapter: ChapterRecord
    render: ChapterRenderRecord
    source_path: Path
    audio_variant: str
    estimated_size_bytes: int


@dataclass(frozen=True)
class ChapterMarker:
    title: str
    duration_ms: int


@dataclass(frozen=True)
class ExportPlan:
    project_id: str
    export_format: str
    audio_variant: str
    metadata: dict[str, object]
    chapters: list[PlannedChapter]
    blockers: list[ExportBlocker]
    estimated_size_bytes: int
    m4b_planned: bool


class ExportService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def estimate(self, project_id: str, request: ExportRequest) -> ExportEstimate:
        plan = self._plan(project_id, request)
        return ExportEstimate(
            projectId=project_id,
            format=plan.export_format,
            audioVariant=plan.audio_variant,
            chapterCount=len(plan.chapters),
            estimatedSizeBytes=plan.estimated_size_bytes,
            blockers=plan.blockers,
            metadata=plan.metadata,
            m4bPlanned=plan.m4b_planned,
        )

    def export(self, project_id: str, request: ExportRequest) -> ExportPackage:
        plan = self._plan(project_id, request)
        if plan.blockers:
            details = "; ".join(blocker.message for blocker in plan.blockers[:3])
            raise ValueError(f"Resolve export blockers before export: {details}")

        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")

        export_id = f"export_{uuid4().hex[:16]}"
        root = Path(project.artifact_path) / "exports" / export_id
        staging = root.with_suffix(".staging")
        staging.mkdir(parents=True)

        outputs: list[dict[str, object]] = []
        qa_outputs: list[dict[str, object]] = []
        source_render_ids: list[str] = []
        render_lineage: list[dict[str, object]] = []
        provider_names: set[str] = set()
        model_versions: set[str] = set()
        voice_profile_ids: set[str] = set()
        render_modes: set[str] = set()
        cover_source = self._cover_source(plan.metadata)

        with self.container.structure.database.session() as session:
            source = self._latest_source(session, project_id)
            latest_readiness = self._latest_readiness(session, project_id)
            open_blocking_issues = self._open_blocking_issue_summary(session, project_id)
            for index, planned in enumerate(plan.chapters, 1):
                target: Path | None = None
                if plan.export_format == "wav":
                    target = staging / f"{index:02d}-{planned.chapter.id}.wav"
                    shutil.copyfile(planned.source_path, target)
                elif plan.export_format == "mp3":
                    target = staging / f"{index:02d}-{planned.chapter.id}.mp3"
                    self._write_mp3(
                        planned.source_path,
                        target,
                        plan.metadata,
                        track_index=index,
                        total_tracks=len(plan.chapters),
                        cover=cover_source,
                    )

                chapter_manifest = self._read_json(planned.render.manifest_path)
                segment_render_ids = [
                    str(item.get("segmentRenderId"))
                    for item in self._manifest_inputs(chapter_manifest)
                    if item.get("segmentRenderId")
                ]
                segment_lineage = self._segment_lineage(session, segment_render_ids)
                for item in segment_lineage:
                    provider = item.get("provider")
                    model = item.get("modelVersion")
                    voice = item.get("voiceProfileId")
                    if isinstance(provider, str) and provider:
                        provider_names.add(provider)
                    if isinstance(model, str) and model:
                        model_versions.add(model)
                    if isinstance(voice, str) and voice:
                        voice_profile_ids.add(voice)
                source_render_ids.append(planned.render.id)
                render_modes.add(planned.render.render_mode)
                if target is not None:
                    score = self._qa_score_for_output(target, planned.render.duration_ms)
                    qa_outputs.append(score)
                    outputs.append(
                        {
                            "role": "chapter",
                            "chapterId": planned.chapter.id,
                            "chapterTitle": planned.chapter.title,
                            "chapterRenderId": planned.render.id,
                            "chapterRenderMode": planned.render.render_mode,
                            "audioVariant": planned.audio_variant,
                            "filename": target.name,
                            "artifactPath": f"exports/{export_id}/{target.name}",
                            "artifactUrl": f"/api/v1/projects/{project_id}/artifacts/exports/{export_id}/{target.name}",
                            "bytes": score["bytes"],
                            "durationMs": planned.render.duration_ms,
                            "sha256": score["sha256"],
                            "segmentRenderIds": segment_render_ids,
                            "segmentCount": len(segment_render_ids),
                        }
                    )
                render_lineage.append(
                    {
                        "chapterId": planned.chapter.id,
                        "chapterRenderId": planned.render.id,
                        "segmentRenders": segment_lineage,
                    }
                )

        selected_duration_ms = sum(item.render.duration_ms for item in plan.chapters)
        if plan.export_format == "m4b":
            target = staging / "audiobook.m4b"
            self._write_m4b(plan.chapters, target, staging, plan.metadata, cover_source)
            score = self._qa_score_for_output(target, selected_duration_ms)
            qa_outputs.append(score)
            outputs.append(
                {
                    "role": "audiobook",
                    "filename": target.name,
                    "artifactPath": f"exports/{export_id}/{target.name}",
                    "artifactUrl": f"/api/v1/projects/{project_id}/artifacts/exports/{export_id}/{target.name}",
                    "bytes": score["bytes"],
                    "durationMs": selected_duration_ms,
                    "sha256": score["sha256"],
                    "audioVariant": plan.audio_variant,
                    "chapterCount": len(plan.chapters),
                    "chapters": [
                        {
                            "chapterId": item.chapter.id,
                            "chapterTitle": item.chapter.title,
                            "chapterRenderId": item.render.id,
                            "durationMs": item.render.duration_ms,
                        }
                        for item in plan.chapters
                    ],
                }
            )
        if request.include_retail_sample and plan.export_format in {"mp3", "m4b"} and plan.chapters:
            first = plan.chapters[0]
            target = staging / "retail_sample.mp3"
            sample_duration_ms = min(first.render.duration_ms, RETAIL_SAMPLE_SECONDS * 1000)
            self._write_retail_sample(first.source_path, target, plan.metadata, cover_source)
            score = self._qa_score_for_output(target, sample_duration_ms)
            qa_outputs.append(score)
            outputs.append(
                {
                    "role": "retail_sample",
                    "filename": target.name,
                    "artifactPath": f"exports/{export_id}/{target.name}",
                    "artifactUrl": f"/api/v1/projects/{project_id}/artifacts/exports/{export_id}/{target.name}",
                    "bytes": score["bytes"],
                    "durationMs": sample_duration_ms,
                    "sha256": score["sha256"],
                    "sourceChapterId": first.chapter.id,
                    "sourceChapterTitle": first.chapter.title,
                    "audioVariant": first.audio_variant,
                }
            )

        cover_filename = self._copy_cover(plan.metadata, staging)
        manifest = staging / "export_manifest.json"
        qa_scorecard = self._qa_manifest(qa_outputs, latest_readiness, open_blocking_issues)
        summary = {
            "chapterCount": len(plan.chapters),
            "durationMs": selected_duration_ms,
            "outputBytes": sum(_int_value(item.get("bytes")) for item in outputs),
            "estimatedSizeBytes": plan.estimated_size_bytes,
            "providers": sorted(provider_names),
            "modelVersions": sorted(model_versions),
            "voiceProfileIds": sorted(voice_profile_ids),
            "renderModes": sorted(render_modes),
            "sourceRenderCount": len(source_render_ids),
            "retailSampleIncluded": any(item.get("role") == "retail_sample" for item in outputs),
            "m4bPlanned": False,
        }
        manifest_payload = {
            "manifestType": "export_manifest",
            "schemaVersion": EXPORT_MANIFEST_VERSION,
            "exportId": export_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "projectId": project_id,
            "format": plan.export_format,
            "audioVariant": plan.audio_variant,
            "metadata": {**plan.metadata, "coverFilename": cover_filename},
            "source": self._source_manifest(source),
            "qa": qa_scorecard,
            "sourceRenders": source_render_ids,
            "outputs": outputs,
            "renderLineage": render_lineage,
            "summary": summary,
        }
        manifest.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8"
        )

        archive = staging / "audiobook.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for output in outputs:
                package.write(staging / str(output["filename"]), str(output["filename"]))
            if cover_filename:
                package.write(staging / cover_filename, cover_filename)
            package.write(manifest, manifest.name)
        archive_sha = self._file_sha256(archive)
        summary["archiveBytes"] = archive.stat().st_size
        summary["archiveSha256"] = archive_sha
        manifest_payload["summary"] = summary
        manifest.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8"
        )

        staging.replace(root)
        record = ExportPackageRecord(
            id=export_id,
            project_id=project_id,
            format=plan.export_format,
            status="succeeded",
            output_path=str(root),
            manifest_path=str(root / manifest.name),
            archive_path=str(root / archive.name),
        )
        with self.container.structure.database.session() as session:
            session.add(record)
            session.commit()
        return self._model(record)

    def list_packages(self, project_id: str) -> list[ExportPackage]:
        with self.container.structure.database.session() as session:
            records = list(
                session.scalars(
                    select(ExportPackageRecord)
                    .where(ExportPackageRecord.project_id == project_id)
                    .order_by(ExportPackageRecord.created_at.desc(), ExportPackageRecord.id.desc())
                )
            )
        return [self._model(record) for record in records]

    def get(self, project_id: str, export_id: str) -> ExportPackage | None:
        with self.container.structure.database.session() as session:
            record = session.get(ExportPackageRecord, export_id)
            if not record or record.project_id != project_id:
                return None
        return self._model(record)

    def _plan(self, project_id: str, request: ExportRequest) -> ExportPlan:
        export_format = request.format.strip().lower()
        audio_variant = request.audio_variant.strip().lower()
        metadata = self._request_metadata(project_id, request)
        blockers: list[ExportBlocker] = []
        m4b_planned = False
        if export_format not in {"wav", "mp3", "m4b"}:
            blockers.append(
                ExportBlocker(
                    code="unsupported_format",
                    message="Only WAV, MP3, and M4B exports are available locally.",
                    scope="format",
                )
            )
        if audio_variant not in {"active", "clean", "mixed"}:
            blockers.append(
                ExportBlocker(
                    code="unsupported_audio_variant",
                    message="Use audioVariant active, clean, or mixed.",
                    scope="audioVariant",
                )
            )
        if export_format in {"mp3", "m4b"} and shutil.which("ffmpeg") is None:
            blockers.append(
                ExportBlocker(
                    code="ffmpeg_missing",
                    message="MP3, M4B, and retail sample exports require FFmpeg.",
                    scope="system",
                )
            )
        cover_path = metadata.get("coverImagePath")
        if (
            isinstance(cover_path, str)
            and cover_path
            and not Path(cover_path).expanduser().is_file()
        ):
            blockers.append(
                ExportBlocker(
                    code="cover_missing",
                    message="Cover image path does not exist.",
                    scope="metadata",
                )
            )

        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")
        if project.rights_status.value != "declared":
            blockers.append(
                ExportBlocker(
                    code="rights_not_declared",
                    message="Declared rights are required for export.",
                    scope="rights",
                )
            )

        planned: list[PlannedChapter] = []
        with self.container.structure.database.session() as session:
            chapters = list(
                session.scalars(
                    select(ChapterRecord)
                    .where(ChapterRecord.project_id == project_id)
                    .order_by(ChapterRecord.order_index)
                )
            )
            if request.chapter_ids:
                selected = set(request.chapter_ids)
                known = {chapter.id for chapter in chapters}
                for chapter_id in sorted(selected - known):
                    blockers.append(
                        ExportBlocker(
                            code="chapter_not_found",
                            message=f"Chapter {chapter_id} is not part of this project.",
                            scope="chapter",
                            chapterId=chapter_id,
                        )
                    )
                chapters = [chapter for chapter in chapters if chapter.id in selected]
            if not chapters:
                blockers.append(
                    ExportBlocker(
                        code="no_chapters_selected",
                        message="Select at least one chapter for export.",
                        scope="chapter",
                    )
                )
            selected_chapter_ids = {chapter.id for chapter in chapters}
            blockers.extend(
                self._blocking_issue_blockers(session, project_id, selected_chapter_ids)
            )
            for chapter in chapters:
                render = self._active_render(session, chapter.id)
                if not render:
                    blockers.append(
                        ExportBlocker(
                            code="missing_chapter_render",
                            message=f"Chapter {chapter.title or chapter.id} has no assembled render.",
                            scope="chapter",
                            chapterId=chapter.id,
                        )
                    )
                    continue
                source_path, resolved_variant = self._source_path(render, audio_variant)
                if not source_path:
                    blockers.append(
                        ExportBlocker(
                            code="missing_mixed_render",
                            message=f"Chapter {chapter.title or chapter.id} has no mixed render.",
                            scope="chapter",
                            chapterId=chapter.id,
                        )
                    )
                    continue
                if not source_path.is_file():
                    blockers.append(
                        ExportBlocker(
                            code="missing_audio_file",
                            message=f"Audio artifact is missing for chapter render {render.id}.",
                            scope="chapter",
                            chapterId=chapter.id,
                        )
                    )
                    continue
                planned.append(
                    PlannedChapter(
                        chapter=chapter,
                        render=render,
                        source_path=source_path,
                        audio_variant=resolved_variant,
                        estimated_size_bytes=self._estimate_audio_size(
                            export_format, source_path, render.duration_ms
                        ),
                    )
                )
        estimated = sum(item.estimated_size_bytes for item in planned) + 12_000
        if request.include_retail_sample and export_format in {"mp3", "m4b"} and planned:
            sample_ms = min(planned[0].render.duration_ms, RETAIL_SAMPLE_SECONDS * 1000)
            estimated += max(1, int((sample_ms / 1000) * (MP3_BITRATE_BPS / 8)))
        return ExportPlan(
            project_id=project_id,
            export_format=export_format,
            audio_variant=audio_variant,
            metadata=metadata,
            chapters=planned,
            blockers=blockers,
            estimated_size_bytes=estimated,
            m4b_planned=m4b_planned,
        )

    def _request_metadata(self, project_id: str, request: ExportRequest) -> dict[str, object]:
        project = self.container.projects.get(project_id)
        return {
            "title": request.title or (project.title if project else None),
            "author": request.author or (project.author if project else None),
            "album": request.album or (project.title if project else None),
            "publisher": request.publisher,
            "copyright": request.copyright,
            "language": request.language or "en",
            "coverImagePath": request.cover_image_path,
        }

    @staticmethod
    def _source_path(render: ChapterRenderRecord, audio_variant: str) -> tuple[Path | None, str]:
        if audio_variant == "clean":
            return Path(render.speech_path), "clean"
        if audio_variant == "mixed":
            return (
                (Path(render.mixed_audio_path), "mixed")
                if render.mixed_audio_path
                else (None, "mixed")
            )
        if render.mixed_audio_path:
            return Path(render.mixed_audio_path), "mixed"
        return Path(render.speech_path), "clean"

    @staticmethod
    def _estimate_audio_size(export_format: str, source: Path, duration_ms: int) -> int:
        if export_format == "mp3":
            return max(1, int((duration_ms / 1000) * (MP3_BITRATE_BPS / 8)))
        if export_format == "m4b":
            return max(1, int((duration_ms / 1000) * (M4B_BITRATE_BPS / 8)))
        return source.stat().st_size

    def _write_mp3(
        self,
        source: Path,
        target: Path,
        metadata: dict[str, object],
        *,
        track_index: int,
        total_tracks: int,
        cover: Path | None,
    ) -> None:
        self._run_media_command(
            self._mp3_command(
                source,
                target,
                metadata,
                track_index=track_index,
                total_tracks=total_tracks,
                cover=cover,
            ),
            target,
            "MP3 export",
        )

    def _write_retail_sample(
        self,
        source: Path,
        target: Path,
        metadata: dict[str, object],
        cover: Path | None,
    ) -> None:
        self._run_media_command(
            self._mp3_command(
                source,
                target,
                metadata,
                track_index=None,
                total_tracks=None,
                cover=cover,
                sample_seconds=RETAIL_SAMPLE_SECONDS,
                title_override=f"{self._metadata_value(metadata, 'title', 'Audiobook')} Retail Sample",
            ),
            target,
            "Retail sample export",
        )

    def _write_m4b(
        self,
        chapters: list[PlannedChapter],
        target: Path,
        staging: Path,
        metadata: dict[str, object],
        cover: Path | None,
    ) -> None:
        concat_file = staging / "m4b-concat.txt"
        metadata_file = staging / "m4b-ffmetadata.txt"
        markers = [
            ChapterMarker(
                title=planned.chapter.title or f"Chapter {index}",
                duration_ms=planned.render.duration_ms,
            )
            for index, planned in enumerate(chapters, 1)
        ]
        concat_file.write_text(
            self._concat_manifest([item.source_path for item in chapters]), encoding="utf-8"
        )
        metadata_file.write_text(self._ffmetadata(markers, metadata), encoding="utf-8")
        try:
            self._run_media_command(
                self._m4b_command(concat_file, metadata_file, target, cover),
                target,
                "M4B export",
            )
        finally:
            concat_file.unlink(missing_ok=True)
            metadata_file.unlink(missing_ok=True)

    @classmethod
    def _mp3_command(
        cls,
        source: Path,
        target: Path,
        metadata: dict[str, object],
        *,
        track_index: int | None,
        total_tracks: int | None,
        cover: Path | None,
        sample_seconds: int | None = None,
        title_override: str | None = None,
    ) -> list[str]:
        command = ["ffmpeg", "-y", "-v", "error", "-i", str(source)]
        if cover:
            command.extend(["-i", str(cover)])
        if sample_seconds is not None:
            command.extend(["-t", str(sample_seconds)])
        if cover:
            command.extend(["-map", "0:a", "-map", "1:v"])
        command.extend(cls._ffmpeg_metadata_args(metadata, title_override=title_override))
        if track_index is not None and total_tracks is not None:
            command.extend(["-metadata", f"track={track_index}/{total_tracks}"])
        command.extend(["-codec:a", "libmp3lame", "-b:a", "192k"])
        if cover:
            command.extend(["-c:v", "mjpeg", "-disposition:v", "attached_pic"])
        command.extend(["-id3v2_version", "3", str(target)])
        return command

    @staticmethod
    def _m4b_command(
        concat_file: Path,
        metadata_file: Path,
        target: Path,
        cover: Path | None,
    ) -> list[str]:
        command = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-f",
            "ffmetadata",
            "-i",
            str(metadata_file),
        ]
        if cover:
            command.extend(["-i", str(cover), "-map", "0:a", "-map", "2:v"])
        else:
            command.extend(["-map", "0:a"])
        command.extend(
            [
                "-map_metadata",
                "1",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
            ]
        )
        if cover:
            command.extend(["-c:v", "mjpeg", "-disposition:v", "attached_pic"])
        command.extend(["-movflags", "+faststart", str(target)])
        return command

    @classmethod
    def _ffmpeg_metadata_args(
        cls, metadata: dict[str, object], *, title_override: str | None = None
    ) -> list[str]:
        pairs = [
            ("title", title_override or cls._metadata_value(metadata, "title", "Audiobook")),
            ("artist", cls._metadata_value(metadata, "author", "")),
            ("album", cls._metadata_value(metadata, "album", "")),
            ("genre", "Audiobook"),
            ("date", datetime.now(UTC).strftime("%Y")),
            ("publisher", cls._metadata_value(metadata, "publisher", "")),
            ("language", cls._metadata_value(metadata, "language", "en")),
            ("copyright", cls._metadata_value(metadata, "copyright", "")),
        ]
        args: list[str] = []
        for key, value in pairs:
            if value:
                args.extend(["-metadata", f"{key}={value}"])
        return args

    @classmethod
    def _ffmetadata(cls, chapters: list[ChapterMarker], metadata: dict[str, object]) -> str:
        lines = [";FFMETADATA1"]
        for key, value in (
            ("title", cls._metadata_value(metadata, "title", "Audiobook")),
            ("artist", cls._metadata_value(metadata, "author", "")),
            ("album", cls._metadata_value(metadata, "album", "")),
            ("genre", "Audiobook"),
            ("date", datetime.now(UTC).strftime("%Y")),
            ("publisher", cls._metadata_value(metadata, "publisher", "")),
            ("language", cls._metadata_value(metadata, "language", "en")),
            ("copyright", cls._metadata_value(metadata, "copyright", "")),
        ):
            if value:
                lines.append(f"{key}={cls._escape_ffmetadata(value)}")
        start = 0
        for chapter in chapters:
            end = start + max(0, chapter.duration_ms)
            lines.extend(
                [
                    "[CHAPTER]",
                    "TIMEBASE=1/1000",
                    f"START={start}",
                    f"END={end}",
                    f"title={cls._escape_ffmetadata(chapter.title or 'Untitled')}",
                ]
            )
            start = end
        return "\n".join(lines) + "\n"

    @classmethod
    def _concat_manifest(cls, sources: list[Path]) -> str:
        return "".join(f"file '{cls._escape_concat_path(source)}'\n" for source in sources)

    @staticmethod
    def _escape_concat_path(path: Path) -> str:
        return str(path).replace("'", "'\\''")

    @staticmethod
    def _escape_ffmetadata(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("=", "\\=")
            .replace(";", "\\;")
            .replace("#", "\\#")
            .replace("\n", "\\n")
        )

    @staticmethod
    def _metadata_value(metadata: dict[str, object], key: str, fallback: str) -> str:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    @staticmethod
    def _run_media_command(command: list[str], target: Path, label: str) -> None:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError(f"{label} failed: {error}") from error
        if completed.returncode or not target.is_file() or target.stat().st_size == 0:
            detail = (
                completed.stderr.strip() or completed.stdout.strip() or "ffmpeg produced no file"
            )
            raise ValueError(f"{label} failed: {detail}")

    def _qa_manifest(
        self,
        outputs: list[dict[str, object]],
        latest_readiness: ReadinessReportRecord | None,
        open_blocking_issues: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "targetLufs": mastering.TARGET_LUFS,
            "lufsTolerance": EXPORT_LUFS_TOLERANCE,
            "truePeakCeilingDb": mastering.TRUE_PEAK_DB,
            "allWithinTolerance": bool(outputs)
            and all(output.get("withinTolerance") is True for output in outputs),
            "outputs": outputs,
            "latestReadinessReport": self._readiness_manifest(latest_readiness),
            "openBlockingIssues": open_blocking_issues,
        }

    def _qa_score_for_output(self, path: Path, duration_ms: int) -> dict[str, object]:
        score: dict[str, object] = {
            "filename": path.name,
            "durationMs": duration_ms,
            "bytes": path.stat().st_size,
            "sha256": self._file_sha256(path),
        }
        if mastering.ffmpeg_available():
            try:
                measured = mastering.measure_loudness(path)
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                score.update(
                    {"method": "ffmpeg_loudnorm", "withinTolerance": False, "error": str(error)}
                )
                return score
            score["method"] = "ffmpeg_loudnorm"
            for source_key, target_key in (
                ("input_i", "lufsIntegrated"),
                ("input_tp", "truePeakDb"),
                ("input_lra", "lra"),
            ):
                value = _finite_float(measured.get(source_key))
                if value is not None:
                    score[target_key] = value
            score["withinTolerance"] = self._within_export_tolerance(score)
            return score
        if path.suffix.lower() == ".wav":
            try:
                analysis = analyze_wav(path)
            except (EOFError, OSError, ValueError, wave.Error) as error:
                score.update(
                    {"method": "rms_fallback", "withinTolerance": False, "error": str(error)}
                )
                return score
            score.update(
                {
                    "method": "rms_fallback",
                    "truePeakDb": analysis.peak_dbfs,
                    "rmsDbfs": analysis.rms_dbfs,
                    "sampleRate": analysis.sample_rate,
                    "withinTolerance": False,
                }
            )
            return score
        score.update({"method": "unavailable", "withinTolerance": False})
        return score

    @staticmethod
    def _within_export_tolerance(score: dict[str, object]) -> bool:
        lufs = score.get("lufsIntegrated")
        peak = score.get("truePeakDb")
        if not isinstance(lufs, (int, float)) or not isinstance(peak, (int, float)):
            return False
        return (
            abs(float(lufs) - mastering.TARGET_LUFS) <= EXPORT_LUFS_TOLERANCE
            and float(peak) <= mastering.TRUE_PEAK_DB
        )

    @staticmethod
    def _cover_source(metadata: dict[str, object]) -> Path | None:
        cover = metadata.get("coverImagePath")
        if not isinstance(cover, str) or not cover:
            return None
        source = Path(cover).expanduser()
        return source if source.is_file() else None

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _copy_cover(self, metadata: dict[str, object], staging: Path) -> str | None:
        cover = metadata.get("coverImagePath")
        if not isinstance(cover, str) or not cover:
            return None
        source = Path(cover).expanduser()
        if not source.is_file():
            return None
        target = staging / f"cover{source.suffix.lower() or '.image'}"
        shutil.copyfile(source, target)
        return target.name

    @staticmethod
    def _active_render(session: Any, chapter_id: str) -> ChapterRenderRecord | None:
        return cast(
            ChapterRenderRecord | None,
            session.scalar(
                select(ChapterRenderRecord)
                .where(
                    ChapterRenderRecord.chapter_id == chapter_id,
                    ChapterRenderRecord.status == "succeeded",
                )
                .order_by(ChapterRenderRecord.created_at.desc(), ChapterRenderRecord.id.desc())
            ),
        )

    @staticmethod
    def _latest_source(session: Any, project_id: str) -> SourceDocumentRecord | None:
        return cast(
            SourceDocumentRecord | None,
            session.scalar(
                select(SourceDocumentRecord)
                .where(SourceDocumentRecord.project_id == project_id)
                .order_by(SourceDocumentRecord.imported_at.desc())
            ),
        )

    @staticmethod
    def _latest_readiness(session: Any, project_id: str) -> ReadinessReportRecord | None:
        return cast(
            ReadinessReportRecord | None,
            session.scalar(
                select(ReadinessReportRecord)
                .where(ReadinessReportRecord.project_id == project_id)
                .order_by(ReadinessReportRecord.created_at.desc())
            ),
        )

    @staticmethod
    def _blocking_issue_blockers(
        session: Any, project_id: str, chapter_ids: set[str]
    ) -> list[ExportBlocker]:
        selected_segment_ids = set(
            session.scalars(
                select(SegmentRecord.id)
                .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                .where(SceneRecord.chapter_id.in_(chapter_ids))
            )
        )
        issues = list(
            session.scalars(
                select(IssueRecord).where(
                    IssueRecord.project_id == project_id,
                    IssueRecord.severity == "blocking",
                    IssueRecord.status == "open",
                    or_(
                        IssueRecord.chapter_id.in_(chapter_ids),
                        IssueRecord.segment_id.in_(selected_segment_ids),
                        and_(IssueRecord.chapter_id.is_(None), IssueRecord.segment_id.is_(None)),
                    ),
                )
            )
        )
        return [
            ExportBlocker(
                code="open_blocking_issue",
                message=issue.title,
                scope="review",
                chapterId=issue.chapter_id,
                issueId=issue.id,
            )
            for issue in issues
        ]

    @staticmethod
    def _open_blocking_issue_summary(session: Any, project_id: str) -> list[dict[str, object]]:
        return [
            {
                "id": issue.id,
                "chapterId": issue.chapter_id,
                "segmentId": issue.segment_id,
                "title": issue.title,
                "category": issue.category,
            }
            for issue in session.scalars(
                select(IssueRecord).where(
                    IssueRecord.project_id == project_id,
                    IssueRecord.severity == "blocking",
                    IssueRecord.status == "open",
                )
            )
        ]

    @staticmethod
    def _source_manifest(source: SourceDocumentRecord | None) -> dict[str, object]:
        if not source:
            return {}
        return {
            "sourceDocumentId": source.id,
            "originalFilename": source.original_filename,
            "mimeType": source.mime_type,
            "checksum": source.checksum,
            "parserVersion": source.parser_version,
            "canonicalPath": source.canonical_path,
            "manifestPath": source.manifest_path,
        }

    @staticmethod
    def _readiness_manifest(record: ReadinessReportRecord | None) -> dict[str, object]:
        if not record:
            return {}
        return {
            "id": record.id,
            "chapterId": record.chapter_id,
            "status": record.status,
            "score": record.score,
            "summary": _json_dict(record.summary_json),
            "createdAt": record.created_at.isoformat(),
        }

    def _segment_lineage(self, session: Any, render_ids: list[str]) -> list[dict[str, object]]:
        lineage: list[dict[str, object]] = []
        for render_id in render_ids:
            record = session.get(SegmentRenderRecord, render_id)
            if not record:
                continue
            request = _json_dict(record.request_json)
            metadata = self._read_json(record.metadata_path)
            tts = _json_dict_from_value(metadata.get("tts"))
            provider = tts.get("provider") or request.get("ttsProvider")
            model_version = tts.get("modelVersion")
            lineage.append(
                {
                    "segmentRenderId": record.id,
                    "segmentId": record.segment_id,
                    "parentRenderId": record.parent_render_id,
                    "renderKey": record.render_key,
                    "durationMs": record.duration_ms,
                    "provider": provider,
                    "modelVersion": model_version,
                    "voiceProfileId": request.get("voiceProfileId"),
                    "audioPath": record.audio_path,
                    "metadataPath": record.metadata_path,
                }
            )
        return lineage

    @staticmethod
    def _manifest_inputs(manifest: dict[str, object]) -> list[dict[str, object]]:
        raw = manifest.get("inputs")
        if not isinstance(raw, list):
            return []
        return [cast(dict[str, object], item) for item in raw if isinstance(item, dict)]

    @staticmethod
    def _read_json(path: str | None) -> dict[str, object]:
        if not path:
            return {}
        try:
            loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return cast(dict[str, object], loaded if isinstance(loaded, dict) else {})

    @staticmethod
    def _model(record: ExportPackageRecord) -> ExportPackage:
        manifest = ExportService._read_json(record.manifest_path)
        summary = _json_dict_from_value(manifest.get("summary"))
        metadata = _json_dict_from_value(manifest.get("metadata"))
        qa = _json_dict_from_value(manifest.get("qa"))
        return ExportPackage(
            id=record.id,
            projectId=record.project_id,
            format=record.format,
            status=record.status,
            outputPath=record.output_path,
            manifestPath=record.manifest_path,
            archivePath=record.archive_path,
            audioVariant=str(manifest.get("audioVariant") or "active"),
            chapterCount=_int_value(summary.get("chapterCount")),
            estimatedSizeBytes=_int_value(
                summary.get("archiveBytes") or summary.get("estimatedSizeBytes")
            ),
            checksum=str(summary.get("archiveSha256")) if summary.get("archiveSha256") else None,
            metadata=metadata,
            manifestSummary=summary,
            qa=ExportQa.model_validate(qa),
            blockers=[],
            createdAt=record.created_at,
        )


def _json_dict(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], loaded if isinstance(loaded, dict) else {})


def _json_dict_from_value(value: object) -> dict[str, object]:
    return cast(dict[str, object], value if isinstance(value, dict) else {})


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _finite_float(value: object) -> float | None:
    if not isinstance(value, (str, bytes, int, float)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
