import json
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import text

from echodraft_api import mastering
from echodraft_api.assembly import ChapterAssembler, band_limited_resample
from echodraft_api.audio_analysis import analyze_wav


def test_band_limited_resample_preserves_duration_and_suppresses_alias_images() -> None:
    source_rate, target_rate, freq = 16_000, 44_100, 7_000
    count = int(source_rate * 0.5)
    t = np.arange(count) / source_rate
    signal = (np.sin(2 * np.pi * freq * t) * 10_000).astype(np.float64)

    resampled = band_limited_resample(signal, source_rate, target_rate)

    # Duration is preserved to within 2% (resampling correctness).
    expected = round(count * target_rate / source_rate)
    assert abs(resampled.size - expected) / expected < 0.02

    # A 7 kHz tone (near the 8 kHz source Nyquist) must not spawn alias images above
    # 8 kHz after upsampling; linear interpolation would mirror one to ~9 kHz.
    spectrum = np.abs(np.fft.rfft(resampled))
    freqs = np.fft.rfftfreq(resampled.size, d=1.0 / target_rate)
    energy_above = float(spectrum[freqs > 8_500].sum())
    assert energy_above / float(spectrum.sum()) < 0.02


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(60):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_chapter_assembly_pins_ordered_renders_and_emits_stem(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Assembly", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                (
                    b"Chapter 1: Arrival\n\n"
                    b"The first passage has enough carefully chosen words to exceed the segment "
                    b"boundary without relying on implementation-specific paragraph behavior. "
                    b"The second passage also has enough carefully chosen words to become a "
                    b"separate renderable segment in the chapter assembly test."
                ),
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(
        f"/api/v1/projects/{project}/structure/extract", json={"maxSegmentChars": 120}
    ).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert len(segments) >= 2
    rendered = []
    for segment in segments:
        response = client.post(
            f"/api/v1/projects/{project}/segments/{segment['id']}/generate",
            json={
                "voiceProfileId": "voice_test",
                "direction": {"scopeType": "project", "scopeId": project},
            },
        )
        assert response.status_code == 202
        rendered.append(response.json())

    response = client.post(f"/api/v1/projects/{project}/chapters/{chapter['id']}/assemble")
    assert response.status_code == 202, response.text
    assembled = response.json()
    manifest = json.loads(Path(assembled["manifestPath"]).read_text())
    assert [item["segmentRenderId"] for item in manifest["inputs"]] == [
        item["id"] for item in rendered
    ]
    assert Path(assembled["speechPath"]).is_file()
    with wave.open(assembled["speechPath"]) as output:
        assert output.getframerate() == 44_100
        assert output.getnchannels() == 1
    assert assembled["durationMs"] >= sum(item["durationMs"] for item in rendered) + 350
    assert (
        client.get(f"/api/v1/projects/{project}/chapters/{chapter['id']}/renders").json()[0]["id"]
        == assembled["id"]
    )
    assert (
        client.get(f"/api/v1/projects/{project}/chapters/{chapter['id']}/active-render").json()[
            "id"
        ]
        == assembled["id"]
    )


def test_chapter_assembly_honors_saved_pause_after_ms(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Pauses", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                (
                    b"Chapter 1: Arrival\n\n"
                    b"The first passage has enough carefully chosen words to exceed the segment "
                    b"boundary without relying on implementation-specific paragraph behavior. "
                    b"The second passage also has enough carefully chosen words to become a "
                    b"separate renderable segment in the chapter assembly test."
                ),
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(
        f"/api/v1/projects/{project}/structure/extract", json={"maxSegmentChars": 120}
    ).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert len(segments) >= 2

    # Save a long deliberate pause after the first segment via the direction PUT endpoint.
    saved = client.put(
        f"/api/v1/projects/{project}/segments/{segments[0]['id']}/direction",
        json={
            "direction": {
                "scopeType": "segment",
                "scopeId": segments[0]["id"],
                "pauseAfterMs": 1200,
            },
            "userLocked": True,
        },
    )
    assert saved.status_code == 200, saved.text

    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )
    produce_job = client.post(
        f"/api/v1/projects/{project}/chapters/{chapter['id']}/produce"
    ).json()
    assert wait_for_job(client, produce_job["id"])["status"] == "succeeded"

    render_durations = 0
    for segment in segments:
        render = client.get(
            f"/api/v1/projects/{project}/segments/{segment['id']}/renders"
        ).json()[0]
        render_durations += render["durationMs"]

    response = client.post(f"/api/v1/projects/{project}/chapters/{chapter['id']}/assemble")
    assert response.status_code == 202, response.text
    assembled = response.json()
    manifest = json.loads(Path(assembled["manifestPath"]).read_text())

    # The 1200 ms saved pause must dominate the 350 ms paragraph default.
    assert assembled["durationMs"] >= render_durations + 1200
    applied = manifest["pauses"]["applied"]
    assert any(
        gap["afterSegmentId"] == segments[0]["id"] and gap["ms"] == 1200 for gap in applied
    )


