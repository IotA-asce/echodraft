import time
from types import SimpleNamespace

import echodraft_api.cast_discovery as cast_discovery_module
import echodraft_api.structure as structure_module
import pytest


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(60):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def project_with_source(client, text: str) -> str:
    project = client.post("/api/v1/projects", json={"title": "Structure", "rightsStatus": "declared"}).json()["id"]
    job = client.post(f"/api/v1/projects/{project}/source/import", files={"file": ("book.txt", text.encode(), "text/plain")}, data={"rightsAcknowledged": "true"}).json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"
    return project


def extract(client, project: str) -> None:
    job = client.post(f"/api/v1/projects/{project}/structure/extract", json={"maxSegmentChars": 120}).json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"


def atom_ids_from_prompt(prompt: str) -> list[str]:
    return [line.split()[1] for line in prompt.splitlines() if line.startswith("ATOM ")]


def all_segments(client, project: str) -> list[dict]:
    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    scenes = [
        scene
        for chapter in chapters
        for scene in client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()
    ]
    return [
        segment
        for scene in scenes
        for segment in client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    ]


def warning_codes(client, project: str) -> set[str]:
    warnings = client.get(f"/api/v1/projects/{project}/structure-warnings").json()
    return {str(warning["evidence"].get("code") or "") for warning in warnings}


def test_heading_scene_and_sentence_safe_segments(client) -> None:
    project = project_with_source(client, "Chapter 1: Arrival\n\nMara arrived. Theo said hello.\n\n***\n\nA second scene begins. It ends here.\n\nChapter 2: Night\n\nFinal sentence.")
    extract(client, project)
    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    assert len(chapters) == 2 and chapters[0]["status"] == "structured"
    scenes = client.get(f"/api/v1/chapters/{chapters[0]['id']}/scenes").json()
    assert len(scenes) == 2
    segments = client.get(f"/api/v1/scenes/{scenes[0]['id']}/segments").json()
    assert all(item["textContent"][-1] in ".!?" for item in segments)
    assert any(item["speakerCandidate"] == "Theo" for item in segments)


def test_unresolved_structure_and_segment_revision_history(client) -> None:
    project = project_with_source(client, "A single paragraph with no heading. Another complete sentence.")
    extract(client, project)
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    assert chapter["status"] == "unresolved"
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segment = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()[0]
    edited = client.patch(f"/api/v1/segments/{segment['id']}", json={"textContent": "Corrected sentence."}).json()
    assert edited["revision"] == 2 and edited["status"] == "needs_review"
    revisions = client.get(f"/api/v1/segments/{segment['id']}/revisions").json()
    assert revisions[0]["revision"] == 1


def test_structure_parser_v2_front_matter_dialogue_and_warnings(client) -> None:
    project = project_with_source(
        client,
        "Dedication\n\n# Prologue\n\n[softly]\n\n\"Hello,\" she said.\n\nScene 2\n\nMara: We go.\n\nChapter 1: Start\n\nA final sentence.",
    )
    extract(client, project)

    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    assert [chapter["title"] for chapter in chapters][:2] == ["Front matter", "Prologue"]
    assert chapters[0]["status"] == "front_matter"
    warnings = client.get(f"/api/v1/projects/{project}/structure-warnings").json()
    assert any("Dialogue segment" in warning["message"] for warning in warnings)

    scenes = client.get(f"/api/v1/chapters/{chapters[1]['id']}/scenes").json()
    segments = [item for scene in scenes for item in client.get(f"/api/v1/scenes/{scene['id']}/segments").json()]
    assert any(item["segmentType"] == "performance_beat" for item in segments)
    assert any(item["segmentType"] == "dialogue" and item["speakerCandidate"] == "Mara" for item in segments)
    assert all("parserEvidence" in item for item in segments)


def test_chapter_title_line_and_h3_h4_headings(client) -> None:
    project = project_with_source(
        client,
        "Chapter One\n"
        "The Door\n\n"
        "A first scene sentence.\n\n"
        "### Interior Beat\n\n"
        "This should stay inside chapter one.\n\n"
        "#### Camera Note\n\n"
        "This also stays inside chapter one.\n\n"
        "Chapter Two\n\n"
        "The ending.",
    )
    extract(client, project)

    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    assert [chapter["title"] for chapter in chapters] == [
        "Chapter One - The Door",
        "Chapter Two",
    ]


