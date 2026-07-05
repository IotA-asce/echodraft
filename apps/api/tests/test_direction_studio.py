import json
import time
from pathlib import Path
from types import SimpleNamespace

from echodraft_api import direction as direction_module


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def project_with_segment(client) -> tuple[str, str, str]:
    project, chapter, _scene, segments = project_with_segments(
        client,
        b"Chapter 1\n\nHurry now! The signal is fading.\n\nThe rain softened.",
    )
    return project, chapter, segments[0]["id"]


def project_with_segments(client, text: bytes) -> tuple[str, str, str, list[dict]]:
    project = client.post(
        "/api/v1/projects", json={"title": "Direction Studio", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "direction.txt",
                text,
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene = client.get(f"/api/v1/chapters/{chapter}/scenes").json()[0]["id"]
    segments = client.get(f"/api/v1/scenes/{scene}/segments").json()
    return project, chapter, scene, segments


def direction(segment_id: str, emotion: str, intensity: float) -> dict:
    return {
        "scopeType": "segment",
        "scopeId": segment_id,
        "pace": 1.1,
        "intensity": intensity,
        "tone": emotion,
        "emotion": emotion,
        "pauseBeforeMs": 50,
        "pauseAfterMs": 180,
        "stylePrompt": f"{emotion} delivery",
        "emphasis": emotion == "urgent",
        "whisper": False,
        "noSfx": True,
    }


def test_segment_direction_changes_render_fingerprint(client) -> None:
    project, chapter, segment = project_with_segment(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )

    saved = client.put(
        f"/api/v1/projects/{project}/segments/{segment}/direction",
        json={"direction": direction(segment, "urgent", 0.8), "userLocked": True},
    ).json()
    assert saved["direction"]["emotion"] == "urgent"
    assert saved["userLocked"] is True
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"
    render = client.get(f"/api/v1/projects/{project}/segments/{segment}/renders").json()[0]
    metadata = json.loads(Path(render["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["direction"]["emotion"] == "urgent"
    assert metadata["direction"]["pauseAfterMs"] == 180
    status = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/production-status").json()
    assert status["currentSegments"] == status["totalSegments"]

    client.put(
        f"/api/v1/projects/{project}/segments/{segment}/direction",
        json={"direction": direction(segment, "quiet", 0.25), "userLocked": True},
    )
    stale_status = client.get(
        f"/api/v1/projects/{project}/chapters/{chapter}/production-status"
    ).json()
    assert stale_status["currentSegments"] == stale_status["totalSegments"] - 1

    inferred = client.post(f"/api/v1/projects/{project}/directions/infer", json={}).json()
    assert wait_for_job(client, inferred["id"])["status"] == "succeeded"
    locked_direction = client.get(
        f"/api/v1/projects/{project}/segments/{segment}/direction"
    ).json()
    assert locked_direction["direction"]["emotion"] == "quiet"


def test_direction_inference_without_payload_stays_deterministic(client) -> None:
    project, _chapter, segment = project_with_segment(client)

    inferred = client.post(f"/api/v1/projects/{project}/directions/infer").json()
    assert wait_for_job(client, inferred["id"])["status"] == "succeeded"

    row = client.get(f"/api/v1/projects/{project}/segments/{segment}/direction").json()
    assert row["source"] == "inferred"
    assert row["direction"]["emotion"] == "urgent"
    assert row["evidence"]["reason"] == "deterministic_direction_inference"


def test_llm_direction_inference_prompt_target_guard_and_evidence(client, monkeypatch) -> None:
    project, _chapter, _scene, segments = project_with_segments(
        client,
        b'Chapter 1\n\nMara: Hold the bridge.\n\n"Be quiet," Mara whispered.\n\nThe rain softened.',
    )
    attributed = client.post(f"/api/v1/projects/{project}/speaker-attributions/run", json={}).json()
    assert wait_for_job(client, attributed["id"])["status"] == "succeeded"
    context_segment = next(item for item in segments if "Mara: Hold" in item["textContent"])
    target_segment = next(item for item in segments if "Be quiet" in item["textContent"])
    client.put(
        f"/api/v1/projects/{project}/segments/{context_segment['id']}/direction",
        json={"direction": direction(context_segment["id"], "warm", 0.5), "userLocked": True},
    )
    captured: dict[str, str] = {}

    def fake_extract(_self, _project_id, request, _job_id=None):
        captured["prompt"] = request.prompt
        return SimpleNamespace(
            run=SimpleNamespace(id="llmrun_direction"),
            result={
                "directions": [
                    {
                        "segmentId": context_segment["id"],
                        "emotion": "angry",
                        "tone": "angry",
                        "pace": 1.4,
                        "intensity": 0.9,
                        "confidence": 0.9,
                        "evidence": "context-only rows must be ignored",
                    },
                    {
                        "segmentId": target_segment["id"],
                        "emotion": "quiet",
                        "tone": "hushed restraint",
                        "pace": 0.82,
                        "intensity": 0.28,
                        "pauseAfterMs": 260,
                        "stylePrompt": "hushed, restrained audiobook delivery",
                        "whisper": True,
                        "confidence": 0.74,
                        "evidence": "dialogue asks for quiet",
                    },
                ],
                "warnings": [],
            },
        )

    monkeypatch.setattr(direction_module.LocalLlmService, "extract", fake_extract, raising=False)
    inferred = client.post(
        f"/api/v1/projects/{project}/directions/infer",
        json={"useLocalLlm": True, "model": "qwen3:4b"},
    ).json()
    assert wait_for_job(client, inferred["id"])["status"] == "succeeded"

    assert f"CONTEXT {context_segment['id']}" in captured["prompt"]
    assert f"TARGET {target_segment['id']}" in captured["prompt"]
    assert "speakerCandidate=Mara" in captured["prompt"]
    assert "approvedSpeaker=Mara" in captured["prompt"]
    assert "existingDirection=warm" in captured["prompt"]
    assert "Return direction rows only for TARGET segment IDs" in captured["prompt"]

    context_row = client.get(
        f"/api/v1/projects/{project}/segments/{context_segment['id']}/direction"
    ).json()
    assert context_row["direction"]["emotion"] == "warm"
    assert context_row["userLocked"] is True
    target_row = client.get(
        f"/api/v1/projects/{project}/segments/{target_segment['id']}/direction"
    ).json()
    assert target_row["source"] == "llm_inferred"
    assert target_row["direction"]["emotion"] == "quiet"
    assert target_row["direction"]["whisper"] is True
    assert target_row["evidence"]["llmRunId"] == "llmrun_direction"
    assert target_row["evidence"]["model"] == "qwen3:4b"
    assert target_row["evidence"]["confidence"] == 0.74
    assert target_row["evidence"]["targetSegmentIds"] == [
        item["id"] for item in segments if item["id"] != context_segment["id"]
    ]
    assert target_row["evidence"]["sceneWindowSegmentIds"] == [item["id"] for item in segments]
    assert target_row["evidence"]["speakerName"] == "Mara"


def test_invalid_or_missing_llm_direction_falls_back_to_deterministic(client, monkeypatch) -> None:
    project, _chapter, _scene, segments = project_with_segments(
        client,
        b"Chapter 1\n\nHurry now! The signal is fading.\n\nThe rain softened.",
    )
    urgent_segment = next(item for item in segments if "Hurry now" in item["textContent"])

    def fake_extract(_self, _project_id, _request, _job_id=None):
        return SimpleNamespace(
            run=SimpleNamespace(id="llmrun_bad_direction"),
            result={
                "directions": [
                    {
                        "segmentId": urgent_segment["id"],
                        "emotion": "melodramatic",
                        "tone": "melodramatic",
                        "pace": 1.0,
                        "intensity": 0.5,
                        "confidence": 0.7,
                    }
                ],
                "warnings": [],
            },
        )

    monkeypatch.setattr(direction_module.LocalLlmService, "extract", fake_extract, raising=False)
    inferred = client.post(
        f"/api/v1/projects/{project}/directions/infer", json={"useLocalLlm": True}
    ).json()
    assert wait_for_job(client, inferred["id"])["status"] == "succeeded"

    row = client.get(f"/api/v1/projects/{project}/segments/{urgent_segment['id']}/direction").json()
    assert row["source"] == "inferred"
    assert row["direction"]["emotion"] == "urgent"
    assert row["evidence"]["reason"] == "deterministic_direction_inference"
