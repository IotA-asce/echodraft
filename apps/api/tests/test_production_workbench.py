import json
import time
from pathlib import Path


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
        files={"file": ("book.txt", b"Chapter 1: One\n\nA reviewable local sentence.", "text/plain")},
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
    assert client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    ).status_code == 200
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
    assert manifest["schemaVersion"] == "0.2.0"
    assert manifest["metadata"]["title"] == "Exported Workbench"
    assert manifest["metadata"]["author"] == "Local Author"
    assert manifest["summary"]["chapterCount"] == 1
    assert manifest["summary"]["archiveSha256"] == package["checksum"]
    assert manifest["source"]["sourceDocumentId"]
    assert manifest["outputs"][0]["sha256"]
    assert manifest["renderLineage"][0]["segmentRenders"][0]["provider"] == "mock"


def test_segment_render_cache_and_forced_lineage_are_append_only(client) -> None:
    project, _, segment = project_with_chapter(client)
    payload = {
        "voiceProfileId": "voice_test",
        "direction": {"scopeType": "project", "scopeId": project},
    }

    first = client.post(f"/api/v1/projects/{project}/segments/{segment}/generate", json=payload).json()
    cached = client.post(f"/api/v1/projects/{project}/segments/{segment}/generate", json=payload).json()
    forced = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate",
        json={**payload, "force": True},
    ).json()
    history = client.get(f"/api/v1/projects/{project}/segments/{segment}/renders").json()

    assert cached["id"] == first["id"]
    assert forced["id"] != first["id"]
    assert forced["parentRenderId"] == first["id"]
    assert {item["id"] for item in history} == {forced["id"], first["id"]}


def test_export_refuses_open_blocking_issues(client) -> None:
    project, chapter, _ = project_with_chapter(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    assert client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    ).status_code == 200
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


def test_export_estimate_marks_mixed_gate_and_m4b_as_planned(client) -> None:
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
    assert m4b["m4bPlanned"] is True
    assert m4b["blockers"][0]["code"] == "m4b_planned"
    blocked = client.post(
        f"/api/v1/projects/{project}/exports",
        json={"format": "m4b", "chapterIds": [chapter]},
    )
    assert blocked.status_code == 422
    assert "M4B export is planned" in blocked.json()["detail"]


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
