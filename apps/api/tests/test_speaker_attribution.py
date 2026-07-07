import json
import time
from pathlib import Path
from types import SimpleNamespace

import echodraft_api.cast_discovery as cast_discovery_module
import echodraft_api.speaker_attribution as speaker_attribution_module
from echodraft_db.models import (
    CastGraphDecisionRecord,
    CharacterRecord,
    SpeakerAttributionRecord,
)
from sqlalchemy import delete


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


def _attribution_for_text(client, project: str, needle: str) -> dict:
    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    segment_id = ""
    for chapter in chapters:
        scenes = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()
        for scene in scenes:
            segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
            match = next(
                (segment for segment in segments if needle in segment["textContent"]), None
            )
            if match:
                segment_id = match["id"]
                break
        if segment_id:
            break
    assert segment_id
    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    return next(row for row in rows if row["segmentId"] == segment_id)


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


def test_unlabeled_dialogue_uses_nearby_turn_evidence(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Turn Evidence", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        "Chapter 1\n\nMara: We leave now.\n\n\"No,\" she replied.\n\nMara: Stay close.",
    )

    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    contextual = next(
        row
        for row in rows
        if row["speakerName"] == "Mara"
        and row["evidence"].get("reason") == "nearby_dialogue_turn"
    )
    assert contextual["status"] == "needs_review"
    assert contextual["evidence"]["previousSpeaker"] == "Mara"
    assert contextual["evidence"]["pronounCue"] == "she"


def test_unlabeled_dialogue_uses_two_speaker_alternation(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Alternation", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        "Chapter 1\n\nMara: First.\n\nJon: Second.\n\n\"Third.\"\n\nJon: Fourth.",
    )

    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    inferred = next(
        row
        for row in rows
        if row["speakerName"] == "Mara"
        and row["evidence"].get("reason") == "turn_taking_alternation"
    )
    assert inferred["status"] == "needs_review"
    assert inferred["characterId"]
    assert inferred["evidence"]["previousSpeaker"] == "Jon"
    assert inferred["evidence"]["priorSpeaker"] == "Mara"
    assert inferred["evidence"]["nextSpeaker"] == "Jon"


def test_unlabeled_dialogue_uses_interruption_exchange(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Interruption", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        'Chapter 1\n\nMara: First.\n\nJon: Second.\n\nMara: I told you—\n\n"Enough."',
    )

    inferred = _attribution_for_text(client, project, "Enough.")
    assert inferred["speakerName"] == "Jon"
    assert inferred["status"] == "needs_review"
    assert inferred["evidence"]["reason"] == "interruption_exchange"
    assert inferred["evidence"]["interruptedSpeaker"] == "Mara"
    assert inferred["evidence"]["activeSpeakers"] == ["Mara", "Jon"]


def test_unlabeled_dialogue_uses_vocative_exchange(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Vocative", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        'Chapter 1\n\nMara: First.\n\nJon: Second.\n\n"Mara, listen to me."',
    )

    inferred = _attribution_for_text(client, project, "Mara, listen")
    assert inferred["speakerName"] == "Jon"
    assert inferred["status"] == "needs_review"
    assert inferred["evidence"]["reason"] == "vocative_exchange"
    assert inferred["evidence"]["addressedSpeaker"] == "Mara"
    assert inferred["evidence"]["activeSpeakers"] == ["Mara", "Jon"]


def test_three_speaker_scene_skips_two_speaker_exchange_rules(client) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"title": "Three Speaker Exchange", "rightsStatus": "declared"},
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        (
            "Chapter 1\n\nMara: First.\n\nJon: Second.\n\n"
            'Talia: Third.\n\nMara: I told you—\n\n"Enough."'
        ),
    )

    unresolved = _attribution_for_text(client, project, "Enough.")
    assert unresolved["speakerName"] is None
    assert unresolved["status"] == "needs_review"
    assert unresolved["evidence"]["reason"] == "dialogue_without_speaker"


def test_unlabeled_dialogue_uses_named_speech_action_cue(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Action Cue", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        "Chapter 1\n\nMara: Listen.\n\n\"Stay close,\" Mara muttered.",
    )

    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    cued = next(
        row
        for row in rows
        if row["speakerName"] == "Mara"
        and row["evidence"].get("reason") == "speech_action_cue"
    )
    assert cued["status"] == "needs_review"
    assert cued["evidence"]["speechCue"] == "Mara"