def test_explicit_and_possible_scene_breaks_report_quality(client) -> None:
    project = project_with_source(
        client,
        "Chapter 1\n\n"
        "The opening has enough body text to count before the separator.\n\n"
        "***\n\n"
        "A second scene has enough body text before time shifts arrive.\n\n"
        "Later that night, the windows rattled.\n\n"
        "The aftermath continued.",
    )
    extract(client, project)

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scenes = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()
    assert len(scenes) == 3
    assert any(scene["confidence"] >= 0.9 for scene in scenes)
    assert "scene.possible_break_detected" in warning_codes(client, project)
    quality = client.get(f"/api/v1/projects/{project}/structure/quality").json()
    assert quality["sceneCount"] == 3
    assert quality["possibleSceneBreakCount"] == 1


def test_quote_tags_apostrophes_and_mixed_paragraphs(client) -> None:
    project = project_with_source(
        client,
        "Chapter 1\n\n"
        "\"I don't know,\" Mary-Jane said. I'm ready.\n\n"
        "\"Are you?\" asked Dr. Sen.\n\n"
        "[whispering]",
    )
    extract(client, project)

    segments = all_segments(client, project)
    assert [segment["segmentType"] for segment in segments] == [
        "dialogue",
        "narration",
        "dialogue",
        "performance_beat",
    ]
    assert segments[0]["speakerCandidate"] == "Mary-Jane"
    assert segments[1]["textContent"] == "I'm ready."
    assert segments[2]["speakerCandidate"] == "Dr. Sen"
    assert segments[0]["parserEvidence"]["productionType"] == "dialogue_with_tag"


def test_alternating_unattributed_dialogue_remains_reviewable(client) -> None:
    project = project_with_source(client, "Chapter 1\n\n\"Yes.\"\n\n\"No.\"")
    extract(client, project)

    segments = all_segments(client, project)
    dialogue = [segment for segment in segments if segment["segmentType"] == "dialogue"]
    assert len(dialogue) == 2
    assert all(segment["status"] == "needs_review" for segment in dialogue)
    assert "segment.dialogue_no_speaker" in warning_codes(client, project)


def test_segment_split_merge_and_lock_survives_reextract(client) -> None:
    project = project_with_source(
        client,
        "Chapter 1\n\nA first sentence that is long enough to split near the middle. A second sentence follows for merging.",
    )
    extract(client, project)
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    target = segments[0]

    split_offset = target["textContent"].index(" enough")
    split = client.post(
        f"/api/v1/segments/{target['id']}/split", json={"splitOffset": split_offset}
    )
    assert split.status_code == 200
    split_segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert len(split_segments) == len(segments) + 1

    merged = client.post(
        f"/api/v1/segments/{split_segments[0]['id']}/merge",
        json={"nextSegmentId": split_segments[1]["id"]},
    )
    assert merged.status_code == 200
    merged_segment = merged.json()
    locked = client.put(
        f"/api/v1/structure-locks/segment/{merged_segment['id']}",
        json={"locked": True, "reason": "Keep editorial split"},
    ).json()
    assert locked["userLocked"] is True

    extract(client, project)
    chapters = client.get(f"/api/v1/projects/{project}/chapters").json()
    scenes = [scene for chapter in chapters for scene in client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()]
    all_segments = [
        segment
        for scene in scenes
        for segment in client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    ]
    assert any(
        segment["id"] == merged_segment["id"] and segment["userLocked"]
        for segment in all_segments
    )


