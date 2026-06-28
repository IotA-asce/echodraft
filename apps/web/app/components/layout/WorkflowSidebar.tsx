import type { WorkflowStep, WorkflowStepId } from "../../lib/workflow";

const statusLabels: Record<WorkflowStep["status"], string> = {
  blocked: "Blocked",
  available: "Available",
  in_progress: "Working",
  needs_attention: "Needs attention",
  complete: "Complete",
};

export function WorkflowSidebar({
  steps,
  activeStep,
  onStepChange,
}: {
  steps: WorkflowStep[];
  activeStep: WorkflowStepId;
  onStepChange: (step: WorkflowStepId) => void;
}) {
  return (
    <nav className="workflow-sidebar" aria-label="Production workflow">
      <ol>
        {steps.map((step, index) => (
          <li key={step.id}>
            <button
              type="button"
              className={`workflow-step ${step.status}`}
              aria-current={activeStep === step.id ? "step" : undefined}
              onClick={() => onStepChange(step.id)}
            >
              <span className="workflow-step-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="workflow-step-copy">
                <strong>{step.label}</strong>
                <small>{step.blockedReason ?? step.description}</small>
              </span>
              <span className={`workflow-step-status ${step.status}`}>
                {statusLabels[step.status]}
                {step.issueCount ? ` · ${step.issueCount}` : ""}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
