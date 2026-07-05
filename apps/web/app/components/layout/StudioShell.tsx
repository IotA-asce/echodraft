import type { ReactNode } from "react";
import type { WorkflowAction, WorkflowStep, WorkflowStepId } from "../../lib/workflow";
import { WorkflowSidebar } from "./WorkflowSidebar";

export function StudioShell({
  steps,
  activeStep,
  onStepChange,
  nextAction,
  onAction,
  children,
}: {
  steps: WorkflowStep[];
  activeStep: WorkflowStepId;
  onStepChange: (step: WorkflowStepId) => void;
  nextAction?: WorkflowAction | null;
  onAction?: (action: WorkflowAction) => void;
  children: ReactNode;
}) {
  return (
    <div className="studio-shell-grid">
      <WorkflowSidebar steps={steps} activeStep={activeStep} onStepChange={onStepChange} />
      <main className="studio-active-panel">
        {nextAction ? (
          <aside className="next-action-card" aria-label="Next best action">
            <div>
              <p className="eyebrow">Next best action</p>
              <strong>{nextAction.title}</strong>
              <span>{nextAction.description}</span>
            </div>
            <button type="button" className="small-button" onClick={() => onAction?.(nextAction)}>
              Go
            </button>
          </aside>
        ) : null}
        {children}
      </main>
    </div>
  );
}