def test_llm_structure_refinement_creates_cast_and_speaker_rows(client, monkeypatch) -> None:
    monkeypatch.setattr(
        structure_module.StructureService,
        "_local_llm_ready",
        lambda _self: (True, "ready"),
    )
    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_local_llm_ready",
        lambda _self: True,
    )

    def fake_extract(_self, _project_id, request, _job_id=None):
        if request.task == "atom_segment_refinement":
            atom_ids = atom_ids_from_prompt(request.prompt)
            return SimpleNamespace(
                run=SimpleNamespace(id="llmrun_segments"),
                result={
                    "segments": [
                        {
                            "atomIds": atom_ids[:2],
                            "segmentType": "dialogue",
                            "speakerHint": "Mara",
                            "confidence": 0.93,
                            "evidence": "speaker label",
                        },
                        {
                            "atomIds": atom_ids[2:],
                            "segmentType": "narration",
                            "speakerHint": "",
                            "confidence": 0.9,
                            "evidence": "narrative sentence",
                        },
                    ],
                    "warnings": [],
                },
            )
        if request.task == "cast_discovery":
            segment_id = request.prompt.split("- ", 1)[1].split(" ", 1)[0]
            return SimpleNamespace(
                run=SimpleNamespace(id="llmrun_cast"),
                result={
                    "characters": [
                        {
                            "displayName": "Mara",
                            "canonicalName": "Mara",
                            "aliases": [],
                            "firstSeenSegmentId": segment_id,
                            "roleGuess": "supporting",
                            "confidence": 0.94,
                            "evidence": ["Mara: We leave now."],
                        }
                    ],
                    "warnings": [],
                },
            )
        if request.task == "cast_merge_verification":
            return SimpleNamespace(
                run=SimpleNamespace(id="llmrun_merge"),
                result={
                    "decisions": [
                        {
                            "displayName": "Mara",
                            "action": "create_new",
                            "targetName": "",
                            "aliases": [],
                            "confidence": 0.94,
                            "reason": "unique observed speaker",
                        }
                    ],
                    "warnings": [],
                },
            )
        return SimpleNamespace(run=SimpleNamespace(id="llmrun_empty"), result={"attributions": [], "warnings": []})

    monkeypatch.setattr(structure_module.LocalLlmService, "extract", fake_extract)
    project = project_with_source(
        client,
        'Chapter 1\n\n"We leave now," Mara said. The rain answered.',
    )

    extract(client, project)

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert [segment["segmentType"] for segment in segments] == ["dialogue", "narration"]
    assert segments[0]["speakerCandidate"] == "Mara"
    assert "optional_atom_llm_grouping" in segments[0]["parserEvidence"]["sources"]

    characters = client.get(f"/api/v1/projects/{project}/characters").json()
    mara = next(character for character in characters if character["displayName"] == "Mara")
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    mara_row = next(item for item in attributions if item["speakerName"] == "Mara")
    assert mara_row["status"] == "approved"
    assert mara_row["characterId"] == mara["id"]


def test_invalid_llm_structure_refinement_falls_back_with_warning(client, monkeypatch) -> None:
    monkeypatch.setattr(
        structure_module.StructureService,
        "_local_llm_ready",
        lambda _self: (True, "ready"),
    )
    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_local_llm_ready",
        lambda _self: True,
    )

    def fake_extract(_self, _project_id, request, _job_id=None):
        if request.task == "atom_segment_refinement":
            atom_ids = atom_ids_from_prompt(request.prompt)
            return SimpleNamespace(
                run=SimpleNamespace(id="llmrun_bad_segments"),
                result={
                    "segments": [
                        {
                            "atomIds": atom_ids[:-1],
                            "segmentType": "dialogue",
                            "text": "Mara: We leave now. Invented text.",
                            "speakerHint": "Mara",
                            "confidence": 0.9,
                            "evidence": "bad output",
                        }
                    ],
                    "warnings": [],
                },
            )
        return SimpleNamespace(
            run=SimpleNamespace(id="llmrun_empty"),
            result={"characters": [], "decisions": [], "attributions": [], "warnings": []},
        )

    monkeypatch.setattr(structure_module.LocalLlmService, "extract", fake_extract)
    project = project_with_source(client, "Chapter 1\n\nMara: We leave now.")

    extract(client, project)

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert [segment["textContent"] for segment in segments] == ["Mara: We leave now."]
    warnings = client.get(f"/api/v1/projects/{project}/structure-warnings").json()
    assert any("failed validation" in warning["message"] for warning in warnings)


