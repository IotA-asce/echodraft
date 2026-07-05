import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from audio_fixtures import wav_bytes_from_segments
from echodraft_api.rendering import SegmentRenderer
from echodraft_api import review as review_module
from echodraft_api.review import ReviewService
from echodraft_db.models import SegmentRenderRecord
from echodraft_domain import SegmentRenderRequest
from sqlalchemy import select


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


def test_segment_render_metadata_carries_real_audio_telemetry(client) -> None:
    project, _, segment = prepared_segment(client)
    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=render_payload(project)
    ).json()
    metadata = json.loads(Path(rendered["metadataPath"]).read_text(encoding="utf-8"))

    # The mock provider always writes pure digital silence, so an honest analysis floors
    # peak at -120 dBFS -- a real float, never the old hardcoded literal `0`.
    assert metadata["peak"] == -120.0
    assert isinstance(metadata["peak"], float)
    assert len(metadata["waveform"]) == 200
    assert metadata["silenceRanges"] == [[0, rendered["durationMs"]]]


def test_concurrent_forced_renders_keep_a_linear_chain(app, client) -> None:
    project, _, segment = prepared_segment(client)
    renderer = SegmentRenderer(app.state.container)
    request = SegmentRenderRequest.model_validate(
        {
            "voiceProfileId": "voice_test",
            "direction": {"scopeType": "project", "scopeId": project},
            "force": True,
        }
    )
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def run() -> None:
        try:
            barrier.wait()
            renderer.render(project, segment, request)
        except Exception as exc:  # noqa: BLE001 - test captures any failure for assertion
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert not any("database is locked" in str(error).lower() for error in errors)

    with app.state.container.structure.database.session() as session:
        records = list(
            session.scalars(
                select(SegmentRenderRecord).where(
                    SegmentRenderRecord.segment_id == segment,
                    SegmentRenderRecord.status == "succeeded",
                )
            )
        )
    assert len(records) == 2
    roots = [record for record in records if record.parent_render_id is None]
    assert len(roots) == 1, "forked append-only chain: expected exactly one root render"
    parents = [record.parent_render_id for record in records if record.parent_render_id]
    assert len(parents) == len(set(parents)), "forked chain: two renders share a parent"


def test_qa_issues_are_durable_and_deduplicated_per_render(client) -> None:
    project, _, segment = prepared_segment(client)
    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=render_payload(project)
    )
    assert rendered.status_code == 202
    issues = client.get(f"/api/v1/projects/{project}/issues?segment_id={segment}").json()
    # The mock provider's render is pure digital silence for its whole (short) duration, so
    # the honest real-analysis finding is "too quiet" (rms floors at -120 dBFS). It is too
    # short for any window to qualify as a >=3s interior dead-air run, so `excessive_silence`
    # / `dead_air` do not fire here (covered separately below with fabricated WAVs long
    # enough to contain a real interior dead-air stretch).
    low_loudness = [item for item in issues if item["category"] == "low_loudness"]
    assert len(low_loudness) == 1

    # Re-reading the queue never produces another QA finding for the same render revision.
    assert (
        len(
            [
                item
                for item in client.get(f"/api/v1/projects/{project}/issues").json()
                if item["id"] == low_loudness[0]["id"]
            ]
        )
        == 1
    )


