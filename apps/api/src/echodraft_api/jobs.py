from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from echodraft_db import JobRepository
from echodraft_domain import Job, JobState


class InProcessJobRunner:
    def __init__(self, repository: JobRepository, max_workers: int = 2) -> None:
        self.repository = repository
        # A single bounded pool backs every submission site so concurrent jobs never
        # exceed max_workers OS threads; jobs beyond the limit stay queued (JobState.QUEUED)
        # until a worker is free and run_inline transitions them to RUNNING.
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="echodraft-job"
        )

    def enqueue(
        self, job_type: str, project_id: str | None = None, target_id: str | None = None
    ) -> Job:
        return self.repository.create(job_type, project_id, target_id)

    def run_inline(self, job_id: str, operation: Callable[[], None]) -> Job:
        self.repository.transition(job_id, JobState.RUNNING)
        try:
            operation()
        except Exception as error:
            return self.repository.transition(
                job_id, JobState.FAILED, self._recovery_message(error)
            )
        return self.repository.transition(job_id, JobState.SUCCEEDED)

    def submit(
        self, job_type: str, operation: Callable[[], None], project_id: str | None = None
    ) -> Job:
        job = self.enqueue(job_type, project_id)
        self._executor.submit(self.run_inline, job.id, operation)
        return job

    def submit_with_job(
        self,
        job_type: str,
        operation: Callable[[str], None],
        project_id: str | None = None,
        target_id: str | None = None,
    ) -> Job:
        job = self.enqueue(job_type, project_id, target_id)
        self._executor.submit(self.run_inline, job.id, lambda: operation(job.id))
        return job

    def resume(self, job_id: str, operation: Callable[[], None]) -> None:
        """Re-run a job row that already exists and is back in QUEUED.

        Used by startup resume to re-execute interrupted, checkpointed jobs without
        creating a new job row (preserving the job id and its event/checkpoint history).
        """
        self._executor.submit(self.run_inline, job_id, operation)

    @staticmethod
    def _recovery_message(error: Exception) -> str:
        message = str(error)
        if isinstance(error, (ValueError, KeyError)):
            return f"validation: {message}. Review the request and retry."
        if isinstance(error, OSError):
            return f"filesystem: {message}. Check local storage permissions and retry."
        return f"unexpected: {message}. Capture a debug bundle and retry the workflow."