def test_chapter_assembly_writes_real_waveform_and_validation_telemetry(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Real Telemetry", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"A sentence to assemble for telemetry checks.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene_id = client.get(f"/api/v1/chapters/{chapter_id}/scenes").json()[0]["id"]
    segment_id = client.get(f"/api/v1/scenes/{scene_id}/segments").json()[0]["id"]
    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment_id}/generate",
        json={
            "voiceProfileId": "voice_test",
            "direction": {"scopeType": "project", "scopeId": project},
        },
    )
    assert rendered.status_code == 202

    assembled = client.post(f"/api/v1/projects/{project}/chapters/{chapter_id}/assemble")
    assert assembled.status_code == 202, assembled.text
    root = Path(assembled.json()["manifestPath"]).parent
    waveform = json.loads((root / "waveform.json").read_text())
    validation = json.loads((root / "validation_report.json").read_text())

    # Old fake was a hardcoded empty list regardless of content; the real analysis always
    # produces the full bucket count.
    assert len(waveform["peaks"]) == 200
    # The mock provider renders pure digital silence, so honest chapter QA must surface
    # `low_loudness` (RMS floors at -120 dBFS) as a warning finding -- which, being
    # non-blocking, still leaves the validation status "passed".
    findings = {item["category"]: item["severity"] for item in validation["findings"]}
    assert findings["low_loudness"] == "warning"
    assert not any(severity == "blocking" for severity in findings.values())
    assert validation["status"] == "passed"


def test_chapter_assembly_selects_latest_render_despite_adversarial_ids(client, app) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Adversarial", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                (
                    b"Chapter 1: Arrival\n\n"
                    b"The first passage has enough carefully chosen words to exceed the segment "
                    b"boundary without relying on implementation-specific paragraph behavior. "
                    b"The second passage also has enough carefully chosen words to become a "
                    b"separate renderable segment in the chapter assembly test."
                ),
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(
        f"/api/v1/projects/{project}/structure/extract", json={"maxSegmentChars": 120}
    ).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert len(segments) >= 2
    for segment in segments:
        response = client.post(
            f"/api/v1/projects/{project}/segments/{segment['id']}/generate",
            json={
                "voiceProfileId": "voice_test",
                "direction": {"scopeType": "project", "scopeId": project},
            },
        )
        assert response.status_code == 202
    target = segments[0]["id"]
    old_render_id = client.get(f"/api/v1/projects/{project}/segments/{target}/renders").json()[
        0
    ]["id"]
    rerender = client.post(
        f"/api/v1/projects/{project}/segments/{target}/generate",
        json={
            "voiceProfileId": "voice_test",
            "direction": {"scopeType": "project", "scopeId": project},
            "force": True,
        },
    )
    assert rerender.status_code == 202
    new_render_id = rerender.json()["id"]
    assert new_render_id != old_render_id

    # Give the *older* render an id that sorts after every uuid-hex id so any
    # lookup still ordering by id DESC would pick the stale render.
    adversarial_id = "rend_ffffffffffffffff"
    with app.state.container.structure.database.session() as session:
        session.execute(
            text("UPDATE segment_renders SET id = :new WHERE id = :old"),
            {"new": adversarial_id, "old": old_render_id},
        )
        session.execute(
            text(
                "UPDATE segment_renders SET parent_render_id = :new "
                "WHERE parent_render_id = :old"
            ),
            {"new": adversarial_id, "old": old_render_id},
        )
        session.commit()

    response = client.post(f"/api/v1/projects/{project}/chapters/{chapter['id']}/assemble")
    assert response.status_code == 202, response.text
    manifest = json.loads(Path(response.json()["manifestPath"]).read_text())
    stitched = {item["segmentId"]: item["segmentRenderId"] for item in manifest["inputs"]}
    assert stitched[target] == new_render_id
    assert adversarial_id not in stitched.values()

    active = client.get(
        f"/api/v1/projects/{project}/chapters/{chapter['id']}/active-render"
    ).json()
    assert active["id"] == response.json()["id"]


