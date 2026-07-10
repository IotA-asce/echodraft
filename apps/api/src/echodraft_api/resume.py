"""Startup resume registry for interrupted, checkpointed orchestrator jobs.

When the API process restarts, jobs left in ``RUNNING`` cannot continue in place.
Historically every such job was marked ``FAILED``. Jobs whose type appears in
``RESUME_REGISTRY`` and that recorded orchestrator checkpoints are instead
re-enqueued and re-run: the extraction stages consult the checkpoint store and the
inference cache to skip units that already completed, so resumption is cheap and
deterministic.

Each resume callable must recover its inputs solely from the persisted job row
(``project_id``/``target_id``); any other input is treated as absent and defaulted.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from echodraft_domain import Job

if TYPE_CHECKING:
    from .container import AppContainer

ResumeCallable = Callable[["AppContainer", Job], None]

# Structure extraction runs entirely from the project's latest canonical source, so the
# only input that cannot be recovered from the job row is the segment-size hint. We fall
# back to the API default (matching ``StructureRequest.max_segment_chars``).
DEFAULT_MAX_SEGMENT_CHARS = 600


def _resume_structure_extract(container: "AppContainer", job: Job) -> None:
    from .structure import StructureService

    if not job.project_id:
        raise ValueError("structure.extract resume requires a project id on the job row.")
    StructureService(container).extract(
        job.project_id, DEFAULT_MAX_SEGMENT_CHARS, job_id=job.id
    )


RESUME_REGISTRY: dict[str, ResumeCallable] = {
    "structure.extract": _resume_structure_extract,
}
