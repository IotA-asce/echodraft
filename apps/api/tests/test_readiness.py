import time


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def structured_project(client) -> tuple[str, str]:
    project = client.post(
        "/api/v1/projects", json={"title": "Readiness", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("ready.txt", b"Chapter 1\n\nReady checks need audio.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    return project, chapter


def test_readiness_report_persists_checks_and_issue_resolution(client) -> None:
    project, chapter = structured_project(client)

    report = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    assert report["status"] == "blocked"
    assert report["chapterId"] == chapter
    categories = {check["category"] for check in report["checks"]}
    assert "readiness_voice" in categories
    assert "readiness_audio" in categories
    voice_check = next(check for check in report["checks"] if check["id"] == "voice_narrator_missing")
    assert voice_check["issueId"]
    assert voice_check["resolutionStatus"] == "open"

    client.patch(f"/api/v1/issues/{voice_check['issueId']}", json={"status": "ignored"})
    rerun = client.post(
        f"/api/v1/projects/{project}/readiness/run", json={"chapterId": chapter}
    ).json()
    rerun_voice = next(check for check in rerun["checks"] if check["id"] == "voice_narrator_missing")
    assert rerun_voice["issueId"] == voice_check["issueId"]
    assert rerun_voice["resolutionStatus"] == "ignored"

    latest = client.get(
        f"/api/v1/projects/{project}/readiness/latest?chapter_id={chapter}"
    ).json()
    assert latest["id"] == rerun["id"]
    history = client.get(f"/api/v1/projects/{project}/readiness/reports").json()
    assert [item["id"] for item in history][:2] == [rerun["id"], report["id"]]
