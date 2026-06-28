from uuid import uuid4

from sqlalchemy import select

from .database import Database
from .models import AmbienceAssetRecord, AmbienceCueRecord, AmbienceProfileRecord, SceneRecord


class AmbienceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def assets(self, project_id: str) -> list[AmbienceAssetRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(AmbienceAssetRecord)
                    .where(AmbienceAssetRecord.project_id == project_id)
                    .order_by(AmbienceAssetRecord.name)
                )
            )

    def asset(self, asset_id: str) -> AmbienceAssetRecord | None:
        with self.database.session() as session:
            return session.get(AmbienceAssetRecord, asset_id)

    def create_asset(
        self,
        project_id: str,
        name: str,
        path: str,
        license_note: str,
        provenance: str,
        asset_type: str = "ambience",
        duration_ms: int | None = None,
    ) -> AmbienceAssetRecord:
        record = AmbienceAssetRecord(
            id=f"ambasset_{uuid4().hex[:16]}",
            project_id=project_id,
            name=name,
            asset_type=asset_type,
            asset_path=path,
            duration_ms=duration_ms,
            license_note=license_note,
            provenance=provenance,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def profiles(self, project_id: str) -> list[AmbienceProfileRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(AmbienceProfileRecord).where(
                        AmbienceProfileRecord.project_id == project_id
                    )
                )
            )

    def create_profile(self, project_id: str, name: str, gain_db: float) -> AmbienceProfileRecord:
        record = AmbienceProfileRecord(
            id=f"ambprofile_{uuid4().hex[:16]}", project_id=project_id, name=name, gain_db=gain_db
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def cues_for_chapter(self, chapter_id: str) -> list[AmbienceCueRecord]:
        with self.database.session() as session:
            scene_ids = select(SceneRecord.id).where(SceneRecord.chapter_id == chapter_id)
            return list(
                session.scalars(
                    select(AmbienceCueRecord)
                    .where(AmbienceCueRecord.scene_id.in_(scene_ids))
                    .order_by(AmbienceCueRecord.scene_id, AmbienceCueRecord.start_ms)
                )
            )

    def cues_for_scene(self, scene_id: str) -> list[AmbienceCueRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(AmbienceCueRecord)
                    .where(AmbienceCueRecord.scene_id == scene_id)
                    .order_by(AmbienceCueRecord.start_ms)
                )
            )

    def create_cue(
        self,
        scene_id: str,
        asset_id: str | None,
        cue_type: str,
        start_ms: int,
        gain_db: float,
        fade_in_ms: int,
        fade_out_ms: int,
        ducking: bool,
        render_mode: str,
        no_sfx: bool,
    ) -> AmbienceCueRecord:
        record = AmbienceCueRecord(
            id=f"ambcue_{uuid4().hex[:16]}",
            scene_id=scene_id,
            asset_id=asset_id,
            cue_type=cue_type,
            start_ms=start_ms,
            gain_db=gain_db,
            fade_in_ms=fade_in_ms,
            fade_out_ms=fade_out_ms,
            ducking=ducking,
            render_mode=render_mode,
            no_sfx=no_sfx,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record
