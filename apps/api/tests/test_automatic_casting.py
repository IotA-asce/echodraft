import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from echodraft_api.automatic_casting import AutomaticCastingService, CastingSpec, detect_point_of_view
from echodraft_api.config import AppSettings
from echodraft_api.production import ProductionService
from echodraft_api.voice_catalog import VoiceCatalogService
from echodraft_db.models import (
    CastingDecisionRecord,
    ChapterRecord,
    CharacterVoiceAssignmentRecord,
    SceneRecord,
    SegmentRecord,
    SpeakerAttributionRecord,
    VoiceCatalogEntryRecord,
)
from echodraft_domain import VoiceCatalogEntry
from sqlalchemy import select


def _wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_automatic_casting_v2_environment_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECHODRAFT_AUTOMATIC_CASTING_V2_ENABLED", "true")
    assert AppSettings.from_environment().automatic_casting_v2_enabled is True


def test_detect_point_of_view_uses_pronoun_ratio_sanity_check() -> None:
    first_person = detect_point_of_view(
        "I kept my promise while we crossed the quiet harbor together."
    )
    third_person = detect_point_of_view(
        "Mara kept the promise while the travelers crossed the quiet harbor together."
    )

    assert first_person.classification == "first_person"
    assert first_person.first_person_pronoun_ratio > 0.015
    assert third_person.classification == "third_person"
    assert third_person.first_person_pronoun_ratio == 0


