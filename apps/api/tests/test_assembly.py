import json
import time
import wave
from pathlib import Path


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
        assert output.getframerate() == 16_000
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
