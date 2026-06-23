import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    database_url: str
    artifact_root: Path

    @classmethod
    def from_environment(cls) -> "AppSettings":
        return cls(
            database_url=os.getenv("ECHODRAFT_DATABASE_URL", "sqlite:///./.echodraft/echodraft.db"),
            artifact_root=Path(os.getenv("ECHODRAFT_ARTIFACT_ROOT", ".echodraft/projects")).resolve(),
        )