def test_narrator_selection_runs_before_character_cast_and_persists(client) -> None:
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "First-person narrator", "rightsStatus": "declared"},
    ).json()["id"]
    source = (
        "Chapter 1: Crossing\n\n"
        "I kept my promise, and we crossed the harbor before I lost my nerve. "
        "My hands held the rail while the rain found us."
    )
    imported = client.post(
        f"/api/v1/projects/{project_id}/source/import",
        files={"file": ("book.txt", source.encode(), "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert _wait_for_job(client, imported["id"])["status"] == "succeeded"
    extracted = client.post(
        f"/api/v1/projects/{project_id}/structure/extract",
        json={"maxSegmentChars": 180},
    ).json()
    assert _wait_for_job(client, extracted["id"])["status"] == "succeeded"
    container = client.app.state.container

    selection = AutomaticCastingService(container).select_narrator(project_id)

    assert selection["pointOfView"] == "first_person"
    assert selection["firstPersonPronounRatio"] > 0.015
    assert selection["stylePreset"] == "warm_neutral"
    assert selection["evidence"]["catalogVersion"]
    settings = client.get(f"/api/v1/projects/{project_id}/production-settings").json()
    assert settings["narratorVoiceProfileId"] == selection["voiceProfileId"]
    voice = next(
        item
        for item in client.get(f"/api/v1/projects/{project_id}/voices").json()
        if item["id"] == selection["voiceProfileId"]
    )
    assert voice["voiceCatalogEntryId"] == selection["voiceCatalogEntryId"]

    rerun = AutomaticCastingService(container).select_narrator(project_id)
    assert rerun["voiceProfileId"] == selection["voiceProfileId"]
    assert len(client.get(f"/api/v1/projects/{project_id}/voices").json()) == 1


def test_auto_cast_assigns_every_character_and_preserves_decision_history(client) -> None:
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "Automatic ensemble", "rightsStatus": "declared"},
    ).json()["id"]
    container = client.app.state.container
    mara = container.casting.create_character(
        project_id,
        "Mara",
        [],
        "protagonist",
        0.98,
        None,
        traits=["tone:warm"],
        speaking_style=["warm and clear"],
    )
    theo = container.casting.create_character(
        project_id,
        "Theo",
        [],
        "supporting",
        0.93,
        None,
        traits=["tone:brisk"],
        speaking_style=["bright"],
    )
    guard = container.casting.create_character(
        project_id,
        "Guard",
        [],
        "walk_on",
        0.8,
        None,
    )
    now = datetime.now(UTC)
    chapter = ChapterRecord(
        id="chapter_casting",
        project_id=project_id,
        order_index=0,
        title="Crossing",
        start_offset=0,
        end_offset=220,
        confidence=1.0,
        status="structured",
        parser_evidence_json="{}",
        user_locked=False,
        auto_accepted=True,
    )
    scene = SceneRecord(
        id="scene_casting",
        chapter_id=chapter.id,
        order_index=0,
        start_offset=0,
        end_offset=220,
        confidence=1.0,
        status="structured",
        parser_evidence_json="{}",
        user_locked=False,
        auto_accepted=True,
    )
    segment_rows = [
        ("seg_narration", "I kept my promise while we crossed the harbor.", "narration", None),
        (
            "seg_mara",
            "We leave before sunrise and carry enough water for the long road ahead.",
            "dialogue",
            mara,
        ),
        (
            "seg_theo",
            "The eastern bridge is watched, so take the quiet path through town.",
            "dialogue",
            theo,
        ),
        ("seg_guard", "Move along.", "dialogue", guard),
    ]
    with container.structure.database.session() as session:
        session.add(chapter)
        session.add(scene)
        offset = 0
        for order_index, (segment_id, text, segment_type, character) in enumerate(segment_rows):
            segment = SegmentRecord(
                id=segment_id,
                scene_id=scene.id,
                order_index=order_index,
                text_content=text,
                normalized_text=text,
                segment_type=segment_type,
                speaker_candidate=character.display_name if character else None,
                speaker_confidence=1.0 if character else 0.0,
                confidence=1.0,
                start_offset=offset,
                end_offset=offset + len(text),
                revision=1,
                status="structured",
                parser_evidence_json="{}",
                user_locked=False,
                auto_accepted=True,
            )
            session.add(segment)
            if character:
                session.add(
                    SpeakerAttributionRecord(
                        id=f"attr_{character.id}",
                        project_id=project_id,
                        segment_id=segment_id,
                        character_id=character.id,
                        speaker_name=character.display_name,
                        method="test",
                        evidence_json="{}",
                        confidence=1.0,
                        status="approved",
                        user_locked=False,
                        auto_accepted=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
            offset += len(text)
        session.commit()

    response = client.post(
        f"/api/v1/projects/{project_id}/casting/auto-run",
        json={"scope": "all", "castingStylePreset": "warm_neutral"},
    )
    assert response.status_code == 202
    assert _wait_for_job(client, response.json()["id"])["status"] == "succeeded"

    settings = client.get(f"/api/v1/projects/{project_id}/production-settings").json()
    assignments = container.casting.character_voice_assignments(project_id)
    assert settings["autoCastEnabled"] is True
    assert settings["castingStylePreset"] == "warm_neutral"
    assert settings["narratorCastingDecisionId"]
    assert set(assignments) == {mara.id, theo.id, guard.id}
    assert assignments[guard.id] == settings["narratorVoiceProfileId"]
    assert assignments[mara.id] != settings["narratorVoiceProfileId"]

    initial_choices: dict[str, str] = {}
    for character in (mara, theo, guard):
        decision = client.get(
            f"/api/v1/characters/{character.id}/casting-decision"
        ).json()
        initial_choices[character.id] = decision["chosenVoiceId"]
        assert decision["algorithmVersion"] == "1.0.0"
        assert decision["catalogVersion"]
        assert 1 <= len(decision["candidateScores"]) <= 3
    guard_decision = client.get(
        f"/api/v1/characters/{guard.id}/casting-decision"
    ).json()
    assert guard_decision["prominenceClass"] == "walk_on"
    assert guard_decision["candidateScores"][0]["fallback"] == (
        "narrator_min_dialogue_floor"
    )

    rerun = client.post(
        f"/api/v1/projects/{project_id}/casting/auto-run",
        json={"scope": "all", "castingStylePreset": "warm_neutral"},
    ).json()
    assert _wait_for_job(client, rerun["id"])["status"] == "succeeded"
    for character_id, chosen_voice_id in initial_choices.items():
        current = client.get(
            f"/api/v1/characters/{character_id}/casting-decision"
        ).json()
        assert current["chosenVoiceId"] == chosen_voice_id

    with container.structure.database.session() as session:
        decisions = list(
            session.scalars(
                select(CastingDecisionRecord).where(
                    CastingDecisionRecord.project_id == project_id
                )
            )
        )
    assert len(decisions) == 8
    assert sum(item.superseded_by_id is None for item in decisions) == 4
    project = container.projects.get(project_id)
    assert project is not None
    manifest = json.loads(
        (Path(project.artifact_path) / "manifests" / "casting_manifest.json").read_text()
    )
    assert manifest["algorithmVersion"] == "1.0.0"
    assert manifest["lockedCharacterIds"] == []


def test_auto_cast_preserves_legacy_hand_cast_narrator_and_character(client) -> None:
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "Legacy hand cast", "rightsStatus": "declared"},
    ).json()["id"]
    narrator = client.post(
        f"/api/v1/projects/{project_id}/voices",
        json={
            "name": "Hand narrator",
            "backend": "mock",
            "providerVoiceId": "mock-narrator",
        },
    ).json()
    character_voice = client.post(
        f"/api/v1/projects/{project_id}/voices",
        json={
            "name": "Hand character",
            "backend": "mock",
            "providerVoiceId": "mock-character",
        },
    ).json()
    character = client.post(
        f"/api/v1/projects/{project_id}/characters",
        json={"displayName": "Mara", "roleType": "major"},
    ).json()
    container = client.app.state.container
    container.casting.assign(character["id"], character_voice["id"])
    client.put(
        f"/api/v1/projects/{project_id}/production-settings",
        json={"narratorVoiceProfileId": narrator["id"]},
    )

    job = client.post(
        f"/api/v1/projects/{project_id}/casting/auto-run",
        json={"scope": "all", "castingStylePreset": "warm_neutral"},
    ).json()
    assert _wait_for_job(client, job["id"])["status"] == "succeeded"

    settings = client.get(f"/api/v1/projects/{project_id}/production-settings").json()
    assert settings["narratorVoiceProfileId"] == narrator["id"]
    assert container.casting.character_voice_assignment(character["id"]) == character_voice["id"]
    with container.structure.database.session() as session:
        assignment = session.scalar(
            select(CharacterVoiceAssignmentRecord).where(
                CharacterVoiceAssignmentRecord.character_id == character["id"]
            )
        )
        narrator_decision = session.get(
            CastingDecisionRecord, settings["narratorCastingDecisionId"]
        )
    assert assignment is not None
    assert assignment.user_locked is True
    assert assignment.casting_decision_id is None
    assert narrator_decision is not None
    assert narrator_decision.user_locked is True
    assert client.get(
        f"/api/v1/characters/{character['id']}/casting-decision"
    ).status_code == 404
    project = container.projects.get(project_id)
    assert project is not None
    manifest = json.loads(
        (Path(project.artifact_path) / "manifests" / "casting_manifest.json").read_text()
    )
    assert manifest["lockedCharacterIds"] == [character["id"]]


def test_manual_override_enforces_narrator_reuse_and_lock(client) -> None:
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "Override safety", "rightsStatus": "declared"},
    ).json()["id"]
    container = client.app.state.container
    character = container.casting.create_character(
        project_id, "Mara", [], "major", 1.0, None
    )
    AutomaticCastingService(container).auto_cast(project_id)
    settings = client.get(f"/api/v1/projects/{project_id}/production-settings").json()
    narrator_voice_id = settings["narratorVoiceProfileId"]

    blocked = client.post(
        f"/api/v1/characters/{character.id}/assign-voice",
        json={"voiceProfileId": narrator_voice_id, "lockAssignment": True},
    )
    assert blocked.status_code == 422

    alternate = client.post(
        f"/api/v1/projects/{project_id}/voices",
        json={
            "name": "Alternate",
            "backend": "mock",
            "providerVoiceId": "mock-character",
        },
    ).json()
    VoiceCatalogService(container).audition_backfill()
    overridden = client.post(
        f"/api/v1/characters/{character.id}/assign-voice",
        json={
            "voiceProfileId": alternate["id"],
            "lockAssignment": True,
            "allowNarratorReuse": False,
        },
    )
    assert overridden.status_code == 200
    decision = client.get(
        f"/api/v1/characters/{character.id}/casting-decision"
    ).json()
    assert decision["userLocked"] is True
    assert decision["evidence"]["source"] == "user_override"

    AutomaticCastingService(container).auto_cast(project_id)
    assert container.casting.character_voice_assignment(character.id) == alternate["id"]


