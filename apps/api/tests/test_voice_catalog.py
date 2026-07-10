import time
from pathlib import Path


def _wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_audition_backfill_measures_and_links_voice_catalog(client) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"title": "Voice catalog", "rightsStatus": "declared"},
    ).json()["id"]
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={
            "name": "Measured narrator",
            "backend": "mock",
            "providerVoiceId": "mock-narrator",
        },
    ).json()
    assert voice["voiceCatalogEntryId"] is None

    job = client.post("/api/v1/voice-catalog/audition-jobs").json()
    assert _wait_for_job(client, job["id"])["status"] == "succeeded"

    catalog = client.get("/api/v1/voice-catalog").json()
    assert {entry["engineVoiceId"] for entry in catalog} == {
        "mock-narrator",
        "mock-character",
    }
    narrator = next(
        entry for entry in catalog if entry["engineVoiceId"] == "mock-narrator"
    )
    assert narrator["labeledBy"]["method"] == "local_acoustic_measurement"
    assert narrator["acoustics"]["sampleRate"] == 16000
    assert Path(narrator["samplePaths"]["auditionWav"]).is_file()

    refreshed = client.get(f"/api/v1/projects/{project}/voices").json()[0]
    assert refreshed["voiceCatalogEntryId"] == narrator["id"]
    assert refreshed["facets"] == narrator["facets"]

    rerun = client.post("/api/v1/voice-catalog/audition-jobs").json()
    assert _wait_for_job(client, rerun["id"])["status"] == "succeeded"
    assert len(client.get("/api/v1/voice-catalog").json()) == 2
