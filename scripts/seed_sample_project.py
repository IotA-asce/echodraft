from echodraft_domain import ProjectCreate

from echodraft_api.config import AppSettings
from echodraft_api.container import build_container


def main() -> None:
    container = build_container(AppSettings.from_environment())
    project_id = "proj_seed_sample"
    artifact_path = container.artifacts.create_project_layout(project_id)
    project = container.projects.create(
        ProjectCreate(title="Foundation Sample", author="echodraft", rightsStatus="declared"),
        str(artifact_path),
        project_id,
    )
    job = container.jobs.enqueue("seed.completed", project.id)
    container.jobs.run_inline(job.id, lambda: None)
    print(f"Created {project.id} at {project.artifact_path}")


if __name__ == "__main__":
    main()
