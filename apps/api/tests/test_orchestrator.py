import threading
import time

from echodraft_api.orchestrator import (
    AdaptiveWorkerPool,
    CheckpointStore,
    HardwareSnapshot,
    SingleWriterQueue,
    Stage,
    Unit,
    WorkQueue,
    recommended_llm_workers,
)


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


def test_job_events_sse_endpoint_replays_persisted_events(client) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"title": "Orchestrator", "rightsStatus": "declared"},
    ).json()
    container = client.app.state.container
    job = container.jobs_repository.create("eval.test", project_id=project["id"])
    first = container.orchestrator_repository.append_event(
        job_id=job.id,
        project_id=project["id"],
        event_type="job.running",
        stage="structure",
        payload={"message": "started"},
    )
    second = container.orchestrator_repository.append_event(
        job_id=job.id,
        project_id=project["id"],
        event_type="stage.done",
        stage="structure",
        scope={"chapter": 1},
    )

    response = client.get(f"/api/v1/events?jobId={job.id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert f"id: {first.event_id}" in response.text
    assert "event: job.running" in response.text
    assert '"message": "started"' in response.text
    assert f"id: {second.event_id}" in response.text

    filtered = client.get(
        f"/api/v1/events?jobId={job.id}",
        headers={"Last-Event-ID": str(first.event_id)},
    )

    assert f"id: {first.event_id}" not in filtered.text
    assert f"id: {second.event_id}" in filtered.text


def test_hardware_probe_recommends_adaptive_llm_workers() -> None:
    assert recommended_llm_workers(HardwareSnapshot(cpu_count=8, total_ram_gib=8)) == 1
    assert recommended_llm_workers(HardwareSnapshot(cpu_count=8, total_ram_gib=16)) == 2
    assert recommended_llm_workers(HardwareSnapshot(cpu_count=8, total_ram_gib=64)) == 4
    assert recommended_llm_workers(HardwareSnapshot(cpu_count=8, total_ram_gib=64), 3) == 3


def test_adaptive_worker_pool_limits_llm_concurrency() -> None:
    pool = AdaptiveWorkerPool("llm-test", max_workers=2)
    barrier = threading.Barrier(2)
    observed_threads: set[str] = set()

    def operation() -> str:
        observed_threads.add(threading.current_thread().name)
        barrier.wait(timeout=2)
        time.sleep(0.01)
        return "done"

    results: list[str] = []
    threads = [threading.Thread(target=lambda: results.append(pool.run(operation))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    pool.shutdown()

    assert results == ["done", "done"]
    assert all(name.startswith("echodraft-llm-test") for name in observed_threads)


def test_writer_queue_serializes_parallel_cache_writes(client) -> None:
    container = client.app.state.container
    errors: list[str] = []

    def write_cache(index: int) -> None:
        try:
            container.orchestrator_pools.writer.run(
                lambda: container.orchestrator_repository.put_cache(
                    cache_key=f"parallel_cache_{index}",
                    kind="llm",
                    model_id="qwen3:4b",
                    value_json={"index": index},
                    size_bytes=1,
                )
            )
        except Exception as error:  # pragma: no cover - assertion reports the message.
            errors.append(str(error))

    threads = [threading.Thread(target=write_cache, args=(index,)) for index in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    assert container.orchestrator_repository.cache_entry("parallel_cache_11") is not None


def test_writer_queue_runs_only_one_operation_at_a_time() -> None:
    writer = SingleWriterQueue()
    active = 0
    max_active = 0
    guard = threading.Lock()

    def operation() -> None:
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.01)
        with guard:
            active -= 1

    threads = [threading.Thread(target=lambda: writer.run(operation)) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert max_active == 1
