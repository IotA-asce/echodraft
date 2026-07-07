from echodraft_api.orchestrator import CheckpointStore, Stage, Unit, WorkQueue


def test_orchestrator_checkpoint_store_and_work_queue(client) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"title": "Orchestrator", "rightsStatus": "declared"},
    ).json()
    container = client.app.state.container
    job = container.jobs_repository.create("eval.test", project_id=project["id"])
    store = CheckpointStore(container.orchestrator_repository)
    stage = Stage("structure_map", "v1")
    unit = Unit(stage=stage, job_id=job.id, project_id=project["id"], scope={"chapter": 1})

    queue = WorkQueue([unit])
    assert queue.pop_ready(store) == unit

    pending = store.mark_pending(unit)
    assert pending.status == "pending"
    running = store.mark_running(unit)
    assert running.status == "running"
    assert running.attempt == 1
    done = store.mark_done(unit, output_ref="manifests/structure.json")
    assert done.status == "done"
    assert done.output_ref == "manifests/structure.json"

    queue.push(unit)
    assert queue.pop_ready(store) is None


def test_orchestrator_repository_cache_and_events(client) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"title": "Orchestrator", "rightsStatus": "declared"},
    ).json()
    container = client.app.state.container
    job = container.jobs_repository.create("eval.test", project_id=project["id"])
    repository = container.orchestrator_repository

    repository.put_cache(
        cache_key="cache_1",
        kind="llm",
        model_id="qwen3:4b",
        schema_id="speaker-attribution",
        value_json={"speaker": "Mara"},
        size_bytes=18,
    )
    cache_entry = repository.cache_entry("cache_1", record_hit=True)
    assert cache_entry is not None
    assert cache_entry.hit_count == 1
    assert cache_entry.value_json == '{"speaker": "Mara"}'

    first = repository.append_event(
        job_id=job.id,
        project_id=project["id"],
        event_type="job.running",
        stage="structure",
        payload={"message": "started"},
    )
    second = repository.append_event(
        job_id=job.id,
        project_id=project["id"],
        event_type="stage.done",
        stage="structure",
        scope={"chapter": 1},
    )

    events = repository.events_for_job(job.id, after_event_id=first.event_id)
    assert [event.event_id for event in events] == [second.event_id]
    assert events[0].type == "stage.done"
