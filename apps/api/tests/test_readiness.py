import time
from pathlib import Path
from types import SimpleNamespace

from audio_fixtures import wav_bytes_from_segments
from echodraft_api import readiness as readiness_module
from echodraft_api import review as review_module
from echodraft_db.models import ChapterRenderRecord


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def structured_project(client) -> tuple[str, str]:
    project = client.post(
        "/api/v1/projects", json={"title": "Readiness", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("ready.txt", b"Chapter 1\n\nReady checks need audio.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    return project, chapter


def produced_chapter(client) -> tuple[str, str]:
    """A structured project with a real (mock-provider) chapter audio render."""
    project, chapter = structured_project(client)
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
    return project, chapter


def test_readiness_report_persists_checks_and_accepted_risk_is_counted(client) -> None:
    project, chapter = structured_project(client)

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    assert report["status"] == "blocked"
    assert report["chapterId"] == chapter
    categories = {check["category"] for check in report["checks"]}
    assert "readiness_voice" in categories
    assert "readiness_audio" in categories
    voice_check = next(check for check in report["checks"] if check["id"] == "voice_narrator")
    assert voice_check["issueId"]
    assert voice_check["resolutionStatus"] == "open"

    # "Ignore" == accept-risk: the check stays visible and is counted under "accepted",
    # but no longer inflates the blocking count. It is not silently gone.
    client.patch(f"/api/v1/issues/{voice_check['issueId']}", json={"status": "ignored"})
    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    rerun_voice = next(check for check in rerun["checks"] if check["id"] == "voice_narrator")
    assert rerun_voice["issueId"] == voice_check["issueId"]
    assert rerun_voice["resolutionStatus"] == "ignored"

    assert rerun["summary"]["accepted"] == 1
    active_blocking = [
        check
        for check in rerun["checks"]
        if check["status"] != "passed"
        and check["severity"] == "blocking"
        and check["resolutionStatus"] in (None, "open")
    ]
    assert rerun["summary"]["blocking"] == len(active_blocking)
    assert all(check["id"] != "voice_narrator" for check in active_blocking)

    latest = client.get(
        f"/api/v1/projects/{project}/readiness/latest?chapter_id={chapter}"
    ).json()
    assert latest["id"] == rerun["id"]
    history = client.get(f"/api/v1/projects/{project}/readiness/reports").json()
    assert [item["id"] for item in history][:2] == [rerun["id"], report["id"]]


def test_readiness_reopens_resolved_but_still_failing_check(client) -> None:
    project, chapter = structured_project(client)

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    voice_check = next(check for check in report["checks"] if check["id"] == "voice_narrator")
    issue_id = voice_check["issueId"]

    # A "resolved" mark is only a claim. The narrator voice is still missing, so the next
    # run must re-verify it and reopen the check instead of hiding it forever.
    assert (
        client.patch(f"/api/v1/issues/{issue_id}", json={"status": "resolved"}).json()["status"]
        == "resolved"
    )
    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()

    rerun_voice = next(check for check in rerun["checks"] if check["id"] == "voice_narrator")
    assert rerun_voice["issueId"] == issue_id
    assert rerun_voice["resolutionStatus"] == "open"
    assert rerun_voice["metadata"]["reopened"] is True

    issue = next(
        item
        for item in client.get(f"/api/v1/projects/{project}/issues").json()
        if item["id"] == issue_id
    )
    assert issue["status"] == "open"
    assert rerun["status"] == "blocked"
    assert rerun["score"] < 100


def test_readiness_auto_resolves_a_check_that_now_passes(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Auto Resolve", "rightsStatus": "declared"}
    ).json()["id"]
    narrator_voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": narrator_voice["id"]},
    )
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("cast.txt", b"Chapter 1\n\nMara: Go now.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    coverage = next(
        check for check in report["checks"] if check["id"] == "voice_character_coverage"
    )
    assert coverage["status"] == "failed"
    assert coverage["resolutionStatus"] == "open"
    issue_id = coverage["issueId"]

    # Fix the underlying condition: give the detected character a voice.
    character_voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Mara", "backend": "mock", "providerVoiceId": "mock-mara"},
    ).json()
    character = client.get(f"/api/v1/projects/{project}/characters").json()[0]
    client.patch(
        f"/api/v1/characters/{character['id']}",
        json={"voiceProfileId": character_voice["id"]},
    )

    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    rerun_coverage = next(
        check for check in rerun["checks"] if check["id"] == "voice_character_coverage"
    )
    assert rerun_coverage["status"] == "passed"

    issue = next(
        item
        for item in client.get(f"/api/v1/projects/{project}/issues").json()
        if item["id"] == issue_id
    )
    assert issue["status"] == "resolved"


def test_readiness_auto_resolves_narrator_check_across_fail_reasons(client) -> None:
    """Regression test: the narrator check used to emit "voice_narrator_missing"
    while failing but "voice_narrator" while passing, so the auto-resolve-on-pass
    lookup (keyed on the passing draft's id) could never find the failing issue and
    it lingered "open" forever. The id must stay stable across the fail -> pass
    transition so the SAME issue row is auto-resolved once the narrator voice is set.
    """
    project, chapter = structured_project(client)

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    voice_check = next(check for check in report["checks"] if check["id"] == "voice_narrator")
    assert voice_check["status"] == "failed"
    assert voice_check["metadata"]["reason"] == "missing"
    assert voice_check["resolutionStatus"] == "open"
    issue_id = voice_check["issueId"]
    assert issue_id

    # Fix the underlying condition via the API: configure a narrator voice.
    narrator_voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": narrator_voice["id"]},
    )

    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    rerun_voice = next(check for check in rerun["checks"] if check["id"] == "voice_narrator")
    assert rerun_voice["status"] == "passed"

    issue = next(
        item
        for item in client.get(f"/api/v1/projects/{project}/issues").json()
        if item["id"] == issue_id
    )
    assert issue["status"] == "resolved"


