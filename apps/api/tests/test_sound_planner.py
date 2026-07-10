import json
import time
from pathlib import Path

from echodraft_api.sound_planner import (
    PlannedSoundCue,
    SegmentPlanInput,
    SoundPlanSettings,
    _cue_lock_key,
    _planned_lock_key,
    plan_chapter_sound,
)
from echodraft_db.models import AmbienceCueRecord, SceneRecord


def _wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _structured_project(client, text: str) -> tuple[str, str, list[dict]]:
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "Automatic sound", "rightsStatus": "declared"},
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project_id}/source/import",
        files={"file": ("book.txt", text.encode(), "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert _wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(
        f"/api/v1/projects/{project_id}/structure/extract",
        json={"maxSegmentChars": 120},
    ).json()
    assert _wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project_id}/chapters").json()[0]["id"]
    scenes = client.get(f"/api/v1/chapters/{chapter_id}/scenes").json()
    return project_id, chapter_id, scenes


def _profile(scene_id: str, **changes: object) -> dict[str, object]:
    profile: dict[str, object] = {
        "sceneId": scene_id,
        "locationCategory": "forest",
        "timeOfDay": "night",
        "weather": "rain",
        "interiorExterior": "exterior",
        "mood": "quiet",
        "tensionLevel": 0.2,
        "explicitSoundEvents": [],
        "noSfxRecommended": False,
        "confidence": 0.9,
    }
    profile.update(changes)
    return profile


def test_pure_planner_is_empty_for_speech_only_and_reuses_contiguous_bed() -> None:
    profiles = {
        "scene_1": _profile("scene_1"),
        "scene_2": _profile("scene_2"),
    }
    segments = {
        "scene_1": (SegmentPlanInput("seg_1", "Rain crossed the forest.", 0, 100),),
        "scene_2": (SegmentPlanInput("seg_2", "The forest remained wet.", 0, 100),),
    }

    # Opening/peak music placement is exercised by its own dedicated tests below; disable
    # it here so this test stays focused on ambience continuity.
    no_music = SoundPlanSettings(allow_opening_music=False, allow_peak_music=False)
    clean = plan_chapter_sound(
        "chapter_1", ["scene_1", "scene_2"], profiles, segments, "speech_only", no_music
    )
    cinematic = plan_chapter_sound(
        "chapter_1", ["scene_1", "scene_2"], profiles, segments, "light_cinematic", no_music
    )

    assert clean.cues == ()
    assert [cue.kind for cue in cinematic.cues] == ["ambience"]
    assert cinematic.cues[0].scene_id == "scene_1"
    assert cinematic.cues[0].run_scene_ids == ("scene_1", "scene_2")


def test_pure_planner_confidence_no_sfx_and_budget_guards() -> None:
    profiles = {
        "scene_1": _profile(
            "scene_1",
            explicitSoundEvents=[
                {
                    "eventType": "door_slam",
                    "sentenceEvidence": "The door slammed",
                    "confidence": 0.95,
                },
                {
                    "eventType": "thunder",
                    "sentenceEvidence": "thunder rolled",
                    "confidence": 0.95,
                },
            ],
        ),
        "scene_2": _profile(
            "scene_2",
            locationCategory="tavern",
            interiorExterior="interior",
            weather="none",
            explicitSoundEvents=[
                {
                    "eventType": "knock",
                    "sentenceEvidence": "Someone knocked",
                    "confidence": 0.99,
                }
            ],
        ),
    }
    segments = {
        "scene_1": (
            SegmentPlanInput("seg_door", "The door slammed hard.", 0, 100),
            SegmentPlanInput("seg_thunder", "Then thunder rolled.", 100, 200, no_sfx=True),
        ),
        "scene_2": (SegmentPlanInput("seg_knock", "Someone knocked twice.", 0, 100),),
    }

    plan = plan_chapter_sound(
        "chapter_1",
        ["scene_1", "scene_2"],
        profiles,
        segments,
        "light_cinematic",
        SoundPlanSettings(sfx_budget_light=1, allow_opening_music=False, allow_peak_music=False),
    )

    sfx = [cue for cue in plan.cues if cue.kind == "sfx"]
    assert [(cue.event_type, cue.segment_id) for cue in sfx] == [("door_slam", "seg_door")]
    assert plan.sfx_used == 1
    assert {skip.reason for skip in plan.skipped} >= {
        "segment_no_sfx_flag",
        "chapter_sfx_budget_exhausted",
    }