def test_asr_pass_updates_render_metadata_without_issue(client, monkeypatch) -> None:
    class PassingVerifier:
        def __init__(self, _settings) -> None:
            pass

        def configured(self) -> bool:
            return True

        def verify(self, _audio_path, _expected_text, _output_root):
            return SimpleNamespace(
                status="passed",
                error=None,
                evidence={
                    "reason": "asr_word_match",
                    "status": "passed",
                    "matchRatio": 1.0,
                    "wordErrorRate": 0.0,
                    "expectedPreview": "A reviewable sentence.",
                    "transcriptPreview": "A reviewable sentence.",
                    "provider": "test-asr",
                    "model": "test.bin",
                },
            )

    monkeypatch.setattr(review_module, "LocalAsrVerifier", PassingVerifier)
    project, _, segment = prepared_segment(client)

    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=render_payload(project)
    ).json()

    metadata = json.loads(Path(rendered["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["asrVerification"]["status"] == "passed"
    assert metadata["asrVerification"]["segmentRenderId"] == rendered["id"]
    issues = client.get(f"/api/v1/projects/{project}/issues?segment_id={segment}").json()
    assert not [issue for issue in issues if issue["category"] == "asr_word_mismatch"]


def test_asr_mismatch_creates_review_issue_with_evidence(client, monkeypatch) -> None:
    class FailingVerifier:
        def __init__(self, _settings) -> None:
            pass

        def configured(self) -> bool:
            return True

        def verify(self, _audio_path, _expected_text, _output_root):
            return SimpleNamespace(
                status="failed",
                error=None,
                evidence={
                    "reason": "asr_word_match",
                    "status": "failed",
                    "matchRatio": 0.5,
                    "wordErrorRate": 0.5,
                    "missingWords": ["reviewable"],
                    "extraWords": ["different"],
                    "expectedPreview": "A reviewable sentence.",
                    "transcriptPreview": "A different sentence.",
                    "provider": "test-asr",
                    "model": "test.bin",
                },
            )

    monkeypatch.setattr(review_module, "LocalAsrVerifier", FailingVerifier)
    project, _, segment = prepared_segment(client)

    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=render_payload(project)
    ).json()

    issues = client.get(f"/api/v1/projects/{project}/issues?segment_id={segment}").json()
    mismatch = next(issue for issue in issues if issue["category"] == "asr_word_mismatch")
    assert mismatch["metadata"]["segmentRenderId"] == rendered["id"]
    assert mismatch["metadata"]["matchRatio"] == 0.5
    assert mismatch["metadata"]["missingWords"] == ["reviewable"]


def test_patch_auto_resolves_render_qa_issue_when_new_render_passes(client, app) -> None:
    project, _, segment = prepared_segment(client)
    original = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/generate", json=render_payload(project)
    ).json()

    # Model a render-QA finding that a re-render genuinely fixes. The mock TTS provider only
    # ever emits `low_loudness` (its audio is always pure silence), so it can never make a
    # render-QA issue of some other category disappear; we therefore seed a
    # `very_short_duration` finding with the exact shape `qa_segment` produces (a
    # `segmentRenderId` in metadata) pinned to the render.
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


def test_create_issue_dedupe_hit_refreshes_fields_but_preserves_identity(client, app) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Dedupe Refresh", "rightsStatus": "declared"}
    ).json()["id"]
    review = app.state.container.review
    key = "readiness:proj-1:chapter-1:structure_segments"

    first = review.create_issue(
        project_id=project,
        category="readiness_structure",
        severity="warning",
        title="Empty segments",
        description="1 segment has no renderable text.",
        metadata={"reason": "empty"},
        dedupe_key=key,
    )
    assert first.severity == "warning"
    assert first.status == "open"

    # Simulate an issue a reviewer has already triaged: its status must survive a
    # dedupe-hit refresh even though the underlying check's failure mode changes.
    review.update_issue(first.id, status="ignored", severity=None)
    before = review.issue(first.id)
    assert before is not None

    second = review.create_issue(
        project_id=project,
        category="readiness_structure",
        severity="blocking",
        title="No renderable segments",
        description="Chapters need scenes and segments before production.",
        metadata={"reason": "missing"},
        dedupe_key=key,
    )

    # Same row, same identity/creation time -- but the content now reflects the new
    # (more severe) failure mode instead of staying frozen at first creation.
    assert second.id == before.id
    assert second.created_at == before.created_at
    assert second.severity == "blocking"
    assert second.title == "No renderable segments"
    assert second.description == "Chapters need scenes and segments before production."
    assert json.loads(second.metadata_json) == {"reason": "missing"}
    # Status is a reviewer decision, not a check output -- it must not be reset to "open".
    assert second.status == "ignored"


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


