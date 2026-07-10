from __future__ import annotations

import hashlib
import json
import math
import wave
from array import array
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
from echodraft_db.models import VoiceCatalogEntryRecord, VoiceProfileRecord
from echodraft_domain import DirectionProfile, VoiceCatalogEntry
from sqlalchemy import select

from .container import AppContainer

CATALOG_SCHEMA_VERSION = "0.1.0"
AUDITION_TEXT = (
    "The harbor woke beneath a silver morning. Are you ready for the road ahead? "
    "Keep close, and listen carefully! She lowered her voice and added, 'We begin now.'"
)

# Frame-wise pitch/brightness measurement constants (see `_frame_features`).
_FRAME_MS = 40
_HOP_MS = 20
_MIN_PITCH_HZ = 60.0
_MAX_PITCH_HZ = 400.0
_VOICING_CONFIDENCE = 0.30
_RMS_FLOOR_DBFS = -120.0

_LABEL_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "gender": {
            "type": "string",
            "enum": ["feminine", "masculine", "androgynous", "unknown"],
        },
        "ageRange": {
            "type": "string",
            "enum": ["child", "young_adult", "adult", "elder", "unknown"],
        },
        "accent": {"type": "string"},
        "timbre": {"type": "array", "items": {"type": "string"}},
        "energyDefault": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["gender", "ageRange", "timbre", "energyDefault"],
}


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

    def audition_backfill(
        self, job_id: str | None = None, *, force: bool = False
    ) -> list[VoiceCatalogEntry]:
        """Audition every installed voice once and persist its measured entry.

        Incremental by default: a voice already cataloged for the same
        ``(engine, engine_version, engine_voice_id)`` triple is skipped rather
        than re-synthesized, so re-running this after installing new voices
        (or simply re-chaining it from casting) only pays for what changed.
        Pass ``force=True`` to re-measure everything regardless.
        """
        adapter = self.container.tts_adapter
        engine = adapter.provider_id
        engine_version = adapter.model_version()
        voice_ids = adapter.list_voices()
        already_cataloged: set[str] = set()
        if not force and voice_ids:
            with self.container.structure.database.session() as session:
                already_cataloged = set(
                    session.scalars(
                        select(VoiceCatalogEntryRecord.engine_voice_id).where(
                            VoiceCatalogEntryRecord.engine == engine,
                            VoiceCatalogEntryRecord.engine_version == engine_version,
                        )
                    )
                )
        pending = [
            voice_id
            for voice_id in voice_ids
            if force or voice_id not in already_cataloged
        ]
        skipped = [voice_id for voice_id in voice_ids if voice_id not in pending]
        if skipped:
            # Skipping re-measurement must not skip re-linking: a voice profile
            # created *after* this engine was first cataloged (e.g. a plain
            # `POST /voices` call) still needs its `voice_catalog_entry_id`
            # backfilled, even though the catalog entry itself is untouched.
            self._relink_profiles(engine, engine_version, skipped)
        root = self.container.settings.artifact_root / "_voice_catalog" / engine
        root.mkdir(parents=True, exist_ok=True)
        for index, voice_id in enumerate(pending, 1):
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
            gender = _gender_from_pitch(acoustics)
            age_range = "unknown"
            accent = "unknown"
            energy_default = "medium"
            labeled_by: dict[str, object] = {
                "method": "local_acoustic_measurement",
                "humanReviewed": False,
            }
            if self.container.settings.voice_labeling_enabled:
                labels = self._label_with_llm(engine, voice_id, acoustics)
                if labels is not None:
                    gender = str(labels.get("gender") or gender)
                    age_range = str(labels.get("ageRange") or age_range)
                    accent_value = labels.get("accent")
                    if isinstance(accent_value, str) and accent_value.strip():
                        accent = accent_value.strip().casefold()
                    label_timbre = labels.get("timbre")
                    if isinstance(label_timbre, list) and label_timbre:
                        timbre = [str(item) for item in label_timbre]
                    energy_default = str(labels.get("energyDefault") or energy_default)
                    labeled_by = {
                        "method": "llm_from_acoustic_features",
                        "model": labels.get("model", "qwen3:4b"),
                        "humanReviewed": False,
                    }
            catalog_version = hashlib.sha256(
                json.dumps(
                    {
                        "engine": engine,
                        "version": engine_version,
                        "voice": voice_id,
                        "acoustics": acoustics,
                        "gender": gender,
                        "ageRange": age_range,
                        "accent": accent,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()[:16]
            self._upsert(
                engine=engine,
                engine_version=engine_version,
                voice_id=voice_id,
                gender=gender,
                age_range=age_range,
                accent=accent,
                energy_default=energy_default,
                timbre=timbre,
                acoustics=acoustics,
                wav_path=wav_path,
                catalog_version=catalog_version,
                labeled_by=labeled_by,
            )
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "voice_catalog_audition",
                        "current": index,
                        "total": len(pending),
                        "voiceId": voice_id,
                    },
                )
        return self.entries()

    def _label_with_llm(
        self, engine: str, voice_id: str, acoustics: dict[str, object]
    ) -> dict[str, object] | None:
        """Optional, flag-gated LLM labeling pass over measured features.

        Never touches audio -- the local LLM has no audio capability, so it
        reasons purely over the numeric acoustic features plus engine
        metadata (per `automatic-casting-v2.md`'s catalog design). Fails open:
        any error (Ollama unreachable, model missing, malformed response)
        returns ``None`` and the caller keeps the acoustic-only defaults.
        """
        try:
            from .local_llm import OllamaLlmProvider, validate_json_schema

            provider = OllamaLlmProvider(self.container.settings.ollama_base_url)
            model = "qwen3:4b"
            prompt = (
                "You are labeling a text-to-speech voice for an audiobook voice "
                "catalog. You cannot hear the voice; reason only from the measured "
                "acoustic features below. Return only JSON satisfying the schema.\n\n"
                f"Engine: {engine}\nVoice id: {voice_id}\n"
                f"Measured pitch median (Hz): {acoustics.get('pitchMedianHz')}\n"
                f"Measured pitch range (Hz): {acoustics.get('pitchRangeHz')}\n"
                f"Measured spectral brightness (0-1): {acoustics.get('spectralBrightness')}\n"
                f"Measured RMS loudness (dBFS): {acoustics.get('rmsDbfs')}\n"
                f"Measured tempo (words/min): {acoustics.get('tempoWpmDefault')}\n"
            )
            result = provider.infer(model, prompt, _LABEL_SCHEMA)
            errors = validate_json_schema(result.response, _LABEL_SCHEMA)
            if errors:
                return None
            labels = dict(result.response)
            labels["model"] = model
            return labels
        except Exception:
            return None

    def _relink_profiles(
        self, engine: str, engine_version: str, voice_ids: list[str]
    ) -> None:
        with self.container.structure.database.session() as session:
            for voice_id in voice_ids:
                record = session.scalar(
                    select(VoiceCatalogEntryRecord).where(
                        VoiceCatalogEntryRecord.engine == engine,
                        VoiceCatalogEntryRecord.engine_version == engine_version,
                        VoiceCatalogEntryRecord.engine_voice_id == voice_id,
                    )
                )
                if not record:
                    continue
                profiles = session.scalars(
                    select(VoiceProfileRecord).where(
                        VoiceProfileRecord.backend == engine,
                        VoiceProfileRecord.provider_voice_id == voice_id,
                        VoiceProfileRecord.voice_catalog_entry_id.is_(None),
                    )
                )
                for profile in profiles:
                    profile.voice_catalog_entry_id = record.id
            session.commit()

    def _upsert(
        self,
        *,
        engine: str,
        engine_version: str,
        voice_id: str,
        gender: str,
        age_range: str,
        accent: str,
        energy_default: str,
        timbre: list[str],
        acoustics: dict[str, object],
        wav_path: Path,
        catalog_version: str,
        labeled_by: dict[str, object],
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
                    age_range=age_range,
                    accent=accent,
                    locale="und",
                    timbre_json="[]",
                    energy_default=energy_default,
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
            record.age_range = age_range
            record.accent = accent
            record.energy_default = energy_default
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
            record.labeled_by_json = json.dumps(labeled_by, sort_keys=True)
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
    """Measure honest acoustic features directly from an audition WAV.

    Every value here is a real signal measurement, never a fabricated
    placeholder: pitch comes from per-frame autocorrelation over voiced
    frames (median + real p10-p90 range, not a synthetic +/-10% band),
    spectral brightness is a genuine FFT spectral-centroid ratio (not the
    zero-crossing rate reused as a brightness proxy), and loudness is
    reported as ``rmsDbfs`` -- named for what it actually is, an RMS
    loudness figure in dBFS, rather than mislabeled as "shimmer". There is no
    ``jitterPercent``/``shimmerPercent``: this pipeline does not measure
    cycle-to-cycle jitter or shimmer, so those fields are omitted rather than
    hardcoded/faked.
    """
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
    signal = np.asarray(mono, dtype=np.float64)
    pitches, brightness_values = _frame_features(signal, sample_rate)
    rms = float(np.sqrt(np.mean(np.square(signal)))) / 32768.0
    tempo = word_count / (duration / 60) if duration else 0.0
    pitch_median = float(np.median(pitches)) if pitches else 0.0
    pitch_low = float(np.percentile(pitches, 10)) if pitches else 0.0
    pitch_high = float(np.percentile(pitches, 90)) if pitches else 0.0
    brightness = float(np.mean(brightness_values)) if brightness_values else 0.0
    return {
        "sampleRate": sample_rate,
        "durationSeconds": round(duration, 4),
        "pitchMedianHz": round(pitch_median, 3),
        "pitchRangeHz": [round(pitch_low, 3), round(pitch_high, 3)],
        "tempoWpmDefault": round(tempo, 3),
        "spectralBrightness": round(brightness, 6),
        "rmsDbfs": round(_dbfs(rms), 3),
    }


def _frame_features(signal: np.ndarray, sample_rate: int) -> tuple[list[float], list[float]]:
    """Per-frame autocorrelation pitch + FFT spectral-centroid brightness.

    Silent/unvoiced frames (below an adaptive energy floor) are skipped so
    inter-sentence pauses do not drag the pitch median toward zero or dilute
    the brightness average.
    """
    frame_len = max(2, int(sample_rate * _FRAME_MS / 1000))
    hop_len = max(1, int(sample_rate * _HOP_MS / 1000))
    if signal.size < frame_len:
        frame_len = signal.size
        hop_len = max(1, signal.size)
    overall_rms = float(np.sqrt(np.mean(np.square(signal)))) if signal.size else 0.0
    voiced_floor = max(40.0, overall_rms * 0.35)
    min_lag = max(1, int(sample_rate / _MAX_PITCH_HZ))
    max_lag = max(min_lag + 1, int(sample_rate / _MIN_PITCH_HZ))
    window = np.hanning(frame_len) if frame_len > 1 else np.ones(frame_len)
    pitches: list[float] = []
    brightness_values: list[float] = []
    for start in range(0, max(1, signal.size - frame_len + 1), hop_len):
        frame = signal[start : start + frame_len]
        if frame.size < frame_len:
            break
        frame_rms = float(np.sqrt(np.mean(np.square(frame))))
        if frame_rms < voiced_floor:
            continue
        centered = frame - frame.mean()
        pitch = _autocorrelation_pitch(centered, sample_rate, min_lag, max_lag)
        if pitch is not None:
            pitches.append(pitch)
        brightness_values.append(_spectral_centroid_ratio(centered * window, sample_rate))
    return pitches, brightness_values


def _autocorrelation_pitch(
    frame: np.ndarray, sample_rate: int, min_lag: int, max_lag: int
) -> float | None:
    if frame.size <= max_lag:
        return None
    corr = np.correlate(frame, frame, mode="full")[frame.size - 1 :]
    if corr[0] <= 0:
        return None
    search_end = min(max_lag, corr.size - 1)
    if search_end <= min_lag:
        return None
    window = corr[min_lag : search_end + 1]
    lag = min_lag + int(np.argmax(window))
    if lag <= 0:
        return None
    normalized_peak = corr[lag] / corr[0]
    if normalized_peak < _VOICING_CONFIDENCE:
        return None
    return sample_rate / lag


def _spectral_centroid_ratio(frame: np.ndarray, sample_rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(frame))
    total = float(spectrum.sum())
    if total <= 0:
        return 0.0
    freqs = np.fft.rfftfreq(frame.size, d=1.0 / sample_rate)
    centroid = float((freqs * spectrum).sum() / total)
    nyquist = sample_rate / 2.0
    return min(1.0, centroid / nyquist) if nyquist else 0.0


def _dbfs(rms: float) -> float:
    if rms <= 1e-6:
        return _RMS_FLOOR_DBFS
    return max(_RMS_FLOOR_DBFS, 20.0 * math.log10(rms))


def _empty_acoustics(sample_rate: int, duration: float) -> dict[str, object]:
    return {
        "sampleRate": sample_rate,
        "durationSeconds": round(duration, 4),
        "pitchMedianHz": 0.0,
        "pitchRangeHz": [0.0, 0.0],
        "tempoWpmDefault": 0.0,
        "spectralBrightness": 0.0,
        "rmsDbfs": _RMS_FLOOR_DBFS,
    }


def _gender_from_pitch(acoustics: dict[str, object]) -> str:
    """Coarse default gender guess from measured pitch, pending LLM labeling.

    This is a real signal-derived heuristic (a common bimodal pitch cutover),
    not a fabricated value -- unlike the legacy ID-string regex it replaces.
    It is superseded by `_label_with_llm`'s categorical label when voice
    labeling is enabled and Ollama succeeds.
    """
    pitch = float(cast(float, acoustics.get("pitchMedianHz") or 0.0))
    if pitch == 0:
        return "unknown"
    return "feminine" if pitch >= 175 else "masculine"


def _timbre(acoustics: dict[str, object]) -> list[str]:
    brightness = float(cast(float, acoustics.get("spectralBrightness") or 0.0))
    if brightness >= 0.15:
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
