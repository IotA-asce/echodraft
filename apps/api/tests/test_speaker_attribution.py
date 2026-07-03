import json
import time
from pathlib import Path
from types import SimpleNamespace

import echodraft_api.speaker_attribution as speaker_attribution_module


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _import_and_extract(client, project: str, text: str) -> None:
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("cast.txt", text.encode(), "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    attribution_job = client.post(
        f"/api/v1/projects/{project}/speaker-attributions/run", json={}
    ).json()
    assert wait_for_job(client, attribution_job["id"])["status"] == "succeeded"


def _bran_character_id(client, project: str) -> str:
    characters = client.get(f"/api/v1/projects/{project}/characters").json()
    return next(item["id"] for item in characters if item["displayName"] == "Bran")


def _unlink_all(client, rows: list[dict]) -> None:
    for row in rows:
        client.patch(
            f"/api/v1/speaker-attributions/{row['id']}",
            json={"characterId": None, "status": "needs_review"},
        )


def test_confirmation_propagates_to_sibling_attributions(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Propagate", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        "Chapter 1\n\nBran: We leave now.\n\nBran: Hold the line.\n\nBran: Follow me.",
    )
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    bran_rows = [row for row in attributions if row["speakerName"] == "Bran"]
    assert len(bran_rows) >= 3
    character_id = _bran_character_id(client, project)
    # Clear the auto-linked cast so the siblings are pending/unlinked before we
    # confirm one -- exactly the "40 lines still need review" situation.
    _unlink_all(client, bran_rows)

    first = bran_rows[0]
    response = client.patch(
        f"/api/v1/speaker-attributions/{first['id']}",
        json={"characterId": character_id, "status": "approved"},
    ).json()
    assert response["propagatedCount"] >= 2

    refreshed = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    siblings = [row for row in refreshed if row["speakerName"] == "Bran"]
    assert all(row["characterId"] == character_id for row in siblings)
    assert all(row["status"] == "approved" for row in siblings)
    for row in siblings:
        if row["id"] != first["id"]:
            assert row["evidence"]["method"] == "propagated_from_confirmation"
            assert row["evidence"]["sourceAttributionId"] == first["id"]
            assert row["confidence"] >= 0.9


def test_confirmation_does_not_touch_locked_or_other_character_rows(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Propagate Guard", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        "Chapter 1\n\nBran: One.\n\nBran: Two.\n\nBran: Three.",
    )
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    bran_rows = [row for row in attributions if row["speakerName"] == "Bran"]
    assert len(bran_rows) >= 3
    target_id = _bran_character_id(client, project)
    other = client.post(
        f"/api/v1/projects/{project}/characters", json={"displayName": "Other"}
    ).json()
    _unlink_all(client, bran_rows)

    # Lock one Bran row to a different character; it must never be re-pointed.
    locked = bran_rows[1]
    client.patch(
        f"/api/v1/speaker-attributions/{locked['id']}",
        json={"characterId": other["id"], "status": "approved", "userLocked": True},
    )

    response = client.patch(
        f"/api/v1/speaker-attributions/{bran_rows[0]['id']}",
        json={"characterId": target_id, "status": "approved"},
    ).json()
    # The locked/other-character row is not an eligible sibling.
    assert response["propagatedCount"] == len(bran_rows) - 2
    refreshed = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    locked_after = next(row for row in refreshed if row["id"] == locked["id"])
    assert locked_after["characterId"] == other["id"]
    assert locked_after["userLocked"] is True


def test_merge_repoints_attributions_and_records_decision(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Merge Repoint", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(client, project, "Chapter 1\n\nBran: We leave now.\n\nBran: Hold.")
    source_id = _bran_character_id(client, project)
    target = client.post(
        f"/api/v1/projects/{project}/characters", json={"displayName": "Brandon"}
    ).json()
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    linked_before = [row for row in attributions if row["characterId"] == source_id]
    assert linked_before

    merged = client.post(
        f"/api/v1/characters/{target['id']}/merge",
        json={"sourceCharacterId": source_id, "reason": "Same person."},
    )
    assert merged.status_code == 200

    refreshed = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    assert not [row for row in refreshed if row["characterId"] == source_id]
    linked_after = [row for row in refreshed if row["characterId"] == target["id"]]
    assert len(linked_after) >= len(linked_before)


def test_speaker_attribution_review_and_production_voice_resolution(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Cast Review", "rightsStatus": "declared"}
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
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    mara_row = next(item for item in attributions if item["speakerName"] == "Mara")
    unknown_row = next(item for item in attributions if item["status"] == "needs_review")
    assert mara_row["characterId"] == character["id"]
    assert mara_row["voiceProfileId"] == mara_voice["id"]
    assert unknown_row["speakerName"] is None

    reviewed = client.patch(
        f"/api/v1/speaker-attributions/{unknown_row['id']}",
        json={"characterId": character["id"], "status": "approved", "userLocked": True},
    ).json()
    assert reviewed["voiceProfileId"] == mara_voice["id"]
    rerun = client.post(f"/api/v1/projects/{project}/speaker-attributions/run", json={}).json()
    assert wait_for_job(client, rerun["id"])["status"] == "succeeded"
    locked = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    assert next(item for item in locked if item["id"] == unknown_row["id"])["userLocked"] is True

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter['id']}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"
    dialogue_segment = next(item for item in segments if item["speakerCandidate"] == "Mara")
    renders = client.get(
        f"/api/v1/projects/{project}/segments/{dialogue_segment['id']}/renders"
    ).json()
    metadata = json.loads(Path(renders[0]["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["voiceProfileId"] == mara_voice["id"]


def test_locked_attribution_exemplars_injected_into_llm_prompt(client, monkeypatch) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Few Shot", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        'Chapter 1\n\nBran: We leave now.\n\n"Who goes there?"',
    )
    character = client.post(
        f"/api/v1/projects/{project}/characters", json={"displayName": "Bran"}
    ).json()
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    bran_row = next(row for row in attributions if row["speakerName"] == "Bran")
    unknown_row = next(row for row in attributions if row["status"] == "needs_review")
    # Lock an approved attribution -> it becomes a few-shot exemplar.
    client.patch(
        f"/api/v1/speaker-attributions/{bran_row['id']}",
        json={"characterId": character["id"], "status": "approved", "userLocked": True},
    )
    assert unknown_row["characterId"] is None

    captured: dict[str, str] = {}

    def fake_extract(_self, _project_id, request, _job_id=None):
        if request.task == "speaker_attribution":
            captured["prompt"] = request.prompt
        return SimpleNamespace(
            run=SimpleNamespace(id="llmrun"),
            result={"attributions": [], "warnings": []},
        )

    monkeypatch.setattr(
        speaker_attribution_module.LocalLlmService, "extract", fake_extract, raising=False
    )
    rerun = client.post(
        f"/api/v1/projects/{project}/speaker-attributions/run",
        json={"useLocalLlm": True},
    ).json()
    assert wait_for_job(client, rerun["id"])["status"] == "succeeded"

    assert "prompt" in captured
    assert "→ Speaker: Bran" in captured["prompt"]
    assert "We leave now." in captured["prompt"]
