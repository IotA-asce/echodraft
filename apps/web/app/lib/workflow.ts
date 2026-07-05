import type { Chapter, ChapterApproval, ChapterReviewTimeline, ExportEstimate, ExportPackage, Issue, Job, ProductionSettings, ProductionStatus, Project, ReadinessReport, SourceDocument, StructureParserWarning, TtsSettings, VoiceProfile } from "../api";

export type WorkflowStepId =
  | "project"
  | "voice-engine"
  | "manuscript"
  | "structure"
  | "voices-cast"
  | "produce"
  | "review-patch"
  | "export";

export type WorkflowStepStatus = "blocked" | "available" | "in_progress" | "needs_attention" | "complete";

export type WorkflowStep = {
  id: WorkflowStepId;
  label: string;
  status: WorkflowStepStatus;
  description: string;
  blockedReason?: string;
  issueCount?: number;
};

export type WorkflowAction = {
  id: string;
  title: string;
  description: string;
  step: WorkflowStepId;
  priority: number;
  issueId?: string | null;
  segmentId?: string | null;
  audioStartMs?: number | null;
};

export function buildWorkflowSteps({
  project,
  tts,
  source,
  structureWarnings,
  chapters,
  voices,
  production,
  selectedChapter,
  productionStatus,
  productionJob,
  issues,
  exports,
}: {
  project: Project | null;
  tts: TtsSettings | null;
  source: SourceDocument | null;
  structureWarnings: StructureParserWarning[];
  chapters: Chapter[];
  voices: VoiceProfile[];
  production: ProductionSettings | null;
  selectedChapter: Chapter | null;
  productionStatus: ProductionStatus | null;
  productionJob: Job | null;
  issues: Issue[];
  exports: ExportPackage[];
}): WorkflowStep[] {
  const projectReady = Boolean(project);
  const sourceReady = Boolean(source && ["ready", "available", "imported"].includes(source.status));
  const narratorReady = Boolean(production?.narratorVoiceProfileId);
  const chapterIssues = selectedChapter
    ? issues.filter((issue) => (issue.chapterId === selectedChapter.id || issue.segmentId) && issue.status !== "resolved")
    : [];
  const productionRunning = Boolean(productionJob && ["queued", "running"].includes(productionJob.status));

  return [
    {
      id: "project",
      label: "Project",
      status: projectReady ? "complete" : "available",
      description: projectReady ? `Open: ${project?.title}` : "Create or open a local production file.",
    },
    {
      id: "voice-engine",
      label: "Voice Engine",
      status: !projectReady ? "blocked" : tts?.ready ? "complete" : "available",
      description: tts?.ready ? `${tts.provider} is ready for local production.` : "Choose silent workflow audio or set up a local voice engine.",
      blockedReason: projectReady ? undefined : "Create or open a project first.",
    },
    {
      id: "manuscript",
      label: "Manuscript",
      status: !projectReady ? "blocked" : sourceReady ? "complete" : "available",
      description: sourceReady ? source?.originalFilename ?? "Manuscript imported." : "Bring in a rights-cleared working text.",
      blockedReason: projectReady ? undefined : "Create or open a project first.",
    },
    {
      id: "structure",
      label: "Structure",
      status: !sourceReady ? "blocked" : chapters.length ? "complete" : structureWarnings.length ? "needs_attention" : "available",
      description: chapters.length ? `${chapters.length} chapters in the story map.` : "Extract chapters, scenes, and line-level passages.",
      blockedReason: sourceReady ? undefined : "Import a manuscript before extracting structure.",
      issueCount: structureWarnings.length || undefined,
    },
    {
      id: "voices-cast",
      label: "Voices & Cast",
      status: !projectReady ? "blocked" : narratorReady ? "complete" : voices.length ? "needs_attention" : "available",
      description: narratorReady ? "Narrator voice selected." : "Create voices, review cast, and choose a narrator.",
      blockedReason: projectReady ? undefined : "Create or open a project first.",
    },
    {
      id: "produce",
      label: "Produce",
      status: !selectedChapter
        ? "blocked"
        : productionRunning
          ? "in_progress"
          : productionStatus?.activeRender
            ? "complete"
            : productionStatus?.ready
              ? "available"
              : "blocked",
      description: productionStatus?.activeRender ? "Chapter has an active audio version." : "Produce chapter audio locally.",
      blockedReason: selectedChapter ? productionStatus?.reason ?? undefined : "Choose a chapter before producing audio.",
    },
    {
      id: "review-patch",
      label: "Review & Patch",
      status: !productionStatus?.activeRender ? "blocked" : chapterIssues.length ? "needs_attention" : "complete",
      description: productionStatus?.activeRender ? "Review audio, notes, and line-level fixes." : "Produce a chapter before review.",
      blockedReason: productionStatus?.activeRender ? undefined : "Produce a chapter before review.",
      issueCount: chapterIssues.length || undefined,
    },
    {
      id: "export",
      label: "Export",
      status: !chapters.length ? "blocked" : exports.length ? "complete" : "available",
      description: exports.length ? `${exports.length} export packages created.` : "Package selected chapters as WAV or MP3 ZIP files.",
      blockedReason: chapters.length ? undefined : "Extract structure before exporting chapters.",
    },
  ];
}

