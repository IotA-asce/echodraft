import type { Project } from "../../api";
import { EmptyState } from "../common/EmptyState";

export function ProjectLibraryPanel({
  projects,
  selectedProjectId,
  onOpen,
}: {
  projects: Project[];
  selectedProjectId: string | null;
  onOpen: (projectId: string) => void;
}) {
  return (
    <section className="project-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Project library</p>
          <h2>Your local productions</h2>
        </div>
        <span>{projects.length} projects</span>
      </div>
      <ul className="project-list">
        {projects.map((item) => (
          <li key={item.id} className={item.id === selectedProjectId ? "selected" : undefined}>
            <div className="project-index">{item.title.slice(0, 1).toUpperCase()}</div>
            <div>
              <strong>{item.title}</strong>
              <p>
                {item.author || "Independent production"} · {item.status}
              </p>
            </div>
            <button className="select-project" type="button" onClick={() => onOpen(item.id)}>
              Open
            </button>
          </li>
        ))}
      </ul>
      {!projects.length ? <EmptyState title="No local productions yet." description="Create a project to start a rights-cleared audiobook draft." /> : null}
    </section>
  );
}
