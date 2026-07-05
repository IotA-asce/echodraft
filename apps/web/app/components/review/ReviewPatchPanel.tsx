import type { FormEvent } from "react";
import type { Chapter, ChapterApproval, ChapterReviewTimeline, Comment, Issue, ReadinessReport, SegmentRenderComparison, SegmentReviewInspector, TtsProvider } from "../../api";
import { EmptyState } from "../common/EmptyState";
import { ReadinessReportPanel } from "./ReadinessReportPanel";
import { SegmentInspectorPanel } from "./SegmentInspectorPanel";
import { ChapterTranscriptReview } from "./ChapterTranscriptReview";
import { IssueCard } from "./IssueCard";
import { IssueInspector } from "./IssueInspector";

export function ReviewPatchPanel({
  selectedChapter,
  readiness,
  approval,
  provider,
  busy,
  inspector,
  timeline,
  comparison,
  issues,
  activeIssue,
  comments,
  onGoProduce,
  onRunReadiness,
  onApproveChapter,
  onSetReadinessIssue,
  onInspect,
  onOpenIssue,
  onPatch,
  onResolveIssue,
  onComment,
}: {
  selectedChapter: Chapter | null;
  readiness: ReadinessReport | null;
  approval: ChapterApproval | null;
  provider?: TtsProvider;
  busy: boolean;
  inspector: SegmentReviewInspector | null;
  timeline: ChapterReviewTimeline | null;
  comparison: SegmentRenderComparison | null;
  issues: Issue[];
  activeIssue: Issue | null;
  comments: Comment[];
  onGoProduce: () => void;
  onRunReadiness: () => Promise<void>;
  onApproveChapter: () => Promise<void>;
  onSetReadinessIssue: (issueId: string, status: "resolved" | "ignored" | "locked") => Promise<void>;
  onInspect: (segmentId: string) => void;
  onOpenIssue: (issue: Issue) => void;
  onPatch: (issue: Issue) => void;
  onResolveIssue: (issue: Issue) => void;
  onComment: (event: FormEvent<HTMLFormElement>) => void;
}) {
  if (!selectedChapter) {
    return <EmptyState title="Nothing to review yet." description="Produce a chapter to create audio and review items." onAction={onGoProduce} actionLabel="Go to produce" />;
  }

  const chapterIssues = issues.filter((issue) => issue.chapterId === selectedChapter.id || issue.segmentId);
  return (
    <section className="studio-section review review-patch-panel" aria-labelledby="review-patch-title">
      <div>
        <p className="eyebrow">06 / Review & patch</p>
        <h2 id="review-patch-title">Review Patch Workbench</h2>
        <p className="lede">Listen against the transcript timeline, inspect line evidence, and rebuild only the affected segment when needed.</p>
      </div>
      <div className="studio-card review-workbench-grid">
        <ReadinessReportPanel report={readiness} busy={busy} onRun={onRunReadiness} onSetIssue={onSetReadinessIssue} />
        <div className={approval?.current ? "chapter-approval current" : "chapter-approval"}>
          <div>
            <strong>{approval?.current ? "Chapter approved" : "Listen and approve"}</strong>
            <p>{approval?.current ? `Approved by ${approval.approvedBy ?? "local-user"}.` : approval?.status === "stale" ? "A newer render needs a fresh approval." : "Approval is separate from automated readiness."}</p>
          </div>
          <button type="button" className="small-button" disabled={busy || !timeline?.chapterRender} onClick={() => void onApproveChapter()}>
            Mark listened and approved
          </button>
        </div>
        <ChapterTranscriptReview timeline={timeline} inspector={inspector} issues={chapterIssues} provider={provider} onInspect={onInspect} onOpenIssue={onOpenIssue} />
        <SegmentInspectorPanel inspector={inspector} comparison={comparison} />
        <div className="issue-list">
          {chapterIssues.length ? chapterIssues.map((issue) => <IssueCard key={issue.id} issue={issue} onOpen={onOpenIssue} onPatch={onPatch} onResolve={onResolveIssue} />) : <p className="import-placeholder">No open QA issues for this chapter.</p>}
        </div>
        <IssueInspector activeIssue={activeIssue} comments={comments} onComment={onComment} />
      </div>
    </section>
  );
}
