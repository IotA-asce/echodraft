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


def project_with_segment(client) -> tuple[str, str, str]:
    project = client.post(
        "/api/v1/projects", json={"title": "TTS Upgrade", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("tts.txt", b"Chapter 1\n\nHurry now, local voice.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene = client.get(f"/api/v1/chapters/{chapter}/scenes").json()[0]["id"]
    segment = client.get(f"/api/v1/scenes/{scene}/segments").json()[0]["id"]
    return project, chapter, segment


def test_tts_provider_registry_exposes_local_options(client) -> None:
    providers = client.get("/api/v1/settings/tts/providers").json()
    by_provider = {item["provider"]: item for item in providers}

    assert {"mock", "kokoro", "piper", "xtts_v2"}.issubset(by_provider)
    assert by_provider["mock"]["ready"] is True
    assert by_provider["piper"]["setupMode"] == "local_cli"
    assert by_provider["xtts_v2"]["requiresReferenceConsent"] is True


def test_render_queue_pronunciations_and_compare(client) -> None:
    project, chapter, segment = project_with_segment(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.post(
        f"/api/v1/projects/{project}/pronunciations",
        json={"term": "Hurry", "replacementText": "Her-ree"},
    )
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )

    first_job = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, first_job["id"])["status"] == "succeeded"
    queue = client.get(f"/api/v1/projects/{project}/render-queue?chapter_id={chapter}").json()
    assert queue and queue[0]["status"] == "succeeded"
    assert queue[0]["provider"] == "mock"
    render = client.get(f"/api/v1/projects/{project}/segments/{segment}/renders").json()[0]
    metadata = json.loads(Path(render["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["text"].startswith("Hurry")
    assert metadata["synthesisText"].startswith("Her-ree")
    assert metadata["ttsProvider"]["provider"] == "mock"
    assert metadata["pronunciationsApplied"][0]["term"] == "Hurry"

    client.post(
        f"/api/v1/projects/{project}/pronunciations",
        json={"term": "voice", "replacementText": "voyce"},
    )
    stale = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/production-status").json()
    assert stale["currentSegments"] == stale["totalSegments"] - 1
    second_job = client.post(
        f"/api/v1/projects/{project}/chapters/{chapter}/produce?force=true"
    ).json()
    assert wait_for_job(client, second_job["id"])["status"] == "succeeded"

    comparison = client.get(
        f"/api/v1/projects/{project}/segments/{segment}/renders/compare"
    ).json()
    assert comparison["currentRender"]
    assert comparison["previousRender"]
    assert "synthesisText" in comparison["changedFields"]
    assert "pronunciationsApplied" in comparison["changedFields"]
