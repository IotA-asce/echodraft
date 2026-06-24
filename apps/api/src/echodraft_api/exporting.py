import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from uuid import uuid4

from echodraft_domain import ExportPackage, ExportRequest
from echodraft_db.models import ChapterRecord, ChapterRenderRecord, ExportPackageRecord, IssueRecord
from sqlalchemy import select

from .container import AppContainer


class ExportService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def export(self, project_id: str, request: ExportRequest) -> ExportPackage:
        export_format = request.format.lower()
        if export_format not in {"wav", "mp3"}:
            raise ValueError(
                "Only WAV and MP3 exports are available locally; M4B requires a media adapter."
            )
        project = self.container.projects.get(project_id)
        if not project or project.rights_status.value != "declared":
            raise ValueError("Declared rights are required for export.")
        with self.container.structure.database.session() as session:
            blocking = session.scalar(
                select(IssueRecord).where(
                    IssueRecord.project_id == project_id,
                    IssueRecord.severity == "blocking",
                    IssueRecord.status == "open",
                )
            )
            if blocking:
                raise ValueError("Resolve blocking review issues before export.")
            chapters = list(
                session.scalars(
                    select(ChapterRecord)
                    .where(ChapterRecord.project_id == project_id)
                    .order_by(ChapterRecord.order_index)
                )
            )
            if request.chapter_ids:
                selected = set(request.chapter_ids)
                chapters = [chapter for chapter in chapters if chapter.id in selected]
            renders = []
            for chapter in chapters:
                active = session.scalar(
                    select(ChapterRenderRecord)
                    .where(
                        ChapterRenderRecord.chapter_id == chapter.id,
                        ChapterRenderRecord.status == "succeeded",
                    )
                    .order_by(ChapterRenderRecord.id.desc())
                )
                if active:
                    renders.append(active)
        if not renders:
            raise ValueError("No assembled chapter renders are available.")
        export_id = f"export_{uuid4().hex[:16]}"
        root = Path(project.artifact_path) / "exports" / export_id
        staging = root.with_suffix(".staging")
        staging.mkdir(parents=True)
        outputs = []
        for index, render in enumerate(renders, 1):
            target = staging / f"{index:02d}-{render.chapter_id}.{export_format}"
            source = render.mixed_audio_path or render.speech_path
            if export_format == "wav":
                shutil.copyfile(source, target)
            else:
                completed = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-i",
                        source,
                        "-codec:a",
                        "libmp3lame",
                        "-b:a",
                        "192k",
                        str(target),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode or not target.is_file() or target.stat().st_size == 0:
                    raise ValueError(
                        f"MP3 export failed: {completed.stderr.strip() or 'ffmpeg produced no file'}"
                    )
            outputs.append(
                {
                    "chapterRenderId": render.id,
                    "filename": target.name,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
        manifest = staging / "export_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "projectId": project_id,
                    "format": export_format,
                    "sourceRenders": [x.id for x in renders],
                    "outputs": outputs,
                },
                indent=2,
            )
        )
        archive = staging / "audiobook.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for output in outputs:
                package.write(staging / output["filename"], output["filename"])
            package.write(manifest, manifest.name)
        staging.replace(root)
        record = ExportPackageRecord(
            id=export_id,
            project_id=project_id,
            format=export_format,
            status="succeeded",
            output_path=str(root),
            manifest_path=str(root / manifest.name),
            archive_path=str(root / archive.name),
        )
        with self.container.structure.database.session() as s:
            s.add(record)
            s.commit()
        return ExportPackage(
            id=record.id,
            projectId=project_id,
            format=export_format,
            status="succeeded",
            outputPath=record.output_path,
            manifestPath=record.manifest_path,
            archivePath=record.archive_path,
        )

    def list(self, project_id: str) -> list[ExportPackage]:
        with self.container.structure.database.session() as session:
            records = list(
                session.scalars(
                    select(ExportPackageRecord)
                    .where(ExportPackageRecord.project_id == project_id)
                    .order_by(ExportPackageRecord.id.desc())
                )
            )
        return [self._model(record) for record in records]

    def get(self, project_id: str, export_id: str) -> ExportPackage | None:
        with self.container.structure.database.session() as session:
            record = session.get(ExportPackageRecord, export_id)
            if not record or record.project_id != project_id:
                return None
        return self._model(record)

    @staticmethod
    def _model(record: ExportPackageRecord) -> ExportPackage:
        return ExportPackage(
            id=record.id,
            projectId=record.project_id,
            format=record.format,
            status=record.status,
            outputPath=record.output_path,
            manifestPath=record.manifest_path,
            archivePath=record.archive_path,
        )
