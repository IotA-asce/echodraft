import shutil
from pathlib import Path


class ArtifactStore:
    directories = ("source", "structure", "audio", "exports", "logs", "manifests")

    def __init__(self, root: Path) -> None:
        self.root = root

    def create_project_layout(self, project_id: str) -> Path:
        project_root = self.root / project_id
        for name in self.directories:
            (project_root / name).mkdir(parents=True, exist_ok=True)
        return project_root

    def remove_project_layout(self, project_id: str) -> None:
        shutil.rmtree(self.root / project_id, ignore_errors=True)
