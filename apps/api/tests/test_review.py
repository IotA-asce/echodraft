import time


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(60):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def prepared_segment(client) -> tuple[str, str, str]:
    project = client.post(
        "/api/v1/projects", json={"title": "Review", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"A reviewable sentence.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    extracted = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, extracted["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene_id = client.get(f"/api/v1/chapters/{chapter_id}/scenes").json()[0]["id"]
    segment_id = client.get(f"/api/v1/scenes/{scene_id}/segments").json()[0]["id"]
    return project, chapter_id, segment_id


def render_payload(project: str) -> dict:
    return {
        "voiceProfileId": "voice_test",
        "direction": {"scopeType": "project", "scopeId": project},
    }


def test_qa_issues_are_durable_and_deduplicated_per_render(client) -> None:
    project, _, segment = prepared_segment(client)
    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=render_payload(project)
    )
    assert rendered.status_code == 202
    issues = client.get(f"/api/v1/projects/{project}/issues?segment_id={segment}").json()
    silence = [item for item in issues if item["category"] == "excessive_silence"]
    assert len(silence) == 1

    # Re-reading the queue never produces another QA finding for the same render revision.
    assert (
        len(
            [
                item
                for item in client.get(f"/api/v1/projects/{project}/issues").json()
                if item["id"] == silence[0]["id"]
            ]
        )
        == 1
    )


def test_issue_comment_and_selective_patch_preserve_render_history(client) -> None:
    project, chapter, segment = prepared_segment(client)
    original = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=render_payload(project)
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project}/issues",
        json={
            "segmentId": segment,
            "category": "editorial",
            "severity": "warning",
            "title": "Pacing",
            "description": "Tighten this line.",
        },
    ).json()
    comment = client.post(
        f"/api/v1/issues/{issue['id']}/comments", json={"body": "Patch the wording."}
    )
    assert comment.status_code == 201
    assert (
        client.patch(f"/api/v1/issues/{issue['id']}", json={"status": "resolved"}).json()["status"]
        == "resolved"
    )

    patched = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/patch",
        json={
            **render_payload(project),
            "textContent": "A newly patched reviewable sentence.",
            "issueId": issue["id"],
        },
    )
    assert patched.status_code == 202, patched.text
    result = patched.json()
    assert result["segment"]["revision"] == 2
    assert result["render"]["parentRenderId"] == original["id"]
    assert result["chapterRender"]["chapterId"] == chapter
    assert len(client.get(f"/api/v1/projects/{project}/chapters/{chapter}/renders").json()) == 1
