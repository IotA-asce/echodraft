import json
import time
from pathlib import Path


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def project_with_segment(client) -> tuple[str, str, str]:
    project = client.post(
        "/api/v1/projects", json={"title": "TTS Upgrade", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("tts.txt", b"Chapter 1\n\nHurry now, local voice.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene = client.get(f"/api/v1/chapters/{chapter}/scenes").json()[0]["id"]
    segment = client.get(f"/api/v1/scenes/{scene}/segments").json()[0]["id"]
    return project, chapter, segment


def test_tts_provider_registry_exposes_local_options(client) -> None:
    providers = client.get("/api/v1/settings/tts/providers").json()
    by_provider = {item["provider"]: item for item in providers}

    assert {"mock", "kokoro", "piper", "xtts_v2"}.issubset(by_provider)
    assert by_provider["mock"]["ready"] is True
    assert by_provider["piper"]["setupMode"] == "local_cli"
    assert by_provider["xtts_v2"]["requiresReferenceConsent"] is True


def test_provider_direction_capability_is_truthful(client) -> None:
    from echodraft_api.tts_providers import (
        KokoroTtsAdapter,
        ManagedKokoroOnnxAdapter,
        XttsV2Adapter,
    )

    providers = client.get("/api/v1/settings/tts/providers").json()
    by_provider = {item["provider"]: item for item in providers}

    # In the default (custom-adapter) state the kokoro registry entry has no CLI
    # contract to send pace: it may only advertise the pauses assembly honors.
    assert by_provider["kokoro"]["capabilities"]["direction"] == ["pauseAfterMs", "pauseBeforeMs"]
    # XTTS-v2 has no per-line direction hook: pauses only, no fake stylePrompt claim.
    assert by_provider["xtts_v2"]["capabilities"]["direction"] == [
        "pauseAfterMs",
        "pauseBeforeMs",
    ]
    assert "stylePrompt" not in by_provider["xtts_v2"]["capabilities"]["direction"]
    # Piper honors pace natively plus the assembly-level pauses.
    assert by_provider["piper"]["capabilities"]["direction"] == [
        "pace",
        "pauseAfterMs",
        "pauseBeforeMs",
    ]

    # Managed Kokoro genuinely transmits pace (via --speed) and pauses via assembly.
    managed = ManagedKokoroOnnxAdapter(None, None, None, None, None)
    assert managed.capability()["capabilities"]["direction"] == [
        "pace",
        "pauseAfterMs",
        "pauseBeforeMs",
    ]
    # The adapter-native contracts never claim engine-side pace they cannot send.
    assert KokoroTtsAdapter(None, None, None).capability()["capabilities"]["direction"] == [
        "pauseAfterMs",
        "pauseBeforeMs",
    ]
    assert XttsV2Adapter(None, None, False, "en").capability()["capabilities"]["direction"] == [
        "pauseAfterMs",
        "pauseBeforeMs",
    ]


def test_character_voice_suggestions_rank_by_traits(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Voice Suggestions", "rightsStatus": "declared"}
    ).json()["id"]
    character = client.post(
        f"/api/v1/projects/{project}/characters",
        json={
            "displayName": "Captain Mara",
            "traits": ["gender:feminine", "accent:irish", "age:young", "role:captain"],
        },
    ).json()
    matching = client.post(
        f"/api/v1/projects/{project}/voices",
        json={
            "name": "Young Irish Female",
            "backend": "kokoro",
            "providerVoiceId": "kokoro_female_irish_young",
            "stylePrompt": "young Irish woman, crisp captain energy",
        },
    ).json()
    client.post(
        f"/api/v1/projects/{project}/voices",
        json={
            "name": "Older Neutral",
            "backend": "kokoro",
            "providerVoiceId": "kokoro_neutral_old",
            "stylePrompt": "older neutral narrator",
        },
    )

    response = client.get(f"/api/v1/characters/{character['id']}/voice-suggestions")

    assert response.status_code == 200
    suggestions = response.json()
    assert suggestions[0]["voiceProfileId"] == matching["id"]
    assert suggestions[0]["score"] > suggestions[1]["score"]
    assert "accent:irish" in suggestions[0]["matchedTraits"]
    assert suggestions[0]["sampleText"].startswith("Captain Mara")


def test_render_queue_pronunciations_and_compare(client) -> None:
    project, chapter, segment = project_with_segment(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.post(
        f"/api/v1/projects/{project}/pronunciations",
        json={"term": "Hurry", "replacementText": "Her-ree"},
    )
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )

    first_job = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, first_job["id"])["status"] == "succeeded"
    queue = client.get(f"/api/v1/projects/{project}/render-queue?chapter_id={chapter}").json()
    assert queue and queue[0]["status"] == "succeeded"
    assert queue[0]["provider"] == "mock"
    render = client.get(f"/api/v1/projects/{project}/segments/{segment}/renders").json()[0]
    metadata = json.loads(Path(render["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["text"].startswith("Hurry")
    assert metadata["synthesisText"].startswith("Her-ree")
    assert metadata["ttsProvider"]["provider"] == "mock"
    assert metadata["pronunciationsApplied"][0]["term"] == "Hurry"

    client.post(
        f"/api/v1/projects/{project}/pronunciations",
        json={"term": "voice", "replacementText": "voyce"},
    )
    stale = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/production-status").json()
    assert stale["currentSegments"] == stale["totalSegments"] - 1
    second_job = client.post(
        f"/api/v1/projects/{project}/chapters/{chapter}/produce?force=true"
    ).json()
    assert wait_for_job(client, second_job["id"])["status"] == "succeeded"

    comparison = client.get(
        f"/api/v1/projects/{project}/segments/{segment}/renders/compare"
    ).json()
    assert comparison["currentRender"]
    assert comparison["previousRender"]
    assert "synthesisText" in comparison["changedFields"]
    assert "pronunciationsApplied" in comparison["changedFields"]