def test_unlabeled_dialogue_uses_gendered_pronoun_coreference(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Pronoun Coreference", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    mara = client.post(
        f"/api/v1/projects/{project}/characters",
        json={"displayName": "Mara", "traits": ["gender:feminine"]},
    ).json()
    client.post(
        f"/api/v1/projects/{project}/characters",
        json={"displayName": "Jon", "traits": ["gender:masculine"]},
    )
    _import_and_extract(
        client,
        project,
        "Chapter 1\n\nMara: First.\n\nJon: Second.\n\n\"Third,\" she whispered.\n\nJon: Fourth.",
    )

    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    coreferenced = next(
        row
        for row in rows
        if row["speakerName"] == "Mara"
        and row["evidence"].get("reason") == "pronoun_coreference"
    )
    assert coreferenced["characterId"] == mara["id"]
    assert coreferenced["status"] == "needs_review"
    assert coreferenced["evidence"]["pronounCue"] == "she"


def test_speaker_attribution_proposes_missing_cast_from_confident_label(
    client, app, monkeypatch
) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Cast Proposal", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("cast.txt", b"Chapter 1\n\nTalia: Hold.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"

    database = app.state.container.structure.database
    with database.session() as session:
        session.execute(
            delete(SpeakerAttributionRecord).where(SpeakerAttributionRecord.project_id == project)
        )
        session.execute(
            delete(CastGraphDecisionRecord).where(CastGraphDecisionRecord.project_id == project)
        )
        session.execute(delete(CharacterRecord).where(CharacterRecord.project_id == project))
        session.commit()

    path_calls: dict[str, object] = {}
    original_candidate_from_mentions = (
        cast_discovery_module.CastDiscoveryService._candidate_from_mentions
    )
    original_decision_for_candidate = (
        cast_discovery_module.CastDiscoveryService._decision_for_candidate
    )
    original_apply_candidate = cast_discovery_module.CastDiscoveryService._apply_candidate

    def track_candidate_from_mentions(self, mentions, chapter_id):
        candidate = original_candidate_from_mentions(self, mentions, chapter_id)
        path_calls["candidateSource"] = candidate.source if candidate else None
        path_calls["candidateDisplayName"] = candidate.display_name if candidate else None
        return candidate

    def track_decision_for_candidate(self, project_id, candidate, index, *, use_local_llm):
        decision = original_decision_for_candidate(
            self, project_id, candidate, index, use_local_llm=use_local_llm
        )
        path_calls["decisionAction"] = decision.action
        path_calls["decisionReason"] = decision.reason
        return decision

    def track_apply_candidate(self, project_id, source_id, candidate, decision, index):
        path_calls["appliedCandidateSource"] = candidate.source
        path_calls["appliedDecisionAction"] = decision.action
        return original_apply_candidate(self, project_id, source_id, candidate, decision, index)

    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_candidate_from_mentions",
        track_candidate_from_mentions,
    )
    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_decision_for_candidate",
        track_decision_for_candidate,
    )
    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_apply_candidate",
        track_apply_candidate,
    )

    rerun = client.post(f"/api/v1/projects/{project}/speaker-attributions/run", json={}).json()
    assert wait_for_job(client, rerun["id"])["status"] == "succeeded"

    characters = client.get(f"/api/v1/projects/{project}/characters").json()
    talia = next(character for character in characters if character["displayName"] == "Talia")
    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    row = next(item for item in rows if item["speakerName"] == "Talia")
    assert path_calls == {
        "candidateSource": "speaker_attribution",
        "candidateDisplayName": "Talia",
        "decisionAction": "new",
        "decisionReason": "Filtered candidate is unique and above auto-create confidence.",
        "appliedCandidateSource": "speaker_attribution",
        "appliedDecisionAction": "new",
    }
    assert row["characterId"] == talia["id"]
    assert row["status"] == "approved"
    assert row["evidence"]["castProposal"] == "proposed_cast_from_speaker_attribution"


