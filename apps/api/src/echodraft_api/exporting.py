import hashlib
import json
import shutil
from pathlib import Path
from uuid import uuid4

from echodraft_domain import ExportPackage, ExportRequest
from echodraft_db.models import ChapterRenderRecord, ExportPackageRecord, IssueRecord
from sqlalchemy import select

from .container import AppContainer


class ExportService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def export(self, project_id: str, request: ExportRequest) -> ExportPackage:
        if request.format.lower() != "wav":
            raise ValueError(
                "Only WAV export is available locally; MP3/M4B require a media adapter."
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
            query = (
                select(ChapterRenderRecord)
                .join_from(
                    ChapterRenderRecord,
                    __import__("echodraft_db.models", fromlist=["ChapterRecord"]).ChapterRecord,
                )
                .where(
                    __import__(
                        "echodraft_db.models", fromlist=["ChapterRecord"]
                    ).ChapterRecord.project_id
                    == project_id
                )
                .order_by(ChapterRenderRecord.id)
            )
            renders = list(session.scalars(query))
        if request.chapter_ids:
            renders = [item for item in renders if item.chapter_id in request.chapter_ids]
        if not renders:
            raise ValueError("No assembled chapter renders are available.")
        export_id = f"export_{uuid4().hex[:16]}"
        root = Path(project.artifact_path) / "exports" / export_id
        root.mkdir(parents=True)
        outputs = []
        for index, render in enumerate(renders, 1):
            target = root / f"{index:02d}-{render.chapter_id}.wav"
            shutil.copyfile(render.mixed_audio_path or render.speech_path, target)
            outputs.append(
                {
                    "chapterRenderId": render.id,
                    "path": str(target),
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
        manifest = root / "export_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "projectId": project_id,
                    "format": "wav",
                    "sourceRenders": [x.id for x in renders],
                    "outputs": outputs,
                },
                indent=2,
            )
        )
        record = ExportPackageRecord(
            id=export_id,
            project_id=project_id,
            format="wav",
            status="succeeded",
            output_path=str(root),
            manifest_path=str(manifest),
        )
        with self.container.structure.database.session() as s:
            s.add(record)
            s.commit()
        return ExportPackage(
            id=record.id,
            projectId=project_id,
            format="wav",
            status="succeeded",
            outputPath=record.output_path,
            manifestPath=record.manifest_path,
        )
