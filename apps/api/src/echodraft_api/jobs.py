from collections.abc import Callable
from threading import Thread

from echodraft_db import JobRepository
from echodraft_domain import Job, JobState


class InProcessJobRunner:
    def __init__(self, repository: JobRepository) -> None:
        self.repository = repository

    def enqueue(self, job_type: str, project_id: str | None = None, target_id: str | None = None) -> Job:
        return self.repository.create(job_type, project_id, target_id)

    def run_inline(self, job_id: str, operation: Callable[[], None]) -> Job:
        self.repository.transition(job_id, JobState.RUNNING)
        try:
            operation()
        except Exception as error:
            return self.repository.transition(job_id, JobState.FAILED, str(error))
        return self.repository.transition(job_id, JobState.SUCCEEDED)

    def submit(self, job_type: str, operation: Callable[[], None], project_id: str | None = None) -> Job:
        job = self.enqueue(job_type, project_id)
        Thread(target=self.run_inline, args=(job.id, operation), daemon=True).start()
        return job
