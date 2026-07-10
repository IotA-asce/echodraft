import time

from echodraft_api.automatic_casting import AutomaticCastingService, detect_point_of_view


def _wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


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
