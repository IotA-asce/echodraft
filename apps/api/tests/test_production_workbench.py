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
        f"/api/v1/projects/{project}/exports", json={"format": "wav", "chapterIds": [chapter]}
    ).json()
    downloaded = client.get(package["downloadUrl"])
    assert downloaded.status_code == 200
    assert downloaded.content[:2] == b"PK"
    assert Path(package["archivePath"]).is_file()


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
