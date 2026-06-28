import type { ReactNode } from "react";
import type { WorkflowStep, WorkflowStepId } from "../../lib/workflow";
import { WorkflowSidebar } from "./WorkflowSidebar";

export function StudioShell({
  steps,
  activeStep,
  onStepChange,
  children,
}: {
  steps: WorkflowStep[];
  activeStep: WorkflowStepId;
  onStepChange: (step: WorkflowStepId) => void;
  children: ReactNode;
}) {
  return (
    <div className="studio-shell-grid">
      <WorkflowSidebar steps={steps} activeStep={activeStep} onStepChange={onStepChange} />
      <main className="studio-active-panel">{children}</main>
    </div>
  );
}