def test_speaker_attribution_additively_enriches_existing_character_via_cast_graph_match(
    client, app, monkeypatch
) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Cast Proposal Merge", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("cast.txt", b"Chapter 1\n\nCaptain John: Hold.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"

    database = app.state.container.structure.database
    with database.session() as session:
        session.execute(
            delete(SpeakerAttributionRecord).where(SpeakerAttributionRecord.project_id == project)
        )
        session.execute(
            delete(CastGraphDecisionRecord).where(CastGraphDecisionRecord.project_id == project)
        )
        session.execute(delete(CharacterRecord).where(CharacterRecord.project_id == project))
        session.commit()

    existing = client.post(
        f"/api/v1/projects/{project}/characters", json={"displayName": "John"}
    ).json()

    path_calls: dict[str, object] = {}
    original_decision_for_candidate = (
        cast_discovery_module.CastDiscoveryService._decision_for_candidate
    )
    original_apply_candidate = cast_discovery_module.CastDiscoveryService._apply_candidate
    original_create_character = app.state.container.casting.create_character
    create_character_calls = 0

    def track_decision_for_candidate(self, project_id, candidate, index, *, use_local_llm):
        decision = original_decision_for_candidate(
            self, project_id, candidate, index, use_local_llm=use_local_llm
        )
        path_calls["candidateSource"] = candidate.source
        path_calls["decisionAction"] = decision.action
        path_calls["targetName"] = decision.target_name
        return decision

    def track_apply_candidate(self, project_id, source_id, candidate, decision, index):
        path_calls["appliedCandidateSource"] = candidate.source
        path_calls["appliedDecisionAction"] = decision.action
        return original_apply_candidate(self, project_id, source_id, candidate, decision, index)

    def track_create_character(*args, **kwargs):
        nonlocal create_character_calls
        create_character_calls += 1
        return original_create_character(*args, **kwargs)

    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_decision_for_candidate",
        track_decision_for_candidate,
    )
    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_apply_candidate",
        track_apply_candidate,
    )
    monkeypatch.setattr(app.state.container.casting, "create_character", track_create_character)

    rerun = client.post(f"/api/v1/projects/{project}/speaker-attributions/run", json={}).json()
    assert wait_for_job(client, rerun["id"])["status"] == "succeeded"

    characters = client.get(f"/api/v1/projects/{project}/characters").json()
    active = [character for character in characters if not character["mergedIntoCharacterId"]]
    assert [character["displayName"] for character in active] == ["John"]
    assert active[0]["id"] == existing["id"]
    assert "Captain John" in active[0]["aliases"]
    assert "role:captain" in active[0]["traits"]
    assert create_character_calls == 0
    assert path_calls == {
        "candidateSource": "speaker_attribution",
        "decisionAction": "merge",
        "targetName": "John",
        "appliedCandidateSource": "speaker_attribution",
        "appliedDecisionAction": "merge",
    }

    rows = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    row = next(item for item in rows if item["speakerName"] == "Captain John")
    assert row["characterId"] == existing["id"]
    assert row["status"] == "approved"
    assert row["evidence"]["castProposal"] == "proposed_cast_from_speaker_attribution"


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


def test_llm_prompt_includes_same_scene_context_window(client, monkeypatch) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Scene Window", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    _import_and_extract(
        client,
        project,
        'Chapter 1\n\nMara: Hold the bridge.\n\nThe torches hissed in the rain.\n\n"Who goes there?"',
    )
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    context_segment = next(item for item in segments if "Mara: Hold" in item["textContent"])
    target_segment = next(item for item in segments if "Who goes there" in item["textContent"])
    rows_before = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    context_before = next(row for row in rows_before if row["segmentId"] == context_segment["id"])
    assert context_before["speakerName"] == "Mara"
    assert context_before["status"] == "approved"
    target_before = next(row for row in rows_before if row["segmentId"] == target_segment["id"])
    assert target_before["status"] == "needs_review"

    captured: dict[str, str] = {}

    def fake_extract(_self, _project_id, request, _job_id=None):
        if request.task == "speaker_attribution":
            captured["prompt"] = request.prompt
        return SimpleNamespace(
            run=SimpleNamespace(id="llmrun_scene_window"),
            result={
                "attributions": [
                    {
                        "segmentId": context_segment["id"],
                        "speakerName": "Wrong",
                        "characterName": "Wrong",
                        "confidence": 0.1,
                        "evidence": "context line should be ignored",
                    },
                    {
                        "segmentId": target_segment["id"],
                        "speakerName": "Mara",
                        "characterName": "Mara",
                        "confidence": 0.4,
                        "evidence": "scene context",
                    },
                ],
                "warnings": [],
            },
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
    assert "Active speakers in this scene: Mara" in captured["prompt"]
    assert f"CONTEXT {context_segment['id']}: Mara: Hold the bridge." in captured["prompt"]
    assert f"TARGET {target_segment['id']}: \"Who goes there?\"" in captured["prompt"]
    assert "Return attributions only for TARGET segment IDs" in captured["prompt"]

    rows_after = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    context_after = next(row for row in rows_after if row["segmentId"] == context_segment["id"])
    assert context_after["speakerName"] == "Mara"
    assert context_after["status"] == "approved"
    target_after = next(row for row in rows_after if row["segmentId"] == target_segment["id"])
    assert target_after["evidence"]["sceneWindowSegmentIds"]
    assert target_after["evidence"]["targetSegmentIds"] == [target_segment["id"]]
    assert target_after["evidence"]["activeSpeakers"] == ["Mara"]
