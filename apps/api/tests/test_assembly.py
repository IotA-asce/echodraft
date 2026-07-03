import json
import time
import wave
from pathlib import Path

import pytest
from sqlalchemy import text

from echodraft_api.assembly import ChapterAssembler


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(60):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_chapter_assembly_pins_ordered_renders_and_emits_stem(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Assembly", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                (
                    b"Chapter 1: Arrival\n\n"
                    b"The first passage has enough carefully chosen words to exceed the segment "
                    b"boundary without relying on implementation-specific paragraph behavior. "
                    b"The second passage also has enough carefully chosen words to become a "
                    b"separate renderable segment in the chapter assembly test."
                ),
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(
        f"/api/v1/projects/{project}/structure/extract", json={"maxSegmentChars": 120}
    ).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert len(segments) >= 2
    rendered = []
    for segment in segments:
        response = client.post(
            f"/api/v1/projects/{project}/segments/{segment['id']}/generate",
            json={
                "voiceProfileId": "voice_test",
                "direction": {"scopeType": "project", "scopeId": project},
            },
        )
        assert response.status_code == 202
        rendered.append(response.json())

    response = client.post(f"/api/v1/projects/{project}/chapters/{chapter['id']}/assemble")
    assert response.status_code == 202, response.text
    assembled = response.json()
    manifest = json.loads(Path(assembled["manifestPath"]).read_text())
    assert [item["segmentRenderId"] for item in manifest["inputs"]] == [
        item["id"] for item in rendered
    ]
    assert Path(assembled["speechPath"]).is_file()
    with wave.open(assembled["speechPath"]) as output:
        assert output.getframerate() == 16_000
        assert output.getnchannels() == 1
    assert assembled["durationMs"] >= sum(item["durationMs"] for item in rendered) + 350
    assert (
        client.get(f"/api/v1/projects/{project}/chapters/{chapter['id']}/renders").json()[0]["id"]
        == assembled["id"]
    )
    assert (
        client.get(f"/api/v1/projects/{project}/chapters/{chapter['id']}/active-render").json()[
            "id"
        ]
        == assembled["id"]
    )


def test_chapter_assembly_writes_real_waveform_and_validation_telemetry(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Real Telemetry", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"A sentence to assemble for telemetry checks.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene_id = client.get(f"/api/v1/chapters/{chapter_id}/scenes").json()[0]["id"]
    segment_id = client.get(f"/api/v1/scenes/{scene_id}/segments").json()[0]["id"]
    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment_id}/generate",
        json={
            "voiceProfileId": "voice_test",
            "direction": {"scopeType": "project", "scopeId": project},
        },
    )
    assert rendered.status_code == 202

    assembled = client.post(f"/api/v1/projects/{project}/chapters/{chapter_id}/assemble")
    assert assembled.status_code == 202, assembled.text
    root = Path(assembled.json()["manifestPath"]).parent
    waveform = json.loads((root / "waveform.json").read_text())
    validation = json.loads((root / "validation_report.json").read_text())

    # Old fake was a hardcoded empty list regardless of content; the real analysis always
    # produces the full bucket count.
    assert len(waveform["peaks"]) == 200
    # The mock provider renders pure digital silence, so honest chapter QA must surface
    # `low_loudness` (RMS floors at -120 dBFS) as a warning finding -- which, being
    # non-blocking, still leaves the validation status "passed".
    findings = {item["category"]: item["severity"] for item in validation["findings"]}
    assert findings["low_loudness"] == "warning"
    assert not any(severity == "blocking" for severity in findings.values())
    assert validation["status"] == "passed"