def test_readiness_reports_cast_voice_coverage_and_narrator_fallback(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Voice Coverage", "rightsStatus": "declared"}
    ).json()["id"]
    narrator_voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": narrator_voice["id"]},
    )
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("cast.txt", b"Chapter 1\n\nMara: Go now.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()

    character_check = next(
        check for check in report["checks"] if check["id"] == "voice_character_coverage"
    )
    fallback_check = next(
        check for check in report["checks"] if check["id"] == "voice_narrator_fallback_rows"
    )
    assert character_check["metadata"]["charactersDetected"] == 1
    assert character_check["metadata"]["charactersVoiced"] == 0
    assert fallback_check["metadata"]["narratorFallbackRows"] == 1


def test_readiness_auto_resolves_stale_render_check(client) -> None:
    project, chapter = produced_chapter(client)
    scene = client.get(f"/api/v1/chapters/{chapter}/scenes").json()[0]["id"]
    segment = client.get(f"/api/v1/scenes/{scene}/segments").json()[0]["id"]
    stale_id = f"stale_render_{chapter}"

    # Editing the segment's text without re-rendering makes the chapter's produced audio
    # stale relative to the current segment content.
    client.patch(
        f"/api/v1/segments/{segment}",
        json={"textContent": "Ready checks need audio, revised for staleness."},
    )

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    stale_check = next(check for check in report["checks"] if check["id"] == stale_id)
    assert stale_check["status"] == "failed"
    issue_id = stale_check["issueId"]
    assert issue_id

    # Re-produce so the segment's render catches up with its current text.
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"

    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    rerun_stale = next(check for check in rerun["checks"] if check["id"] == stale_id)
    assert rerun_stale["status"] == "passed"

    issue = next(
        item
        for item in client.get(f"/api/v1/projects/{project}/issues").json()
        if item["id"] == issue_id
    )
    assert issue["status"] == "resolved"


def test_readiness_auto_resolves_segment_audio_missing_check(client) -> None:
    project, chapter = structured_project(client)
    check_id = "segment_audio_missing"

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    check = next(item for item in report["checks"] if item["id"] == check_id)
    assert check["status"] == "failed"
    issue_id = check["issueId"]
    assert issue_id

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

    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    rerun_check = next(item for item in rerun["checks"] if item["id"] == check_id)
    assert rerun_check["status"] == "passed"

    issue = next(
        item
        for item in client.get(f"/api/v1/projects/{project}/issues").json()
        if item["id"] == issue_id
    )
    assert issue["status"] == "resolved"


def _asr_verifier(status: str):
    class FakeVerifier:
        def __init__(self, _settings) -> None:
            pass

        def configured(self) -> bool:
            return True

        def verify(self, _audio_path, _expected_text, _output_root):
            match_ratio = 1.0 if status == "passed" else 0.5
            return SimpleNamespace(
                status=status,
                error=None,
                evidence={
                    "reason": "asr_word_match",
                    "status": status,
                    "matchRatio": match_ratio,
                    "wordErrorRate": 1.0 - match_ratio,
                    "provider": "test-asr",
                    "model": "test.bin",
                    "expectedPreview": "Ready checks need audio.",
                    "transcriptPreview": "Ready checks need audio.",
                },
            )

    return FakeVerifier


def test_readiness_reports_asr_word_match_passed(client, monkeypatch) -> None:
    fake = _asr_verifier("passed")
    monkeypatch.setattr(review_module, "LocalAsrVerifier", fake)
    monkeypatch.setattr(readiness_module, "LocalAsrVerifier", fake)
    project, chapter = produced_chapter(client)

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()

    check = next(item for item in report["checks"] if item["id"] == "segment_asr_word_match")
    assert check["status"] == "passed"


def test_readiness_warns_on_asr_word_mismatch(client, monkeypatch) -> None:
    fake = _asr_verifier("failed")
    monkeypatch.setattr(review_module, "LocalAsrVerifier", fake)
    monkeypatch.setattr(readiness_module, "LocalAsrVerifier", fake)
    project, chapter = produced_chapter(client)

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()

    check = next(item for item in report["checks"] if item["id"] == "segment_asr_word_match")
    assert check["status"] == "failed"
    assert check["metadata"]["statusCounts"]["failed"] == 1
    assert check["resolutionStatus"] == "open"


def test_readiness_reports_chapter_audio_hot_and_dead_air_with_stable_ids(client, app) -> None:
    project, chapter = produced_chapter(client)
    active = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/active-render").json()
    render_id = active["id"]
    speech_path = Path(active["speechPath"])

    # Overwrite the real chapter audio with a fabricated signal that is both too hot (near
    # 0 dBFS, above the -3 dBFS mastering ceiling) and contains a genuine 4s interior dead-air
    # stretch, then keep the DB's declared duration honest for the swap.
    fabricated = wav_bytes_from_segments(
        [(30_000, 2000), (0, 4000), (30_000, 2000)], sample_rate=16_000
    )
    speech_path.write_bytes(fabricated)
    with app.state.container.structure.database.session() as session:
        record = session.get(ChapterRenderRecord, render_id)
        assert record is not None
        record.duration_ms = 8000
        session.commit()

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    hot_id = f"chapter_audio_hot_{chapter}"
    dead_air_id = f"chapter_audio_dead_air_{chapter}"
    hot_check = next(check for check in report["checks"] if check["id"] == hot_id)
    dead_air_check = next(check for check in report["checks"] if check["id"] == dead_air_id)
    assert hot_check["status"] == "failed"
    assert hot_check["severity"] == "warning"
    assert hot_check["metadata"]["reason"] == "hot"
    assert dead_air_check["status"] == "failed"
    assert dead_air_check["metadata"]["reason"] == "dead_air_detected"
    assert dead_air_check["metadata"]["deadAirRangeCount"] == 1

    # Same stable check ids across pass/fail (Task 3's convention): swap in quiet, gapless
    # audio of the same declared duration and confirm the identical ids now report "passed".
    quiet = wav_bytes_from_segments([(3_000, 8000)], sample_rate=16_000)
    speech_path.write_bytes(quiet)
    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    rerun_hot = next(check for check in rerun["checks"] if check["id"] == hot_id)
    rerun_dead_air = next(check for check in rerun["checks"] if check["id"] == dead_air_id)
    assert rerun_hot["status"] == "passed"
    assert rerun_dead_air["status"] == "passed"


def test_readiness_warns_until_active_chapter_render_is_approved(client) -> None:
    project, chapter = produced_chapter(client)

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    approval = next(check for check in report["checks"] if check["id"] == f"chapter_approval_{chapter}")
    assert approval["severity"] == "warning"
    assert approval["status"] == "failed"
    assert approval["metadata"]["reason"] == "approval_missing"

    client.post(
        f"/api/v1/projects/{project}/chapters/{chapter}/approval",
        json={"approvedBy": "qa"},
    )
    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    rerun_approval = next(
        check for check in rerun["checks"] if check["id"] == f"chapter_approval_{chapter}"
    )

    assert rerun_approval["status"] == "passed"