def test_structure_v2_auto_chains_casting_and_writes_manifest(client) -> None:
    container = client.app.state.container
    container.settings = replace(
        container.settings,
        automatic_casting_v2_enabled=True,
    )
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "Auto-chain", "rightsStatus": "declared"},
    ).json()["id"]
    source = client.post(
        f"/api/v1/projects/{project_id}/source/import",
        files={
            "file": (
                "book.txt",
                b"Chapter 1\n\nMara: We leave now.\n\nI followed her into the rain.",
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert _wait_for_job(client, source["id"])["status"] == "succeeded"
    structure = client.post(
        f"/api/v1/projects/{project_id}/structure/extract",
        json={"maxSegmentChars": 120},
    ).json()
    assert _wait_for_job(client, structure["id"])["status"] == "succeeded"

    settings = client.get(f"/api/v1/projects/{project_id}/production-settings").json()
    assert settings["narratorVoiceProfileId"]
    assert settings["narratorCastingDecisionId"]
    project = container.projects.get(project_id)
    assert project is not None
    manifest_path = Path(project.artifact_path) / "manifests" / "casting_manifest.json"
    assert manifest_path.is_file()
    assert json.loads(manifest_path.read_text())["projectId"] == project_id


def test_auto_cast_relaxes_gender_requirement_on_catalog_exhaustion(client) -> None:
    """Casting must never abort mid-run (Fix 1): an all-female catalog with a
    masculine-required character must still complete the whole run, recording
    the relaxation it took rather than raising, and every other character
    (processed after the exhausted one) must still get cast normally."""
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "All-female catalog", "rightsStatus": "declared"},
    ).json()["id"]
    container = client.app.state.container
    now = datetime.now(UTC)
    engine_version = container.tts_adapter.model_version()
    # Seed an all-feminine catalog matching the mock adapter's two voice ids
    # exactly, so automatic casting's incremental audition backfill (Fix 4)
    # recognizes both as already cataloged and leaves these seeded facets
    # alone rather than re-measuring them.
    with container.structure.database.session() as session:
        for suffix in ("narrator", "character"):
            session.add(
                VoiceCatalogEntryRecord(
                    id=f"vcat_test_feminine_{suffix}",
                    engine="mock",
                    engine_version=engine_version,
                    engine_voice_id=f"mock-{suffix}",
                    synthesis_kind="fixed",
                    gender="feminine",
                    age_range="unknown",
                    accent="unknown",
                    locale="und",
                    timbre_json="[]",
                    energy_default="medium",
                    acoustics_json=json.dumps(
                        {"pitchMedianHz": 200.0, "spectralBrightness": 0.2}
                    ),
                    embedding_json="{}",
                    sample_paths_json="{}",
                    license_json=json.dumps({"commercialUse": True}),
                    labeled_by_json="{}",
                    schema_version="0.1.0",
                    catalog_version="seed-v1",
                    created_at=now,
                )
            )
        session.commit()

    bram = container.casting.create_character(
        project_id, "Bram", [], "supporting", 0.9, None, traits=["gender:masculine"]
    )
    nia = container.casting.create_character(
        project_id, "Nia", [], "supporting", 0.9, None, traits=["gender:feminine"]
    )
    chapter = ChapterRecord(
        id="chapter_relax",
        project_id=project_id,
        order_index=0,
        title="Siege",
        start_offset=0,
        end_offset=200,
        confidence=1.0,
        status="structured",
        parser_evidence_json="{}",
        user_locked=False,
        auto_accepted=True,
    )
    scene = SceneRecord(
        id="scene_relax",
        chapter_id=chapter.id,
        order_index=0,
        start_offset=0,
        end_offset=200,
        confidence=1.0,
        status="structured",
        parser_evidence_json="{}",
        user_locked=False,
        auto_accepted=True,
    )
    segment_rows = [
        (
            "seg_bram",
            "I will guard this bridge and hold the eastern line no matter what comes.",
            bram,
        ),
        (
            "seg_nia",
            "We should leave before the guards notice the broken lock upstairs.",
            nia,
        ),
    ]
    with container.structure.database.session() as session:
        session.add(chapter)
        session.add(scene)
        offset = 0
        for order_index, (segment_id, text, character) in enumerate(segment_rows):
            segment = SegmentRecord(
                id=segment_id,
                scene_id=scene.id,
                order_index=order_index,
                text_content=text,
                normalized_text=text,
                segment_type="dialogue",
                speaker_candidate=character.display_name,
                speaker_confidence=1.0,
                confidence=1.0,
                start_offset=offset,
                end_offset=offset + len(text),
                revision=1,
                status="structured",
                parser_evidence_json="{}",
                user_locked=False,
                auto_accepted=True,
            )
            session.add(segment)
            session.add(
                SpeakerAttributionRecord(
                    id=f"attr_{character.id}",
                    project_id=project_id,
                    segment_id=segment_id,
                    character_id=character.id,
                    speaker_name=character.display_name,
                    method="test",
                    evidence_json="{}",
                    confidence=1.0,
                    status="approved",
                    user_locked=False,
                    auto_accepted=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            offset += len(text)
        session.commit()

    response = client.post(
        f"/api/v1/projects/{project_id}/casting/auto-run",
        json={"scope": "all", "castingStylePreset": "warm_neutral"},
    )
    assert response.status_code == 202
    job = _wait_for_job(client, response.json()["id"])
    assert job["status"] == "succeeded"  # the run must never abort mid-way

    bram_decision = client.get(f"/api/v1/characters/{bram.id}/casting-decision").json()
    assert bram_decision["chosenVoiceId"]
    assert "droppedGenderRequirement" in bram_decision["evidence"]["relaxations"]

    # A subsequent character with a satisfiable requirement still casts
    # cleanly, with no relaxation needed.
    nia_decision = client.get(f"/api/v1/characters/{nia.id}/casting-decision").json()
    assert nia_decision["chosenVoiceId"]
    assert nia_decision["evidence"]["relaxations"] == []


def test_assign_majors_backtracks_to_a_better_joint_assignment(client) -> None:
    """Fix 2: greedy-with-backtracking beats pure greedy on a constructible
    two-major, two-voice catalog where scene co-occurrence makes the naive
    first-come-first-served pick order provably suboptimal."""
    container = client.app.state.container
    service = AutomaticCastingService(container)

    def voice(voice_id: str, accent: str, energy: str, pitch: float, brightness: float) -> VoiceCatalogEntry:
        return VoiceCatalogEntry.model_validate(
            {
                "id": voice_id,
                "engine": "mock",
                "engineVersion": "v1",
                "engineVoiceId": voice_id,
                "synthesisKind": "fixed",
                "gender": "unknown",
                "ageRange": "unknown",
                "accent": accent,
                "locale": "und",
                "timbre": [],
                "energyDefault": energy,
                "acoustics": {"pitchMedianHz": pitch, "spectralBrightness": brightness},
                "samplePaths": {},
                "license": {"commercialUse": True},
                "labeledBy": {},
                "catalogVersion": "v1",
                "facets": [],
                "createdAt": datetime.now(UTC),
            }
        )

    def spec(character_id: str, preferred: dict[str, str], partners: list[str]) -> CastingSpec:
        return CastingSpec(
            character_id=character_id,
            required_facets={},
            preferred_facets=preferred,
            timbre_preference=[],
            prominence_class="major",
            dialogue_word_count=2000,
            dialogue_segment_count=10,
            scene_co_occurrence=partners,
            confidence=0.9,
            evidence_refs=[],
        )

    # V1 is the only voice that satisfies both of B's preferred facets; V2 is
    # close enough to V1 acoustically that whichever of A/B gets stuck with it
    # while the other holds V1 pays a real scene-co-occurrence distinctiveness
    # penalty. A only cares about accent, so it is nearly indifferent between
    # V1 and V2 -- the joint-optimal assignment gives V1 to B, not to A.
    v1 = voice("V1", "irish", "high", 150.0, 0.10)
    v2 = voice("V2", "american", "medium", 155.0, 0.11)
    catalog = [v1, v2]

    character_a = spec("A", {"accent": "irish"}, ["B"])
    character_b = spec("B", {"accent": "irish", "energy": "high"}, ["A"])

    # What pure greedy (process A, then B, no backtracking) would produce:
    # A takes its raw favorite (V1) first, forcing B into a penalized pick.
    greedy_scored_a, _ = service._rank_candidates(character_a, catalog, {})
    greedy_a_voice, greedy_a_score, _ = greedy_scored_a[0]
    greedy_scored_b, _ = service._rank_candidates(
        character_b, catalog, {"A": greedy_a_voice}
    )
    greedy_b_voice, greedy_b_score, _ = greedy_scored_b[0]
    assert greedy_a_voice.id == "V1"
    assert greedy_b_voice.id == "V2"
    greedy_total = greedy_a_score + greedy_b_score

    result = service._assign_majors([character_a, character_b], catalog, {})

    assert result["A"].voice.id == "V2"
    assert result["B"].voice.id == "V1"
    backtracked_total = result["A"].score + result["B"].score
    assert backtracked_total > greedy_total
    # A Pareto improvement in this construction: B gains far more than A gives up.
    assert result["B"].score > greedy_b_score
    assert result["A"].score <= greedy_a_score


def test_pooled_minor_voices_get_a_differentiating_pace_offset(client) -> None:
    """Fix 4: pooled minors sharing one catalog voice get a small, deterministic
    pace offset recorded on the casting decision, applied by production's
    direction resolution -- but a user's explicit override always wins untouched."""
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "Pooled minors", "rightsStatus": "declared"},
    ).json()["id"]
    container = client.app.state.container
    now = datetime.now(UTC)
    characters = {
        name: container.casting.create_character(project_id, name, [], "supporting", 0.9, None)
        for name in ("Alice", "Ben", "Cara", "Dee")
    }
    chapter = ChapterRecord(
        id="chapter_pool",
        project_id=project_id,
        order_index=0,
        title="Market",
        start_offset=0,
        end_offset=500,
        confidence=1.0,
        status="structured",
        parser_evidence_json="{}",
        user_locked=False,
        auto_accepted=True,
    )
    scene = SceneRecord(
        id="scene_pool",
        chapter_id=chapter.id,
        order_index=0,
        start_offset=0,
        end_offset=500,
        confidence=1.0,
        status="structured",
        parser_evidence_json="{}",
        user_locked=False,
        auto_accepted=True,
    )
    # Descending word counts so Alice is the sole major (top 15%) and
    # Ben/Cara/Dee are minors, all forced to share the single catalog voice
    # left over once the narrator reserves the other of the mock adapter's
    # two voices.
    lines = {
        "Alice": " ".join(["alpha"] * 50),
        "Ben": " ".join(["bravo"] * 20),
        "Cara": " ".join(["charlie"] * 15),
        "Dee": " ".join(["delta"] * 10),
    }
    segment_ids: dict[str, str] = {}
    with container.structure.database.session() as session:
        session.add(chapter)
        session.add(scene)
        offset = 0
        for order_index, name in enumerate(["Alice", "Ben", "Cara", "Dee"]):
            character = characters[name]
            text = lines[name]
            segment_id = f"seg_pool_{name.lower()}"
            segment_ids[name] = segment_id
            segment = SegmentRecord(
                id=segment_id,
                scene_id=scene.id,
                order_index=order_index,
                text_content=text,
                normalized_text=text,
                segment_type="dialogue",
                speaker_candidate=name,
                speaker_confidence=1.0,
                confidence=1.0,
                start_offset=offset,
                end_offset=offset + len(text),
                revision=1,
                status="structured",
                parser_evidence_json="{}",
                user_locked=False,
                auto_accepted=True,
            )
            session.add(segment)
            session.add(
                SpeakerAttributionRecord(
                    id=f"attr_pool_{name.lower()}",
                    project_id=project_id,
                    segment_id=segment_id,
                    character_id=character.id,
                    speaker_name=name,
                    method="test",
                    evidence_json="{}",
                    confidence=1.0,
                    status="approved",
                    user_locked=False,
                    auto_accepted=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            offset += len(text)
        session.commit()

    response = client.post(
        f"/api/v1/projects/{project_id}/casting/auto-run",
        json={"scope": "all", "castingStylePreset": "warm_neutral"},
    )
    assert _wait_for_job(client, response.json()["id"])["status"] == "succeeded"

    decisions = {
        name: client.get(f"/api/v1/characters/{characters[name].id}/casting-decision").json()
        for name in ("Ben", "Cara", "Dee")
    }
    for name in ("Ben", "Cara", "Dee"):
        assert decisions[name]["prominenceClass"] == "minor"
        assert decisions[name]["chosenVoiceId"]  # never left unresolved
    shared_voice_ids = {decisions[name]["chosenVoiceId"] for name in decisions}
    assert len(shared_voice_ids) == 1  # only one catalog voice left to pool onto

    # First sharer is unperturbed; later sharers get a nonzero, alternating offset.
    assert "poolOffset" not in decisions["Ben"]["evidence"]
    assert decisions["Cara"]["evidence"]["poolOffset"] == pytest.approx(0.04)
    assert decisions["Dee"]["evidence"]["poolOffset"] == pytest.approx(-0.04)

    production = ProductionService(container)
    assert production.resolve_direction(project_id, segment_ids["Ben"]).pace == pytest.approx(1.0)
    assert production.resolve_direction(project_id, segment_ids["Cara"]).pace == pytest.approx(1.04)
    assert production.resolve_direction(project_id, segment_ids["Dee"]).pace == pytest.approx(0.96)

    # A user's explicit segment override always wins untouched, offset or not.
    client.put(
        f"/api/v1/projects/{project_id}/segments/{segment_ids['Cara']}/production-override",
        json={"direction": {"scopeType": "segment", "scopeId": segment_ids["Cara"], "pace": 1.5}},
    )
    assert production.resolve_direction(project_id, segment_ids["Cara"]).pace == pytest.approx(1.5)
