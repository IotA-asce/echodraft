import time


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(60):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def project_with_source(client, text: str) -> str:
    project = client.post("/api/v1/projects", json={"title": "Structure", "rightsStatus": "declared"}).json()["id"]
    job = client.post(f"/api/v1/projects/{project}/source/import", files={"file": ("book.txt", text.encode(), "text/plain")}, data={"rightsAcknowledged": "true"}).json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"
    return project


def extract(client, project: str) -> None:
    job = client.post(f"/api/v1/projects/{project}/structure/extract", json={"maxSegmentChars": 120}).json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"


def test_heading_scene_and_sentence_safe_segments(client) -> None:
    project = project_with_source(client, "Chapter 1: Arrival\n\nMara arrived. Theo said hello.\n\n***\n\nA second scene begins. It ends here.\n\nChapter 2: Night\n\nFinal sentence.")
    extract(client, project)
    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    assert len(chapters) == 2 and chapters[0]["status"] == "structured"
    scenes = client.get(f"/api/v1/chapters/{chapters[0]['id']}/scenes").json()
    assert len(scenes) == 2
    segments = client.get(f"/api/v1/scenes/{scenes[0]['id']}/segments").json()
    assert all(item["textContent"][-1] in ".!?" for item in segments)
    assert any(item["speakerCandidate"] == "Theo" for item in segments)


def test_unresolved_structure_and_segment_revision_history(client) -> None:
    project = project_with_source(client, "A single paragraph with no heading. Another complete sentence.")
    extract(client, project)
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    assert chapter["status"] == "unresolved"
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segment = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()[0]
    edited = client.patch(f"/api/v1/segments/{segment['id']}", json={"textContent": "Corrected sentence."}).json()
    assert edited["revision"] == 2 and edited["status"] == "needs_review"
    revisions = client.get(f"/api/v1/segments/{segment['id']}/revisions").json()
    assert revisions[0]["revision"] == 1


def test_structure_parser_v2_front_matter_dialogue_and_warnings(client) -> None:
    project = project_with_source(
        client,
        "Dedication\n\n# Prologue\n\n[softly]\n\n\"Hello,\" she said.\n\nScene 2\n\nMara: We go.\n\nChapter 1: Start\n\nA final sentence.",
    )
    extract(client, project)

    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    assert [chapter["title"] for chapter in chapters][:2] == ["Front matter", "Prologue"]
    assert chapters[0]["status"] == "front_matter"
    warnings = client.get(f"/api/v1/projects/{project}/structure-warnings").json()
    assert any("Dialogue segment" in warning["message"] for warning in warnings)

    scenes = client.get(f"/api/v1/chapters/{chapters[1]['id']}/scenes").json()
    segments = [item for scene in scenes for item in client.get(f"/api/v1/scenes/{scene['id']}/segments").json()]
    assert any(item["segmentType"] == "performance_beat" for item in segments)
    assert any(item["segmentType"] == "dialogue" and item["speakerCandidate"] == "Mara" for item in segments)
    assert all("parserEvidence" in item for item in segments)


def test_segment_split_merge_and_lock_survives_reextract(client) -> None:
    project = project_with_source(
        client,
        "Chapter 1\n\nA first sentence that is long enough to split near the middle. A second sentence follows for merging.",
    )
    extract(client, project)
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    target = segments[0]

    split_offset = target["textContent"].index(" enough")
    split = client.post(
        f"/api/v1/segments/{target['id']}/split", json={"splitOffset": split_offset}
    )
    assert split.status_code == 200
    split_segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert len(split_segments) == len(segments) + 1

    merged = client.post(
        f"/api/v1/segments/{split_segments[0]['id']}/merge",
        json={"nextSegmentId": split_segments[1]["id"]},
    )
    assert merged.status_code == 200
    merged_segment = merged.json()
    locked = client.put(
        f"/api/v1/structure-locks/segment/{merged_segment['id']}",
        json={"locked": True, "reason": "Keep editorial split"},
    ).json()
    assert locked["userLocked"] is True

    extract(client, project)
    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    scenes = [scene for chapter in chapters for scene in client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()]
    all_segments = [
        segment
        for scene in scenes
        for segment in client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    ]
    assert any(
        segment["id"] == merged_segment["id"] and segment["userLocked"]
        for segment in all_segments
    )
