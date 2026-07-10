from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import echodraft_api.speaker_attribution as speaker_attribution_module
from echodraft_api.attribution_v2 import (
    AttributionVote,
    ConversationState,
    ResolvedTurn,
    alternation_repairs,
    majority_vote,
)
from echodraft_api.config import AppSettings


def test_majority_vote_uses_agreement_for_confidence_and_tally() -> None:
    decision = majority_vote(
        "seg_1",
        [
            AttributionVote("seg_1", "char_mara", "Mara", 0.61, "base"),
            AttributionVote("seg_1", "char_theo", "Theo", 0.72, "sample 1"),
            AttributionVote("seg_1", "char_theo", "Theo", 0.76, "sample 2"),
            AttributionVote("seg_1", "char_theo", "Theo", 0.7, "sample 3"),
        ],
    )

    assert decision.character_key == "char_theo"
    assert decision.speaker_name == "Theo"
    assert decision.method == "vote"
    assert decision.tally == {"char_mara": 1, "char_theo": 3}
    assert decision.confidence == 0.75


def test_majority_vote_tie_keeps_base_decision_conservatively() -> None:
    decision = majority_vote(
        "seg_1",
        [
            AttributionVote("seg_1", "char_mara", "Mara", 0.55, "base"),
            AttributionVote("seg_1", "char_theo", "Theo", 0.8, "sample"),
        ],
    )

    assert decision.character_key == "char_mara"
    assert decision.confidence == 0.55
    assert decision.method == "llm"


def test_conversation_state_tracks_last_speaker_parity_and_addressee() -> None:
    state = ConversationState(active_roster=("Mara", "Theo"))
    state = state.advance("Mara", open_addressee="Theo")
    state = state.advance("Theo")

    assert state.last_speaker == "Theo"
    assert state.turn_parity == 2
    assert state.open_addressee == "Theo"
    assert state.as_prompt_payload()["activeRoster"] == ["Mara", "Theo"]


def test_alternation_repair_changes_only_low_confidence_unlocked_turn() -> None:
    turns = [
        ResolvedTurn("seg_1", "scene_1", "Mara", 0.96),
        ResolvedTurn("seg_2", "scene_1", "Theo", 0.91),
        ResolvedTurn("seg_3", "scene_1", "Theo", 0.54),
        ResolvedTurn("seg_4", "scene_1", "Theo", 0.5, user_locked=True),
    ]

    repairs = alternation_repairs(turns, {"scene_1": ("Mara", "Theo")})

    assert [(repair.segment_id, repair.speaker_name) for repair in repairs] == [
        ("seg_3", "Mara")
    ]
    assert repairs[0].method == "reduce_repair"
    assert repairs[0].confidence == 0.82


def test_attribution_v2_flag_reads_both_environment_names(monkeypatch) -> None:
    monkeypatch.setenv("ECHODRAFT_ATTRIBUTION_V2_ENABLED", "true")
    assert AppSettings.from_environment().attribution_v2_enabled is True
    monkeypatch.delenv("ECHODRAFT_ATTRIBUTION_V2_ENABLED")
    monkeypatch.setenv("ECHODRAFT_ATTRIBUTION_V2", "1")
    assert AppSettings.from_environment().attribution_v2_enabled is True


def test_flagged_attribution_v2_votes_and_writes_manifest(client, monkeypatch) -> None:
    container = client.app.state.container
    project = client.post(
        "/api/v1/projects",
        json={"title": "Attribution v2", "rightsStatus": "declared"},
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                b'Chapter 1\n\nMara: Ready.\n\nThe room held still.\n\n"Again?"',
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert _wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(
        f"/api/v1/projects/{project}/structure/extract", json={}
    ).json()
    assert _wait_for_job(client, structured["id"])["status"] == "succeeded"
    client.post(f"/api/v1/projects/{project}/characters", json={"displayName": "Theo"})
    container.settings = replace(container.settings, attribution_v2_enabled=True)

    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    scenes = client.get(f"/api/v1/chapters/{chapters[0]['id']}/scenes").json()
    segments = client.get(f"/api/v1/scenes/{scenes[0]['id']}/segments").json()
    target = next(segment for segment in segments if "Again?" in segment["textContent"])
    captured_prompts: list[str] = []
    vote_calls = 0

    def fake_extract(_self, _project_id, request, _job_id=None, **_kwargs):
        nonlocal vote_calls
        captured_prompts.append(request.prompt or "")
        if request.task == "speaker_attribution_v2_vote":
            vote_calls += 1
            speaker = "Theo"
            confidence = 0.91
        else:
            speaker = "Mara"
            confidence = 0.42
        return SimpleNamespace(
            run=SimpleNamespace(id=f"llmrun_{len(captured_prompts)}"),
            result={
                "attributions": [
                    {
                        "segmentId": target["id"],
                        "characterId": speaker,
                        "speakerName": speaker,
                        "confidence": confidence,
                        "evidence": "scene conversation",
                    }
                ],
                "warnings": [],
            },
        )

    monkeypatch.setattr(
        speaker_attribution_module.LocalLlmService, "extract", fake_extract
    )
    rerun = client.post(
        f"/api/v1/projects/{project}/speaker-attributions/run",
        json={"useLocalLlm": True},
    ).json()
    assert _wait_for_job(client, rerun["id"])["status"] == "succeeded"

    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    resolved = next(row for row in rows if row["segmentId"] == target["id"])
    theo = next(
        character
        for character in client.get(f"/api/v1/projects/{project}/characters").json()
        if character["displayName"] == "Theo"
    )
    assert vote_calls == 3
    assert resolved["speakerName"] == "Theo"
    assert resolved["characterId"] == theo["id"]
    assert resolved["method"] == "vote"
    assert resolved["status"] == "approved"
    assert any("Conversation state" in prompt for prompt in captured_prompts)
    assert any("Deterministic candidates" in prompt for prompt in captured_prompts)

    project_record = container.projects.get(project)
    assert project_record is not None
    manifest = json.loads(
        (
            Path(project_record.artifact_path)
            / "manifests"
            / "attribution_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["manifestVersion"] == "attribution-v2"
    assert any(row["method"] == "vote" for row in manifest["payload"]["rows"])


def _wait_for_job(client, job_id: str) -> dict[str, object]:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")