def test_patch_with_only_voice_supplied_does_not_require_a_narrator(client) -> None:
    """A half-supplied patch payload (voice given, direction omitted) must resolve each
    field independently: supplying the voice explicitly should not force the direction
    resolution path to also need a configured narrator voice. No narrator is ever
    configured in this project.
    """
    project, _, segment = prepared_segment(client)
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()

    patched = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/patch",
        json={"voiceProfileId": voice["id"]},
    )
    assert patched.status_code == 202, patched.text
    render = patched.json()["render"]
    metadata = json.loads(Path(render["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["voiceProfileId"] == voice["id"]


def test_patch_with_neither_voice_nor_direction_still_requires_a_narrator(client) -> None:
    project, _, segment = prepared_segment(client)

    patched = client.post(
        f"/api/v1/projects/{project}/segments/{segment}/patch",
        json={},
    )
    assert patched.status_code == 422
    assert "narrator voice" in patched.json()["detail"]


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


# --- `ReviewService._audio_rules` unit coverage -----------------------------------------
# These call the rule function directly against fabricated WAVs (no HTTP/DB round trip) so
# each real metric can be isolated precisely, per docs/plans/2026-07-04-phase-2-publishable-
# audio.md Task B2.


def test_audio_rules_flags_clipping_above_threshold(tmp_path) -> None:
    path = tmp_path / "clip.wav"
    path.write_bytes(wav_bytes_from_segments([(32_760, 50)], sample_rate=16_000))
    categories = {category for category, _, _ in ReviewService._audio_rules(path, 50)}
    assert "clipping" in categories


def test_audio_rules_does_not_flag_isolated_clipped_samples(tmp_path) -> None:
    # A handful of near-full-scale samples (inter-sample rounding) must not trip clipping;
    # only clipped_sample_count > 8 does. At 8000 Hz, 1 ms is exactly 8 frames -- right at
    # (not over) the threshold.
    path = tmp_path / "near-clip.wav"
    path.write_bytes(wav_bytes_from_segments([(32_760, 1), (100, 200)], sample_rate=8_000))
    categories = {category for category, _, _ in ReviewService._audio_rules(path, 201)}
    assert "clipping" not in categories


def test_audio_rules_flags_low_loudness_for_quiet_audio(tmp_path) -> None:
    path = tmp_path / "quiet.wav"
    path.write_bytes(wav_bytes_from_segments([(50, 1000)], sample_rate=16_000))
    categories = {category for category, _, _ in ReviewService._audio_rules(path, 1000)}
    assert "low_loudness" in categories
    assert "excessive_silence" not in categories


def test_audio_rules_flags_high_loudness_for_hot_audio(tmp_path) -> None:
    path = tmp_path / "hot.wav"
    path.write_bytes(wav_bytes_from_segments([(30_000, 1000)], sample_rate=16_000))
    categories = {category for category, _, _ in ReviewService._audio_rules(path, 1000)}
    assert "high_loudness" in categories


def test_audio_rules_flags_dead_air_and_excessive_silence_for_long_interior_gap(
    tmp_path,
) -> None:
    # A 6s interior gap (not touching either end) is both a `dead_air` finding and enough
    # of the file (75%) to be `excessive_silence` too.
    data = wav_bytes_from_segments(
        [(16_000, 1000), (0, 6000), (16_000, 1000)], sample_rate=16_000
    )
    path = tmp_path / "deadair.wav"
    path.write_bytes(data)
    categories = {category for category, _, _ in ReviewService._audio_rules(path, 8000)}
    assert "dead_air" in categories
    assert "excessive_silence" in categories


def test_audio_rules_does_not_flag_head_tail_room_tone_as_dead_air(tmp_path) -> None:
    data = wav_bytes_from_segments(
        [(0, 4000), (16_000, 1000), (0, 4000)], sample_rate=16_000
    )
    path = tmp_path / "roomtone.wav"
    path.write_bytes(data)
    categories = {category for category, _, _ in ReviewService._audio_rules(path, 9000)}
    assert "dead_air" not in categories
    assert "excessive_silence" not in categories


def test_audio_rules_flags_truncation_suspected_for_long_text_short_audio(tmp_path) -> None:
    long_text = "x" * 100  # > 40 chars; floor = 100/30*1000 ~= 3333ms, half ~= 1667ms
    path = tmp_path / "short.wav"
    path.write_bytes(wav_bytes_from_segments([(16_000, 300)], sample_rate=16_000))
    categories = {
        category for category, _, _ in ReviewService._audio_rules(path, 300, long_text)
    }
    assert "truncation_suspected" in categories


def test_audio_rules_does_not_flag_truncation_for_normal_ratio(tmp_path) -> None:
    long_text = "x" * 100
    path = tmp_path / "normal.wav"
    path.write_bytes(wav_bytes_from_segments([(16_000, 4000)], sample_rate=16_000))
    categories = {
        category for category, _, _ in ReviewService._audio_rules(path, 4000, long_text)
    }
    assert "truncation_suspected" not in categories


def test_audio_rules_does_not_flag_truncation_for_short_text(tmp_path) -> None:
    # Text at/under the 40-char floor never triggers truncation, however short the audio.
    short_text = "x" * 30
    path = tmp_path / "tiny.wav"
    path.write_bytes(wav_bytes_from_segments([(16_000, 50)], sample_rate=16_000))
    categories = {
        category for category, _, _ in ReviewService._audio_rules(path, 50, short_text)
    }
    assert "truncation_suspected" not in categories
