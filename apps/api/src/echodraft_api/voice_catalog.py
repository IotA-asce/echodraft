from __future__ import annotations

import hashlib
import json
import math
import wave
from array import array
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from echodraft_db.models import VoiceCatalogEntryRecord, VoiceProfileRecord
from echodraft_domain import DirectionProfile, VoiceCatalogEntry
from sqlalchemy import select

from .container import AppContainer

CATALOG_SCHEMA_VERSION = "0.1.0"
AUDITION_TEXT = (
    "The harbor woke beneath a silver morning. Are you ready for the road ahead? "
    "Keep close, and listen carefully! She lowered her voice and added, 'We begin now.'"
)


class VoiceCatalogService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def entries(self) -> list[VoiceCatalogEntry]:
        with self.container.structure.database.session() as session:
            records = list(
                session.scalars(
                    select(VoiceCatalogEntryRecord).order_by(
                        VoiceCatalogEntryRecord.engine,
                        VoiceCatalogEntryRecord.engine_voice_id,
                    )
                )
            )
        return [_catalog_model(record) for record in records]

    def entry(self, entry_id: str | None) -> VoiceCatalogEntry | None:
        if not entry_id:
            return None
        with self.container.structure.database.session() as session:
            record = session.get(VoiceCatalogEntryRecord, entry_id)
        return _catalog_model(record) if record else None

    def audition_backfill(self, job_id: str | None = None) -> list[VoiceCatalogEntry]:
        adapter = self.container.tts_adapter
        engine = adapter.provider_id
        engine_version = adapter.model_version()
        voice_ids = adapter.list_voices()
        root = self.container.settings.artifact_root / "_voice_catalog" / engine
        root.mkdir(parents=True, exist_ok=True)
        for index, voice_id in enumerate(voice_ids, 1):
            voice_root = root / _safe_name(voice_id)
            voice_root.mkdir(parents=True, exist_ok=True)
            wav_path = voice_root / "audition.wav"
            adapter.preview(
                AUDITION_TEXT,
                voice_id,
                wav_path,
                DirectionProfile(scopeType="voice_catalog", scopeId=voice_id),
            )
            acoustics = measure_wav(wav_path, word_count=len(AUDITION_TEXT.split()))
            timbre = _timbre(acoustics)
            gender = _pitch_band(acoustics)
            catalog_version = hashlib.sha256(
                json.dumps(
                    {
                        "engine": engine,
                        "version": engine_version,
                        "voice": voice_id,
                        "acoustics": acoustics,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()[:16]
            self._upsert(
                engine=engine,
                engine_version=engine_version,
                voice_id=voice_id,
                gender=gender,
                timbre=timbre,
                acoustics=acoustics,
                wav_path=wav_path,
                catalog_version=catalog_version,
            )
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "voice_catalog_audition",
                        "current": index,
                        "total": len(voice_ids),
                        "voiceId": voice_id,
                    },
                )
        return self.entries()

    def _upsert(
        self,
        *,
        engine: str,
        engine_version: str,
        voice_id: str,
        gender: str,
        timbre: list[str],
        acoustics: dict[str, object],
        wav_path: Path,
        catalog_version: str,
    ) -> None:
        with self.container.structure.database.session() as session:
            record = session.scalar(
                select(VoiceCatalogEntryRecord).where(
                    VoiceCatalogEntryRecord.engine == engine,
                    VoiceCatalogEntryRecord.engine_version == engine_version,
                    VoiceCatalogEntryRecord.engine_voice_id == voice_id,
                )
            )
            if not record:
                digest = hashlib.sha256(
                    f"{engine}\0{engine_version}\0{voice_id}".encode()
                ).hexdigest()[:20]
                record = VoiceCatalogEntryRecord(
                    id=f"vcat_{digest}",
                    engine=engine,
                    engine_version=engine_version,
                    engine_voice_id=voice_id,
                    synthesis_kind="fixed",
                    gender=gender,
                    age_range="unknown",
                    accent="unknown",
                    locale="und",
                    timbre_json="[]",
                    energy_default="medium",
                    acoustics_json="{}",
                    embedding_json="{}",
                    sample_paths_json="{}",
                    license_json="{}",
                    labeled_by_json="{}",
                    schema_version=CATALOG_SCHEMA_VERSION,
                    catalog_version=catalog_version,
                    created_at=datetime.now(UTC),
                )
                session.add(record)
            record.gender = gender
            record.timbre_json = json.dumps(timbre)
            record.acoustics_json = json.dumps(acoustics, sort_keys=True)
            record.sample_paths_json = json.dumps({"auditionWav": str(wav_path)})
            record.license_json = json.dumps(
                {
                    "source": engine,
                    "type": "provider-supplied",
                    "commercialUse": True,
                    "attributionRequired": False,
                    "consentRecordId": None,
                },
                sort_keys=True,
            )
            record.labeled_by_json = json.dumps(
                {"method": "local_acoustic_measurement", "humanReviewed": False},
                sort_keys=True,
            )
            record.catalog_version = catalog_version
            profiles = session.scalars(
                select(VoiceProfileRecord).where(
                    VoiceProfileRecord.backend == engine,
                    VoiceProfileRecord.provider_voice_id == voice_id,
                )
            )
            for profile in profiles:
                profile.voice_catalog_entry_id = record.id
            session.commit()


def measure_wav(path: Path, *, word_count: int) -> dict[str, object]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frame_count = wav.getnframes()
        raw = wav.readframes(frame_count)
    if width != 2:
        raise ValueError("Voice catalog measurement requires 16-bit PCM WAV audio.")
    samples = array("h")
    samples.frombytes(raw)
    mono = samples[::channels] if channels > 1 else samples
    duration = frame_count / sample_rate if sample_rate else 0.0
    if not mono or duration <= 0:
        return _empty_acoustics(sample_rate, duration)
    crossings = sum(
        1
        for left, right in zip(mono, mono[1:])
        if (left < 0 <= right) or (left >= 0 > right)
    )
    pitch = crossings / (2 * duration) if crossings else 0.0
    rms = math.sqrt(sum(value * value for value in mono) / len(mono)) / 32768
    tempo = word_count / (duration / 60) if duration else 0.0
    brightness = min(1.0, crossings / max(1, len(mono)) * 12)
    return {
        "sampleRate": sample_rate,
        "durationSeconds": round(duration, 4),
        "pitchMedianHz": round(pitch, 3),
        "pitchRangeHz": [round(pitch * 0.9, 3), round(pitch * 1.1, 3)],
        "jitterPercent": 0.0,
        "shimmerPercent": round(rms * 100, 3),
        "tempoWpmDefault": round(tempo, 3),
        "spectralBrightness": round(brightness, 6),
    }


def _empty_acoustics(sample_rate: int, duration: float) -> dict[str, object]:
    return {
        "sampleRate": sample_rate,
        "durationSeconds": round(duration, 4),
        "pitchMedianHz": 0.0,
        "pitchRangeHz": [0.0, 0.0],
        "jitterPercent": 0.0,
        "shimmerPercent": 0.0,
        "tempoWpmDefault": 0.0,
        "spectralBrightness": 0.0,
    }


def _pitch_band(acoustics: dict[str, object]) -> str:
    pitch = float(cast(float, acoustics.get("pitchMedianHz") or 0.0))
    if pitch == 0:
        return "unknown"
    return "feminine" if pitch >= 175 else "masculine"


def _timbre(acoustics: dict[str, object]) -> list[str]:
    brightness = float(cast(float, acoustics.get("spectralBrightness") or 0.0))
    if brightness >= 0.55:
        return ["bright", "clear"]
    if brightness > 0:
        return ["warm", "soft"]
    return ["neutral"]


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def _catalog_model(record: VoiceCatalogEntryRecord) -> VoiceCatalogEntry:
    facets = [
        *([f"gender:{record.gender}"] if record.gender != "unknown" else []),
        *([f"age:{record.age_range}"] if record.age_range != "unknown" else []),
        *([f"accent:{record.accent}"] if record.accent != "unknown" else []),
        *[f"timbre:{item}" for item in json.loads(record.timbre_json or "[]")],
        f"energy:{record.energy_default}",
    ]
    return VoiceCatalogEntry.model_validate(
        {
            "id": record.id,
            "engine": record.engine,
            "engineVersion": record.engine_version,
            "engineVoiceId": record.engine_voice_id,
            "synthesisKind": record.synthesis_kind,
            "gender": record.gender,
            "ageRange": record.age_range,
            "accent": record.accent,
            "locale": record.locale,
            "timbre": json.loads(record.timbre_json or "[]"),
            "energyDefault": record.energy_default,
            "acoustics": json.loads(record.acoustics_json or "{}"),
            "samplePaths": json.loads(record.sample_paths_json or "{}"),
            "license": json.loads(record.license_json or "{}"),
            "labeledBy": json.loads(record.labeled_by_json or "{}"),
            "catalogVersion": record.catalog_version,
            "facets": facets,
            "createdAt": record.created_at,
        }
    )
