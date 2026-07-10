from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord, VoiceProfileRecord
from sqlalchemy import select

from .container import AppContainer
from .voice_catalog import VoiceCatalogService


class AutomaticCastingService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def select_narrator(self, project_id: str, style_preset: str = "warm_neutral") -> dict[str, object]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        narration = self._narration(project_id)
        pov = detect_point_of_view(narration)
        catalog = VoiceCatalogService(self.container).entries()
        if not catalog:
            catalog = VoiceCatalogService(self.container).audition_backfill()
        eligible = [entry for entry in catalog if entry.license.get("commercialUse") is True]
        if not eligible:
            raise ValueError("No commercially usable voice catalog entry is available.")
        selected = max(
            eligible,
            key=lambda entry: (
                _narrator_score(entry.facets, style_preset),
                -len(entry.id),
                entry.id,
            ),
        )
        voice_profile_id = self._project_voice(
            project_id,
            selected.id,
            selected.engine,
            selected.engine_voice_id,
        )
        current = self.container.production.get(project_id)
        self.container.production.update(
            project_id,
            voice_profile_id,
            current.default_direction_json,
        )
        return asdict(
            NarratorSelection(
                projectId=project_id,
                voiceProfileId=voice_profile_id,
                voiceCatalogEntryId=selected.id,
                pointOfView=pov.classification,
                firstPersonPronounRatio=pov.first_person_pronoun_ratio,
                stylePreset=style_preset,
                score=_narrator_score(selected.facets, style_preset),
                evidence={
                    "narrationWordCount": pov.narration_word_count,
                    "catalogVersion": selected.catalog_version,
                    "facets": selected.facets,
                },
            )
        )

    def _narration(self, project_id: str) -> str:
        with self.container.structure.database.session() as session:
            rows = session.scalars(
                select(SegmentRecord)
                .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                .where(
                    ChapterRecord.project_id == project_id,
                    SegmentRecord.segment_type != "dialogue",
                )
                .order_by(
                    ChapterRecord.order_index,
                    SceneRecord.order_index,
                    SegmentRecord.order_index,
                )
            )
            return " ".join(row.text_content for row in rows)

    def _project_voice(
        self, project_id: str, catalog_id: str, engine: str, provider_voice_id: str
    ) -> str:
        with self.container.structure.database.session() as session:
            existing = session.scalar(
                select(VoiceProfileRecord).where(
                    VoiceProfileRecord.project_id == project_id,
                    VoiceProfileRecord.voice_catalog_entry_id == catalog_id,
                )
            )
        if existing:
            return existing.id
        created = self.container.casting.create_voice(
            project_id,
            f"Auto narrator ({provider_voice_id})",
            engine,
            provider_voice_id,
            None,
        )
        with self.container.structure.database.session() as session:
            record = session.get(VoiceProfileRecord, created.id)
            assert record is not None
            record.voice_catalog_entry_id = catalog_id
            session.commit()
            return record.id


@dataclass(frozen=True)
class PointOfViewEvidence:
    classification: str
    first_person_pronoun_ratio: float
    narration_word_count: int


@dataclass(frozen=True)
class NarratorSelection:
    projectId: str
    voiceProfileId: str
    voiceCatalogEntryId: str
    pointOfView: str
    firstPersonPronounRatio: float
    stylePreset: str
    score: int
    evidence: dict[str, object]


def detect_point_of_view(narration: str) -> PointOfViewEvidence:
    words = re.findall(r"[a-z']+", narration.casefold())
    first_person = sum(
        word in {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours"}
        for word in words
    )
    ratio = first_person / max(1, len(words))
    return PointOfViewEvidence(
        classification="first_person" if ratio >= 0.015 else "third_person",
        first_person_pronoun_ratio=round(ratio, 6),
        narration_word_count=len(words),
    )


def _narrator_score(facets: list[str], preset: str) -> int:
    targets = {
        "warm_neutral": {"timbre:warm", "timbre:clear", "energy:medium"},
        "brisk": {"timbre:bright", "energy:medium"},
        "literary": {"timbre:warm", "timbre:soft"},
        "theatrical": {"timbre:bright"},
    }.get(preset, {"timbre:warm", "energy:medium"})
    return len(targets & set(facets))