export function buildWorkflowActions({
  steps,
  readiness,
  exportEstimate,
  selectedChapter,
  approval,
  timeline,
}: {
  steps: WorkflowStep[];
  readiness: ReadinessReport | null;
  exportEstimate: ExportEstimate | null;
  selectedChapter: Chapter | null;
  approval: ChapterApproval | null;
  timeline: ChapterReviewTimeline | null;
}): WorkflowAction[] {
  const actions: WorkflowAction[] = [];
  const blockedStep = steps.find((step) => step.status === "blocked");
  const attentionStep = steps.find((step) => step.status === "needs_attention" || step.status === "available");
  if (blockedStep) {
    actions.push({
      id: `step-${blockedStep.id}`,
      title: `Continue with ${blockedStep.label}`,
      description: blockedStep.blockedReason ?? blockedStep.description,
      step: blockedStep.id,
      priority: 80,
    });
  } else if (attentionStep) {
    actions.push({
      id: `step-${attentionStep.id}`,
      title: `Continue with ${attentionStep.label}`,
      description: attentionStep.description,
      step: attentionStep.id,
      priority: attentionStep.status === "needs_attention" ? 85 : 60,
    });
  }
  for (const check of readiness?.checks ?? []) {
    if (check.status === "passed" || (check.resolutionStatus && check.resolutionStatus !== "open")) continue;
    actions.push({
      id: `readiness-${check.id}`,
      title: check.title,
      description: check.description,
      step: check.scope === "export-blocker" ? "export" : "review-patch",
      priority: check.severity === "blocking" ? 100 : 75,
      issueId: check.issueId,
      segmentId: typeof check.metadata.segmentId === "string" ? check.metadata.segmentId : null,
    });
  }
  for (const blocker of exportEstimate?.blockers ?? []) {
    actions.push({
      id: `export-${blocker.code}-${blocker.issueId ?? blocker.chapterId ?? "global"}`,
      title: blocker.message,
      description: `Export blocker: ${blocker.scope}`,
      step: "export",
      priority: blocker.severity === "blocking" ? 95 : 70,
      issueId: blocker.issueId,
    });
  }
  const firstMarker = timeline?.issueMarkers[0];
  if (firstMarker) {
    actions.push({
      id: `audio-${firstMarker.id}`,
      title: `Review audio issue: ${firstMarker.title}`,
      description: `Jump to ${Math.round(firstMarker.startMs / 1000)}s in ${selectedChapter?.title ?? "the selected chapter"}.`,
      step: "review-patch",
      priority: firstMarker.severity === "blocking" ? 98 : 78,
      issueId: firstMarker.issueId,
      segmentId: firstMarker.segmentId,
      audioStartMs: firstMarker.startMs,
    });
  }
  if (selectedChapter && approval && !approval.current) {
    actions.push({
      id: `approval-${selectedChapter.id}`,
      title: "Listen and approve this chapter",
      description: approval.status === "stale" ? "A newer render needs a fresh approval." : "Approval is separate from automated readiness.",
      step: "review-patch",
      priority: 72,
    });
  }
  return actions.sort((a, b) => b.priority - a.priority);
}