def test_sound_plan_endpoint_materializes_provenance_manifest_and_is_idempotent(client) -> None:
    project_id, chapter_id, scenes = _structured_project(
        client,
        "Chapter 1\n\nRain crossed the forest at night.\n\n***\n\n"
        "The forest remained wet in the night rain.",
    )
    container = client.app.state.container
    with container.structure.database.session() as session:
        for scene in scenes:
            record = session.get(SceneRecord, scene["id"])
            assert record is not None
            record.atmosphere_profile_json = json.dumps(_profile(scene["id"]), sort_keys=True)
        session.commit()

    first = client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/sound-plan",
        json={"renderMode": "light_cinematic"},
    )
    second = client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/sound-plan",
        json={"renderMode": "light_cinematic"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["materializedCueIds"] == first.json()["materializedCueIds"]
    assert second.json()["materializedAssetIds"] == first.json()["materializedAssetIds"]
    assert len(client.get(f"/api/v1/projects/{project_id}/chapters/{chapter_id}/sound-cues").json()) == 1
    asset = client.get(f"/api/v1/projects/{project_id}/sound-assets").json()[0]
    assert asset["provenance"] == "bank"
    assert asset["model"] == "procedural_sound_bank"
    assert asset["cacheKey"]
    assert asset["qaStatus"] == "passed"
    cue = client.get(f"/api/v1/projects/{project_id}/chapters/{chapter_id}/sound-cues").json()[0]
    assert cue["origin"] == "auto_generated"
    assert cue["evidence"]["rule"] == "scene_ambience_bed"
    assert cue["userLocked"] is False
    manifest_path = Path(first.json()["manifestPath"])
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifestType"] == "sound_plan_manifest"
    assert manifest["payload"]["budgets"] == {"sfxLimit": 2, "sfxUsed": 0}
    versions = list(manifest_path.parent.glob("sound_plan_manifest.*.json"))
    assert len(versions) == 2

    muted = client.patch(
        f"/api/v1/projects/{project_id}/sound-cues/{cue['id']}", json={"muted": True}
    )
    assert muted.status_code == 200
    assert muted.json()["muted"] is True
    assert muted.json()["userLocked"] is True
    clean = client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/sound-plan",
        json={"renderMode": "speech_only"},
    )
    assert clean.status_code == 201
    after_clean = client.get(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/sound-cues"
    ).json()
    assert [(item["id"], item["muted"]) for item in after_clean] == [(cue["id"], True)]


def test_sound_plan_never_touches_manual_or_locked_cues(client) -> None:
    project_id, chapter_id, scenes = _structured_project(
        client,
        "Chapter 1\n\nRain crossed the forest at night.",
    )
    container = client.app.state.container
    scene_id = scenes[0]["id"]
    with container.structure.database.session() as session:
        scene = session.get(SceneRecord, scene_id)
        assert scene is not None
        scene.atmosphere_profile_json = json.dumps(_profile(scene_id), sort_keys=True)
        session.commit()
    asset = container.ambience.create_asset(
        project_id,
        "Manual room",
        str(Path(container.projects.get(project_id).artifact_path) / "manual.wav"),
        "user supplied",
        "local_upload",
    )
    manual = container.ambience.create_cue(
        scene_id,
        asset.id,
        "ambience",
        25,
        -30,
        10,
        20,
        True,
        "light_cinematic",
        False,
    )
    locked = container.ambience.create_cue(
        scene_id,
        asset.id,
        "sfx",
        90,
        -27,
        0,
        0,
        False,
        "light_cinematic",
        False,
        origin="auto_generated",
        evidence_json=json.dumps({"planKey": "locked-old", "rule": "explicit_sound_event"}),
        user_locked=True,
    )

    response = client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/sound-plan",
        json={"renderMode": "light_cinematic"},
    )
    assert response.status_code == 201
    with container.structure.database.session() as session:
        manual_after = session.get(AmbienceCueRecord, manual.id)
        locked_after = session.get(AmbienceCueRecord, locked.id)
        assert manual_after is not None and locked_after is not None
        assert (manual_after.asset_id, manual_after.start_ms, manual_after.gain_db) == (
            asset.id,
            25,
            -30,
        )
        assert (locked_after.asset_id, locked_after.start_ms, locked_after.gain_db) == (
            asset.id,
            90,
            -27,
        )
        assert locked_after.evidence_json == json.dumps(
            {"planKey": "locked-old", "rule": "explicit_sound_event"}
        )