def test_chapter_assembly_selects_latest_render_despite_adversarial_ids(client, app) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Adversarial", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                (
                    b"Chapter 1: Arrival\n\n"
                    b"The first passage has enough carefully chosen words to exceed the segment "
                    b"boundary without relying on implementation-specific paragraph behavior. "
                    b"The second passage also has enough carefully chosen words to become a "
                    b"separate renderable segment in the chapter assembly test."
                ),
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(
        f"/api/v1/projects/{project}/structure/extract", json={"maxSegmentChars": 120}
    ).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    assert len(segments) >= 2
    for segment in segments:
        response = client.post(
            f"/api/v1/projects/{project}/segments/{segment['id']}/generate",
            json={
                "voiceProfileId": "voice_test",
                "direction": {"scopeType": "project", "scopeId": project},
            },
        )
        assert response.status_code == 202
    target = segments[0]["id"]
    old_render_id = client.get(f"/api/v1/projects/{project}/segments/{target}/renders").json()[
        0
    ]["id"]
    rerender = client.post(
        f"/api/v1/projects/{project}/segments/{target}/generate",
        json={
            "voiceProfileId": "voice_test",
            "direction": {"scopeType": "project", "scopeId": project},
            "force": True,
        },
    )
    assert rerender.status_code == 202
    new_render_id = rerender.json()["id"]
    assert new_render_id != old_render_id

    # Give the *older* render an id that sorts after every uuid-hex id so any
    # lookup still ordering by id DESC would pick the stale render.
    adversarial_id = "rend_ffffffffffffffff"
    with app.state.container.structure.database.session() as session:
        session.execute(
            text("UPDATE segment_renders SET id = :new WHERE id = :old"),
            {"new": adversarial_id, "old": old_render_id},
        )
        session.execute(
            text(
                "UPDATE segment_renders SET parent_render_id = :new "
                "WHERE parent_render_id = :old"
            ),
            {"new": adversarial_id, "old": old_render_id},
        )
        session.commit()

    response = client.post(f"/api/v1/projects/{project}/chapters/{chapter['id']}/assemble")
    assert response.status_code == 202, response.text
    manifest = json.loads(Path(response.json()["manifestPath"]).read_text())
    stitched = {item["segmentId"]: item["segmentRenderId"] for item in manifest["inputs"]}
    assert stitched[target] == new_render_id
    assert adversarial_id not in stitched.values()

    active = client.get(
        f"/api/v1/projects/{project}/chapters/{chapter['id']}/active-render"
    ).json()
    assert active["id"] == response.json()["id"]


def test_chapter_assembly_rejects_stale_render_revision(client, app) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Stale revision", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"A sentence that will go stale.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene_id = client.get(f"/api/v1/chapters/{chapter_id}/scenes").json()[0]["id"]
    segment_id = client.get(f"/api/v1/scenes/{scene_id}/segments").json()[0]["id"]
    rendered = client.post(
        f"/api/v1/projects/{project}/segments/{segment_id}/generate",
        json={
            "voiceProfileId": "voice_test",
            "direction": {"scopeType": "project", "scopeId": project},
        },
    )
    assert rendered.status_code == 202
    assembled = client.post(f"/api/v1/projects/{project}/chapters/{chapter_id}/assemble")
    assert assembled.status_code == 202, assembled.text

    # Bump the segment revision without re-rendering: the stored render is now stale.
    patched = client.patch(
        f"/api/v1/segments/{segment_id}",
        json={"textContent": "A sentence that went stale after the render."},
    )
    assert patched.status_code == 200
    assert patched.json()["revision"] == 2

    assembler = ChapterAssembler(app.state.container)
    with pytest.raises(ValueError, match="Stale render"):
        assembler.assemble(project, chapter_id)


def test_chapter_assembly_rejects_missing_segment_render(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Missing render", "rightsStatus": "declared"}
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"Only sentence.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, import_job["id"])["status"] == "succeeded"
    structure_job = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structure_job["id"])["status"] == "succeeded"
    chapter_id = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]

    response = client.post(f"/api/v1/projects/{project}/chapters/{chapter_id}/assemble")
    assert response.status_code == 422
    assert "Missing successful render" in response.json()["detail"]
