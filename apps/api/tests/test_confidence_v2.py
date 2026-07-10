from __future__ import annotations

import time
from dataclasses import replace

from echodraft_api.confidence import classify_decision
from echodraft_api.config import AppSettings


def test_three_tier_classifier_is_stage_specific_and_lock_safe() -> None:
    assert classify_decision("attribution", 0.93).tier == "high"
    assert classify_decision("attribution", 0.8).tier == "mid"
    assert classify_decision("attribution", 0.61).tier == "flag"
    assert classify_decision("structure", 0.86).tier == "high"
    assert classify_decision("structure", 0.7).tier == "mid"

    locked = classify_decision("attribution", 0.1, user_locked=True)
    assert locked.tier is None
    assert locked.auto_accepted is False
    assert locked.should_queue is False


def test_vote_agreement_is_a_calibrated_confidence_signal() -> None:
    decision = classify_decision(
        "attribution",
        0.62,
        vote_tally={"char_mara": 3, "char_theo": 1},
    )

    assert decision.calibrated_confidence == 0.75
    assert decision.tier == "mid"
    assert decision.auto_accepted is True


def test_confidence_v2_flag_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("ECHODRAFT_CONFIDENCE_V2_ENABLED", "true")
    assert AppSettings.from_environment().confidence_v2_enabled is True


def test_low_attributions_fold_into_one_durable_review_task(client) -> None:
    container = client.app.state.container
    container.settings = replace(container.settings, confidence_v2_enabled=True)
    project = client.post(
        "/api/v1/projects",
        json={"title": "Grouped review", "rightsStatus": "declared"},
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                b'Chapter 1\n\nMara: Ready.\n\n"Who is there?"\n\n"Answer me."',
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert _wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(
        f"/api/v1/projects/{project}/structure/extract", json={}
    ).json()
    structured_job = _wait_for_job(client, structured["id"])
    assert structured_job["status"] == "succeeded", structured_job.get("errorMessage")

    tasks = client.get(f"/api/v1/projects/{project}/review-tasks").json()
    assert len(tasks) < 20
    attribution_tasks = [task for task in tasks if task["category"] == "attribution"]
    assert len(attribution_tasks) == 1
    task = attribution_tasks[0]
    assert task["memberCount"] >= 2

    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    flagged = [row for row in rows if row["decisionTier"] == "flag"]
    assert len(flagged) >= 2
    assert {row["reviewTaskId"] for row in flagged} == {task["id"]}
    assert all(row["autoAccepted"] is False for row in flagged)
    assert any(row["decisionTier"] == "high" for row in rows)

    rerun = client.post(
        f"/api/v1/projects/{project}/speaker-attributions/run", json={}
    ).json()
    assert _wait_for_job(client, rerun["id"])["status"] == "succeeded"
    refreshed = client.get(f"/api/v1/projects/{project}/review-tasks").json()
    refreshed_task = next(item for item in refreshed if item["id"] == task["id"])
    assert refreshed_task["memberCount"] == task["memberCount"]

    resolved = client.patch(
        f"/api/v1/review-tasks/{task['id']}", json={"status": "resolved"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def _wait_for_job(client, job_id: str) -> dict[str, object]:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")