def test_chapter_assembly_rejects_stale_render_revision(client, app) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Stale revision", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"A sentence that will go stale.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene_id = client.get(f"/api/v1/chapters/{chapter_id}/scenes").json()[0]["id"]
    segment_id = client.get(f"/api/v1/scenes/{scene_id}/segments").json()[0]["id"]
    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment_id}/generate",
        json={
            "voiceProfileId": "voice_test",
            "direction": {"scopeType": "project", "scopeId": project},
        },
    )
    assert rendered.status_code == 202
    assembled = client.post(f"/api/v1/projects/{project}/chapters/{chapter_id}/assemble")
    assert assembled.status_code == 202, assembled.text

    # Bump the segment revision without re-rendering: the stored render is now stale.
    patched = client.patch(
        f"/api/v1/segments/{segment_id}",
        json={"textContent": "A sentence that went stale after the render."},
    )
    assert patched.status_code == 200
    assert patched.json()["revision"] == 2

    assembler = ChapterAssembler(app.state.container)
    with pytest.raises(ValueError, match="Stale render"):
        assembler.assemble(project, chapter_id)


def test_chapter_assembly_rejects_missing_segment_render(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Missing render", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"Only sentence.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]

    response = client.post(f"/api/v1/projects/{project}/chapters/{chapter_id}/assemble")
    assert response.status_code == 422
    assert "Missing successful render" in response.json()["detail"]


def test_chapter_assembly_lays_room_tone_and_records_mastering_block(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Room Tone", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"A sentence to assemble for room tone.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene_id = client.get(f"/api/v1/chapters/{chapter_id}/scenes").json()[0]["id"]
    segment_id = client.get(f"/api/v1/scenes/{scene_id}/segments").json()[0]["id"]
    assert (
        client.post(
            f"/api/v1/projects/{project}/segments/{segment_id}/generate",
            json={
                "voiceProfileId": "voice_test",
                "direction": {"scopeType": "project", "scopeId": project},
            },
        ).status_code
        == 202
    )

    assembled = client.post(
        f"/api/v1/projects/{project}/chapters/{chapter_id}/assemble"
    ).json()
    manifest = json.loads(Path(assembled["manifestPath"]).read_text())
    block = manifest["mastering"]
    assert block["targetLufs"] == -19
    assert block["truePeakDb"] == -3
    assert block["roomToneMs"] == {"head": 1000, "tail": 2000}
    # PATH presence alone does not guarantee a successful mastering pass; corrupt
    # or unsupported local ffmpeg builds still degrade honestly.
    if block["mastered"]:
        assert mastering.ffmpeg_available()
        assert "integratedLufs" in block["measured"]
    else:
        assert block["measured"] == {}

    speech = Path(assembled["speechPath"])
    with wave.open(str(speech)) as output:
        rate = output.getframerate()
        assert rate == 44_100
        frames = output.readframes(output.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64)

    def rms_dbfs(chunk: np.ndarray) -> float:
        if chunk.size == 0:
            return -120.0
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        return 20 * np.log10(rms / 32768.0) if rms > 0 else -120.0

    head = samples[: int(rate * 0.5)]
    tail = samples[-int(rate * 0.5) :]
    # Head/tail are faint room tone (~ -70 dBFS), never digital silence.
    assert int(np.count_nonzero(head)) > 0
    assert int(np.count_nonzero(tail)) > 0
    assert -85.0 < rms_dbfs(head) < -55.0
    assert -85.0 < rms_dbfs(tail) < -55.0

    # The head/tail room tone must not register as dead air (boundary-excluded).
    assert analyze_wav(speech).dead_air_ranges == []
