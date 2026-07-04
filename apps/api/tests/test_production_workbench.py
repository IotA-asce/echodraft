import json
import shutil
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from echodraft_api import exporting, mastering
from echodraft_api.exporting import ChapterMarker, ExportService


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def project_with_chapter(client) -> tuple[str, str, str]:
    project = client.post(
        "/api/v1/projects", json={"title": "Workbench", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": ("book.txt", b"Chapter 1: One\n\nA reviewable local sentence.", "text/plain")
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene = client.get(f"/api/v1/chapters/{chapter}/scenes").json()[0]["id"]
    segment = client.get(f"/api/v1/scenes/{scene}/segments").json()[0]["id"]
    return project, chapter, segment


def test_production_settings_produce_download_and_export(client) -> None:
    project, chapter, segment = project_with_chapter(client)
    settings = client.put("/api/v1/settings/tts", json={"provider": "mock"})
    assert settings.status_code == 200
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    assert (
        client.put(
            f"/api/v1/projects/{project}/production-settings",
            json={"narratorVoiceProfileId": voice["id"]},
        ).status_code
        == 200
    )
    before = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/production-status").json()
    assert before["ready"] is True and before["currentSegments"] == 0
    job = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"
    after = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/production-status").json()
    assert after["currentSegments"] == after["totalSegments"] == 1
    audio = client.get(after["activeRender"]["audioUrl"])
    assert audio.status_code == 200 and audio.headers["content-type"].startswith("audio/")
    package = client.post(
        f"/api/v1/projects/{project}/exports",
        json={
            "format": "wav",
            "chapterIds": [chapter],
            "audioVariant": "clean",
            "title": "Exported Workbench",
            "author": "Local Author",
            "album": "Workbench Album",
            "language": "en",
        },
    ).json()
    downloaded = client.get(package["downloadUrl"])
    assert downloaded.status_code == 200
    assert downloaded.content[:2] == b"PK"
    assert Path(package["archivePath"]).is_file()
    assert package["audioVariant"] == "clean"
    assert package["chapterCount"] == 1
    assert package["estimatedSizeBytes"] > 0
    assert package["checksum"]
    manifest = json.loads(Path(package["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["manifestType"] == "export_manifest"
    assert manifest["schemaVersion"] == "0.3.0"
    assert manifest["metadata"]["title"] == "Exported Workbench"
    assert manifest["metadata"]["author"] == "Local Author"
    assert manifest["summary"]["chapterCount"] == 1
    assert manifest["summary"]["archiveSha256"] == package["checksum"]
    assert manifest["qa"]["targetLufs"] == -19.0
    assert manifest["qa"]["outputs"][0]["filename"].endswith(".wav")
    assert package["qa"]["outputs"][0]["sha256"] == manifest["outputs"][0]["sha256"]
    assert manifest["source"]["sourceDocumentId"]
    assert manifest["outputs"][0]["sha256"]
    assert manifest["renderLineage"][0]["segmentRenders"][0]["provider"] == "mock"


def test_segment_render_cache_and_forced_lineage_are_append_only(client) -> None:
    project, _, segment = project_with_chapter(client)
    payload = {
        "voiceProfileId": "voice_test",
        "direction": {"scopeType": "project", "scopeId": project},
    }

    first = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=payload
    ).json()
    cached = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=payload
    ).json()
    forced = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate",
        json={**payload, "force": True},
    ).json()
    history = client.get(f"/api/v1/projects/{project}/segments/{segment}/renders").json()

    assert cached["id"] == first["id"]
    assert forced["id"] != first["id"]
    assert forced["renderKey"] != first["renderKey"]
    assert forced["parentRenderId"] == first["id"]
    assert {item["id"] for item in history} == {forced["id"], first["id"]}


def test_export_refuses_open_blocking_issues(client) -> None:
    project, chapter, _ = project_with_chapter(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    assert (
        client.put(
            f"/api/v1/projects/{project}/production-settings",
            json={"narratorVoiceProfileId": voice["id"]},
        ).status_code
        == 200
    )
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"
    issue = client.post(
        f"/api/v1/projects/{project}/issues",
        json={
            "chapterId": chapter,
            "category": "readiness",
            "severity": "blocking",
            "title": "Resolve before export",
            "description": "This production should not be packaged yet.",
        },
    ).json()

    blocked = client.post(
        f"/api/v1/projects/{project}/exports",
        json={"format": "wav", "chapterIds": [chapter]},
    )
    assert blocked.status_code == 422
    assert "Resolve export blockers" in blocked.json()["detail"]
    estimate = client.post(
        f"/api/v1/projects/{project}/exports/estimate",
        json={"format": "wav", "chapterIds": [chapter]},
    ).json()
    assert estimate["estimatedSizeBytes"] > 0
    assert estimate["blockers"][0]["code"] == "open_blocking_issue"

    client.patch(f"/api/v1/issues/{issue['id']}", json={"status": "resolved"})
    assert (
        client.post(
            f"/api/v1/projects/{project}/exports",
            json={"format": "wav", "chapterIds": [chapter]},
        ).status_code
        == 202
    )


def test_export_estimate_marks_mixed_gate_and_accepts_m4b(client, monkeypatch) -> None:
    monkeypatch.setattr(
        exporting.shutil,
        "which",
        lambda command: "/usr/bin/ffmpeg" if command == "ffmpeg" else None,
    )
    project, chapter, _ = project_with_chapter(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"

    mixed = client.post(
        f"/api/v1/projects/{project}/exports/estimate",
        json={"format": "wav", "chapterIds": [chapter], "audioVariant": "mixed"},
    ).json()
    assert mixed["blockers"][0]["code"] == "missing_mixed_render"

    m4b = client.post(
        f"/api/v1/projects/{project}/exports/estimate",
        json={"format": "m4b", "chapterIds": [chapter]},
    ).json()
    assert m4b["m4bPlanned"] is False
    assert m4b["blockers"] == []


def test_export_m4b_and_retail_sample_manifest_scorecard(client, monkeypatch) -> None:
    monkeypatch.setattr(
        exporting.shutil,
        "which",
        lambda command: "/usr/bin/ffmpeg" if command == "ffmpeg" else None,
    )
    project, chapter, _ = project_with_chapter(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"

    monkeypatch.setattr(mastering, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        mastering,
        "measure_loudness",
        lambda path: {"input_i": "-19.1", "input_tp": "-3.2", "input_lra": "10.5"},
    )
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        Path(command[-1]).write_bytes(b"encoded audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(exporting.subprocess, "run", fake_run)

    package = client.post(
        f"/api/v1/projects/{project}/exports",
        json={
            "format": "m4b",
            "chapterIds": [chapter],
            "includeRetailSample": True,
            "title": "Tagged Book",
            "author": "Local Author",
            "album": "Tagged Album",
            "language": "en",
        },
    ).json()

    manifest = json.loads(Path(package["manifestPath"]).read_text(encoding="utf-8"))
    outputs_by_role = {item["role"]: item for item in manifest["outputs"]}
    assert manifest["schemaVersion"] == "0.3.0"
    assert outputs_by_role["audiobook"]["filename"] == "audiobook.m4b"
    assert outputs_by_role["audiobook"]["artifactUrl"].endswith("/audiobook.m4b")
    assert outputs_by_role["audiobook"]["chapterCount"] == 1
    assert outputs_by_role["retail_sample"]["filename"] == "retail_sample.mp3"
    assert outputs_by_role["retail_sample"]["artifactPath"].endswith("/retail_sample.mp3")
    assert manifest["summary"]["retailSampleIncluded"] is True
    assert manifest["qa"]["allWithinTolerance"] is True
    assert {item["filename"] for item in manifest["qa"]["outputs"]} == {
        "audiobook.m4b",
        "retail_sample.mp3",
    }
    assert package["qa"]["outputs"][0]["lufsIntegrated"] == -19.1
    with zipfile.ZipFile(package["archivePath"]) as archive:
        assert {"audiobook.m4b", "retail_sample.mp3", "export_manifest.json"}.issubset(
            archive.namelist()
        )
    assert any("aac" in command and "128k" in command for command in commands)
    sample_command = next(
        command for command in commands if command[-1].endswith("retail_sample.mp3")
    )
    assert "-t" in sample_command and "300" in sample_command


def test_m4b_ffmetadata_chapter_blocks_are_contiguous() -> None:
    metadata = {
        "title": "Tagged Book",
        "author": "Local Author",
        "album": "Tagged Album",
        "language": "en",
    }
    payload = ExportService._ffmetadata(
        [
            ChapterMarker("Opening", 1200),
            ChapterMarker("Middle", 2300),
            ChapterMarker("End", 500),
        ],
        metadata,
    )
    year = datetime.now(UTC).strftime("%Y")
    assert payload == (
        ";FFMETADATA1\n"
        "title=Tagged Book\n"
        "artist=Local Author\n"
        "album=Tagged Album\n"
        "genre=Audiobook\n"
        f"date={year}\n"
        "language=en\n"
        "[CHAPTER]\n"
        "TIMEBASE=1/1000\n"
        "START=0\n"
        "END=1200\n"
        "title=Opening\n"
        "[CHAPTER]\n"
        "TIMEBASE=1/1000\n"
        "START=1200\n"
        "END=3500\n"
        "title=Middle\n"
        "[CHAPTER]\n"
        "TIMEBASE=1/1000\n"
        "START=3500\n"
        "END=4000\n"
        "title=End\n"
    )


def test_mp3_command_embeds_id3_track_metadata_and_cover() -> None:
    command = ExportService._mp3_command(
        Path("chapter.wav"),
        Path("chapter.mp3"),
        {
            "title": "Tagged Book",
            "author": "Local Author",
            "album": "Tagged Album",
            "publisher": "Local Press",
            "language": "en",
        },
        track_index=2,
        total_tracks=5,
        cover=Path("cover.jpg"),
    )

    assert command[:8] == [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        "chapter.wav",
        "-i",
        "cover.jpg",
    ]
    assert ["-map", "0:a", "-map", "1:v"] == command[8:12]
    assert "-metadata" in command
    assert "title=Tagged Book" in command
    assert "artist=Local Author" in command
    assert "album=Tagged Album" in command
    assert "track=2/5" in command
    assert "-id3v2_version" in command and "3" in command
    assert "-disposition:v" in command and "attached_pic" in command


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
def test_mp3_and_m4b_exports_open_with_ffprobe_and_scorecard(client) -> None:
    project, chapter, _ = project_with_chapter(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"
    mp3_package = client.post(
        f"/api/v1/projects/{project}/exports",
        json={
            "format": "mp3",
            "chapterIds": [chapter],
            "title": "Probe Book",
            "includeRetailSample": True,
        },
    ).json()
    mp3_manifest = json.loads(Path(mp3_package["manifestPath"]).read_text(encoding="utf-8"))
    assert {item["role"] for item in mp3_manifest["outputs"]} == {
        "chapter",
        "retail_sample",
    }
    assert len(mp3_manifest["qa"]["outputs"]) == 2
    assert all(item.get("sha256") for item in mp3_manifest["qa"]["outputs"])

    package = client.post(
        f"/api/v1/projects/{project}/exports",
        json={
            "format": "m4b",
            "chapterIds": [chapter],
            "title": "Probe Book",
            "includeRetailSample": True,
        },
    ).json()
    manifest = json.loads(Path(package["manifestPath"]).read_text(encoding="utf-8"))
    outputs = {item["role"]: item for item in manifest["outputs"]}
    assert {"audiobook", "retail_sample"} == set(outputs)
    assert len(manifest["qa"]["outputs"]) == 2
    assert all(item.get("sha256") for item in manifest["qa"]["outputs"])
    m4b = Path(package["outputPath"]) / outputs["audiobook"]["filename"]
    probed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_chapters",
            str(m4b),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(json.loads(probed.stdout)["chapters"]) == 1


def test_artifact_route_rejects_escape_and_segment_override(client) -> None:
    project, _, segment = project_with_chapter(client)
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    override = client.put(
        f"/api/v1/projects/{project}/segments/{segment}/production-override",
        json={"voiceProfileId": voice["id"]},
    )
    assert override.status_code == 200
    assert override.json()["voiceProfileId"] == voice["id"]
    assert client.get(f"/api/v1/projects/{project}/artifacts/../../test.db").status_code == 404