@pytest.mark.parametrize(
    "case",
    ["missing", "duplicate", "out_of_order", "invented", "non_adjacent"],
)
def test_invalid_atom_groupings_are_rejected(client, monkeypatch, case) -> None:
    monkeypatch.setattr(
        structure_module.StructureService,
        "_local_llm_ready",
        lambda _self: (True, "ready"),
    )
    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_local_llm_ready",
        lambda _self: False,
    )

    def fake_extract(_self, _project_id, request, _job_id=None):
        if request.task == "atom_segment_refinement":
            atom_ids = atom_ids_from_prompt(request.prompt)
            if case == "missing":
                payload = [{"atomIds": atom_ids[:-1], "segmentType": "narration"}]
            elif case == "duplicate":
                payload = [
                    {"atomIds": atom_ids[:2], "segmentType": "dialogue", "speakerHint": "Mara"},
                    {"atomIds": atom_ids[1:], "segmentType": "narration"},
                ]
            elif case == "out_of_order":
                payload = [{"atomIds": [atom_ids[1], atom_ids[0]], "segmentType": "dialogue"}]
            elif case == "invented":
                payload = [{"atomIds": ["atom_not_real"], "segmentType": "narration"}]
            else:
                payload = [{"atomIds": [atom_ids[0], atom_ids[2]], "segmentType": "narration"}]
            return SimpleNamespace(
                run=SimpleNamespace(id=f"llmrun_bad_{case}"),
                result={"segments": payload, "warnings": []},
            )
        return SimpleNamespace(
            run=SimpleNamespace(id="llmrun_empty"),
            result={"characters": [], "decisions": [], "attributions": [], "warnings": []},
        )

    monkeypatch.setattr(structure_module.LocalLlmService, "extract", fake_extract)
    project = project_with_source(
        client,
        'Chapter 1\n\n"One," Mara said. The room held still. "Two," Theo said.',
    )

    extract(client, project)

    assert "llm.validation_failed" in warning_codes(client, project)
    assert all("Invented" not in segment["textContent"] for segment in all_segments(client, project))


def test_cast_candidates_and_speaker_rows_from_parser_evidence(client) -> None:
    project = project_with_source(
        client,
        "Chapter 1\n\n"
        "Dr. Sen: Begin.\n\n"
        "Mary-Jane: Wait.\n\n"
        "Captain Arjun: Hold.\n\n"
        "Mother: Come here.",
    )
    extract(client, project)

    characters = client.get(f"/api/v1/projects/{project}/characters").json()
    names = {character["displayName"] for character in characters}
    assert {"Dr. Sen", "Mary-Jane", "Captain Arjun", "Mother"} <= names
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    approved = {row["speakerName"]: row for row in attributions if row["status"] == "approved"}
    assert {"Dr. Sen", "Mary-Jane", "Captain Arjun", "Mother"} <= set(approved)


def test_possible_duplicate_cast_name_creates_review_issue(client) -> None:
    project = project_with_source(client, "Chapter 1\n\nMary-Jane: Wait.")
    existing = client.post(
        f"/api/v1/projects/{project}/characters",
        json={"displayName": "Mary"},
    ).json()

    extract(client, project)

    characters = client.get(f"/api/v1/projects/{project}/characters").json()
    assert [character["displayName"] for character in characters] == [existing["displayName"]]
    issues = client.get(f"/api/v1/projects/{project}/issues").json()
    assert any(issue["title"] == "Ambiguous cast candidate" for issue in issues)


def test_cast_discovery_uses_aliases_without_creating_duplicates(client) -> None:
    project = project_with_source(client, "Chapter 1\n\nCaptain Vale: Report.")
    character = client.post(
        f"/api/v1/projects/{project}/characters",
        json={"displayName": "Mara", "aliases": ["Captain Vale"]},
    ).json()

    extract(client, project)

    characters = client.get(f"/api/v1/projects/{project}/characters").json()
    active = [item for item in characters if not item["mergedIntoCharacterId"]]
    assert [item["displayName"] for item in active] == ["Mara"]
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    row = next(item for item in attributions if item["speakerName"] == "Captain Vale")
    assert row["status"] == "approved"
    assert row["characterId"] == character["id"]