def test_sound_plan_never_regenerates_other_chapters_atmosphere_profiles(client) -> None:
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "Cross-chapter atmosphere", "rightsStatus": "declared"},
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project_id}/source/import",
        files={
            "file": (
                "book.txt",
                (
                    "Chapter 1: Arrival\n\nRain crossed the forest at night.\n\n"
                    "Chapter 2: Departure\n\nThe tavern room was quiet at dusk."
                ).encode(),
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert _wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(
        f"/api/v1/projects/{project_id}/structure/extract", json={"maxSegmentChars": 120}
    ).json()
    assert _wait_for_job(client, structured["id"])["status"] == "succeeded"

    chapters = client.get(f"/api/v1/projects/{project_id}/chapters").json()
    assert len(chapters) == 2
    chapter_one_id, chapter_two_id = chapters[0]["id"], chapters[1]["id"]
    scenes_one = client.get(f"/api/v1/chapters/{chapter_one_id}/scenes").json()
    assert scenes_one

    container = client.app.state.container
    good_profile_json = json.dumps(
        _profile(scenes_one[0]["id"], mood="joyful", tensionLevel=0.1, confidence=0.93),
        sort_keys=True,
    )
    with container.structure.database.session() as session:
        record = session.get(SceneRecord, scenes_one[0]["id"])
        assert record is not None
        record.atmosphere_profile_json = good_profile_json
        session.commit()

    # Chapter 2's scenes carry no profile at all, so planning chapter 2 must trigger
    # atmosphere generation -- scoped to chapter 2 only, never touching chapter 1.
    response = client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_two_id}/sound-plan",
        json={"renderMode": "light_cinematic"},
    )
    assert response.status_code == 201

    with container.structure.database.session() as session:
        after = session.get(SceneRecord, scenes_one[0]["id"])
        assert after is not None
        assert after.atmosphere_profile_json == good_profile_json


def test_pure_planner_places_opening_music_cue_that_ends_before_first_dialogue() -> None:
    profiles = {"scene_1": _profile("scene_1", mood="warm", tensionLevel=0.2)}
    segments = {
        "scene_1": (
            SegmentPlanInput("seg_narration", "The forest was quiet.", 0, 4000),
            SegmentPlanInput(
                "seg_dialogue",
                '"Wait," she said.',
                4000,
                6000,
                segment_type="dialogue",
            ),
        ),
    }

    plan = plan_chapter_sound("chapter_1", ["scene_1"], profiles, segments, "light_cinematic")

    music = [cue for cue in plan.cues if cue.kind == "music"]
    assert len(music) == 1
    cue = music[0]
    assert cue.rule == "chapter_opening_music"
    assert cue.start_ms == 0
    assert cue.duration_ms is not None
    # The cue must end at/before the first dialogue segment's start, never under it.
    assert cue.start_ms + cue.duration_ms <= 4000
    assert cue.fade_in_ms == 4000  # capped by the first paragraph's own duration
    assert cue.fade_out_ms == 1500


def test_pure_planner_places_at_most_one_peak_music_cue_and_only_in_dramatized() -> None:
    profiles = {
        "scene_1": _profile("scene_1", mood="calm", tensionLevel=0.2),
        "scene_2": _profile("scene_2", mood="tense", tensionLevel=0.85),
        "scene_3": _profile("scene_3", mood="tense", tensionLevel=0.9),
    }
    segments = {
        "scene_1": (SegmentPlanInput("seg_1", "Calm morning.", 0, 2000),),
        "scene_2": (SegmentPlanInput("seg_2", "Someone shouted.", 0, 2000),),
        "scene_3": (SegmentPlanInput("seg_3", "Another shout followed.", 0, 2000),),
    }
    settings = SoundPlanSettings(allow_opening_music=False)

    dramatized = plan_chapter_sound(
        "chapter_1", ["scene_1", "scene_2", "scene_3"], profiles, segments, "dramatized", settings
    )
    light = plan_chapter_sound(
        "chapter_1", ["scene_1", "scene_2", "scene_3"], profiles, segments, "light_cinematic", settings
    )

    peak_cues = [cue for cue in dramatized.cues if cue.rule == "emotional_peak_underscore"]
    assert len(peak_cues) == 1
    assert peak_cues[0].scene_id == "scene_2"
    assert not [cue for cue in light.cues if cue.kind == "music"]


def test_sfx_lock_key_scopes_to_event_anchor_not_whole_scene() -> None:
    locked_cue = AmbienceCueRecord(
        id="ambcue_locked",
        scene_id="scene_1",
        asset_id="ambasset_x",
        cue_type="sfx",
        start_ms=90,
        gain_db=-20.0,
        fade_in_ms=0,
        fade_out_ms=0,
        ducking=False,
        render_mode="light_cinematic",
        no_sfx=False,
        origin="auto_generated",
        evidence_json=json.dumps({"planKey": "old", "segmentId": "seg_door"}),
        muted=False,
        user_locked=True,
    )
    door_cue = PlannedSoundCue(
        scene_id="scene_1",
        kind="sfx",
        rule="explicit_sound_event",
        tags=("door_slam",),
        plan_key="new-door",
        segment_id="seg_door",
        start_ms=90,
    )
    thunder_cue = PlannedSoundCue(
        scene_id="scene_1",
        kind="sfx",
        rule="explicit_sound_event",
        tags=("thunder",),
        plan_key="new-thunder",
        segment_id="seg_thunder",
        start_ms=400,
    )

    locked_slots = {_cue_lock_key(locked_cue)}

    # Locking one SFX cue must not block an unrelated SFX event in the same scene.
    assert _planned_lock_key(door_cue) in locked_slots
    assert _planned_lock_key(thunder_cue) not in locked_slots
