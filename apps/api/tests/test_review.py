import json
import time
from pathlib import Path


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


def test_patch_auto_resolves_render_qa_issue_when_new_render_passes(client, app) -> None:
    project, _, segment = prepared_segment(client)
    original = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=render_payload(project)
    ).json()

    # Model a render-QA finding that a re-render genuinely fixes. The mock TTS provider only
    # ever emits `excessive_silence` (its audio is always pure silence), so it can never make
    # a render-QA issue disappear; we therefore seed a `very_short_duration` finding with the
    # exact shape `qa_segment` produces (a `segmentRenderId` in metadata) pinned to the render.
    seeded = app.state.container.review.create_issue(
        project_id=project,
        segment_id=segment,
        category="very_short_duration",
        severity="warning",
        title="Very Short Duration",
        description="Audio is shorter than 250 ms.",
        metadata={"segmentRenderId": original["id"]},
        dedupe_key=f"segment:{original['id']}:very_short_duration",
    )
    assert seeded.status == "open"

    patched = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/patch",
        json={
            **render_payload(project),
            "textContent": "A much longer reviewable sentence produced by the corrective patch.",
            "issueId": seeded.id,
        },
    )
    assert patched.status_code == 202, patched.text
    new_render_id = patched.json()["render"]["id"]

    resolved = next(
        item
        for item in client.get(f"/api/v1/projects/{project}/issues").json()
        if item["id"] == seeded.id
    )
    assert resolved["status"] == "resolved"
    assert resolved["metadata"]["resolvedBy"] == "rerender"
    assert resolved["metadata"]["newRenderId"] == new_render_id


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
    manifest = json.loads(Path(result["chapterRender"]["manifestPath"]).read_text())
    stitched = {item["segmentId"]: item["segmentRenderId"] for item in manifest["inputs"]}
    assert stitched[segment] == result["render"]["id"]


def test_segment_review_inspector_layers_patch_history_and_waveform(client) -> None:
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
            "title": "Line note",
            "description": "Review this segment in the patch workbench.",
        },
    ).json()
    client.post(
        f"/api/v1/issues/{issue['id']}/comments", json={"body": "Patch attempt requested."}
    )
    patched = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/patch",
        json={
            **render_payload(project),
            "textContent": "A patched reviewable sentence.",
            "issueId": issue["id"],
        },
    ).json()

    inspector = client.get(
        f"/api/v1/projects/{project}/segments/{segment}/review-inspector"
    ).json()

    assert inspector["chapterId"] == chapter
    assert inspector["segment"]["revision"] == 2
    assert inspector["sourceText"] == "A patched reviewable sentence."
    assert inspector["canonicalText"] == "A patched reviewable sentence."
    assert inspector["structure"]["segment"]["id"] == segment
    assert {item["id"] for item in inspector["renderHistory"]} == {
        original["id"],
        patched["render"]["id"],
    }
    assert inspector["waveform"]["durationMs"] == patched["render"]["durationMs"]
    assert any(item["id"] == issue["id"] for item in inspector["qaIssues"])
    assert any(item["body"] == "Patch attempt requested." for item in inspector["comments"])
    assert inspector["patchQueue"][0]["newRenderId"] == patched["render"]["id"]


def test_segment_revision_stales_only_the_edited_render(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Selective stale", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                b"Chapter 1\n\nFirst reviewable paragraph.\n\nSecond reviewable paragraph.",
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    extracted = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, extracted["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene = client.get(f"/api/v1/chapters/{chapter}/scenes").json()[0]["id"]
    segments = client.get(f"/api/v1/scenes/{scene}/segments").json()
    assert len(segments) == 2
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
    before = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/production-status").json()
    assert before["currentSegments"] == 2

    client.patch(
        f"/api/v1/segments/{segments[0]['id']}",
        json={"textContent": "First reviewable paragraph, revised locally."},
    )
    after = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/production-status").json()
    assert after["totalSegments"] == 2
    assert after["currentSegments"] == 1


def test_patch_with_only_issue_id_resolves_voice_and_forces_fresh_render(client) -> None:
    project, _, segment = prepared_segment(client)
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )
    # Same voice and blank direction the server will resolve to on patch: this isolates the
    # "force" behaviour, since nothing about the effective render inputs actually changes.
    original = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate",
        json={
            "voiceProfileId": voice["id"],
            "direction": {"scopeType": "segment", "scopeId": segment},
        },
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project}/issues",
        json={
            "segmentId": segment,
            "category": "editorial",
            "severity": "warning",
            "title": "Pacing",
            "description": "Needs another pass.",
        },
    ).json()

    patched = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/patch",
        json={"issueId": issue["id"]},
    )
    assert patched.status_code == 202, patched.text
    result = patched.json()
    assert result["render"]["id"] != original["id"]
    assert result["render"]["parentRenderId"] == original["id"]


def test_patch_without_voice_resolves_to_cast_voice_not_narrator(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Cast Patch", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    narrator_voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    mara_voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Mara", "backend": "mock", "providerVoiceId": "mock-mara"},
    ).json()
    character = client.post(
        f"/api/v1/projects/{project}/characters",
        json={"displayName": "Mara", "aliases": ["Captain Vale"]},
    ).json()
    client.patch(
        f"/api/v1/characters/{character['id']}",
        json={"voiceProfileId": mara_voice["id"]},
    )
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": narrator_voice["id"]},
    )
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "cast.txt",
                b"Chapter 1\n\nMara: We leave now.\n\n\"Who is there?\"\n\nThe rain answered.",
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"

    attribution_job = client.post(
        f"/api/v1/projects/{project}/speaker-attributions/run", json={}
    ).json()
    assert wait_for_job(client, attribution_job["id"])["status"] == "succeeded"

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    dialogue_segment = next(item for item in segments if item["speakerCandidate"] == "Mara")

    # Give every segment a successful render (so chapter assembly has inputs), then
    # deliberately re-render the dialogue segment with the wrong (narrator) voice to
    # simulate a stale/incorrect render that the patch should correct.
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter['id']}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"
    original = client.post(
        f"/api/v1/projects/{project}/segments/{dialogue_segment['id']}/generate",
        json={
            "voiceProfileId": narrator_voice["id"],
            "direction": {"scopeType": "segment", "scopeId": dialogue_segment["id"]},
            "force": True,
        },
    ).json()
    issue = client.post(
        f"/api/v1/projects/{project}/issues",
        json={
            "segmentId": dialogue_segment["id"],
            "category": "editorial",
            "severity": "warning",
            "title": "Cast check",
            "description": "Confirm cast voice on patch.",
        },
    ).json()

    patched = client.post(
        f"/api/v1/projects/{project}/segments/{dialogue_segment['id']}/patch",
        json={"issueId": issue["id"]},
    )
    assert patched.status_code == 202, patched.text
    render = patched.json()["render"]
    assert render["id"] != original["id"]
    metadata = json.loads(Path(render["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["voiceProfileId"] == mara_voice["id"]


def test_patch_without_direction_resolves_saved_segment_direction(client) -> None:
    project, _, segment = prepared_segment(client)
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )
    client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate",
        json={
            "voiceProfileId": voice["id"],
            "direction": {"scopeType": "segment", "scopeId": segment},
        },
    )
    client.put(
        f"/api/v1/projects/{project}/segments/{segment}/direction",
        json={
            "direction": {"scopeType": "segment", "scopeId": segment, "pace": 1.3},
            "userLocked": True,
        },
    )
    issue = client.post(
        f"/api/v1/projects/{project}/issues",
        json={
            "segmentId": segment,
            "category": "editorial",
            "severity": "warning",
            "title": "Pacing note",
            "description": "Apply the saved direction on patch.",
        },
    ).json()

    patched = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/patch",
        json={"issueId": issue["id"]},
    )
    assert patched.status_code == 202, patched.text
    render = patched.json()["render"]
    metadata = json.loads(Path(render["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["direction"]["pace"] == 1.3
