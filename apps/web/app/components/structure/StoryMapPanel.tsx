import { useMemo, useState, type ChangeEvent } from "react";
import type {
  Chapter,
  Character,
  Direction,
  Issue,
  Job,
  ProductionStatus,
  RenderQueueItem,
  Scene,
  Segment,
  SegmentDirection,
  SegmentRenderComparison,
  SoundAsset,
  SoundCue,
  StructureParserWarning,
  StructureQuality,
  TtsProvider,
  VoiceProfile,
} from "../../api";
import { uiCopy } from "../../lib/copy";
import { jobProgressMessage, jobProgressPercent } from "../../lib/format";
import { ConfirmAction } from "../common/ConfirmAction";
import { EmptyState } from "../common/EmptyState";
import { ChapterAudioPlayer } from "../production/ChapterAudioPlayer";
import { RenderQueuePanel } from "../production/RenderQueuePanel";
import { SoundDesignPanel } from "../sound/SoundDesignPanel";
import { ChapterList } from "./ChapterList";
import { SceneList } from "./SceneList";
import { SegmentList } from "./SegmentList";
import { StructureWarnings } from "./StructureWarnings";

export function StoryMapPanel({
  chapters,
  scenes,
  segments,
  selectedChapter,
  editing,
  draft,
  voices,
  characters,
  directions,
  supportedDirection,
  warnings,
  issues,
  quality,
  structureJob,
  status,
  job,
  provider,
  renderQueue,
  renderCompare,
  soundAssets,
  soundCues,
  selectedSoundAssetId,
  currentSceneId,
  soundAssetType,
  soundCueType,
  soundRenderMode,
  soundGain,
  busy,
  onGoManuscript,
  onInferDirections,
  onOpenChapter,
  onOpenScene,
  onStartEdit,
  onDraftChange,
  onCancelEdit,
  onSaveEdit,
  onToggleLock,
  onSplit,
  onMerge,
  onInspect,
  onOverride,
  onSaveDirection,
  onApplyIssue,
  onRejectMerge,
  onDismissIssue,
  onProduce,
  onAssetType,
  onAssetSelect,
  onCueType,
  onRenderMode,
  onGain,
  onSoundFile,
  onAddCue,
  onAssemble,
}: {
  chapters: Chapter[];
  scenes: Scene[];
  segments: Segment[];
  selectedChapter: Chapter | null;
  editing: Segment | null;
  draft: string;
  voices: VoiceProfile[];
  characters: Character[];
  directions: SegmentDirection[];
  supportedDirection?: string[] | null;
  warnings: StructureParserWarning[];
  issues: Issue[];
  quality: StructureQuality | null;
  structureJob: Job | null;
  status: ProductionStatus | null;
  job: Job | null;
  provider?: TtsProvider;
  renderQueue: RenderQueueItem[];
  renderCompare: SegmentRenderComparison | null;
  soundAssets: SoundAsset[];
  soundCues: SoundCue[];
  selectedSoundAssetId: string;
  currentSceneId: string | null;
  soundAssetType: "ambience" | "music" | "sfx";
  soundCueType: "ambience" | "music" | "sfx";
  soundRenderMode: "light" | "dramatized" | "all";
  soundGain: number;
  busy: boolean;
  onGoManuscript: () => void;
  onInferDirections: () => void;
  onOpenChapter: (chapter: Chapter) => void;
  onOpenScene: (scene: Scene) => void;
  onStartEdit: (segment: Segment) => void;
  onDraftChange: (value: string) => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onToggleLock: (segment: Segment) => void;
  onSplit: (segment: Segment) => void;
  onMerge: (segment: Segment, nextSegment: Segment) => void;
  onInspect: (segmentId: string) => void;
  onOverride: (segmentId: string, voiceId: string) => void;
  onSaveDirection: (segmentId: string, direction: Direction) => Promise<void>;
  onApplyIssue: (issue: Issue, targetCharacterId?: string | null) => Promise<void>;
  onRejectMerge: (issue: Issue, targetCharacterId: string) => Promise<void>;
  onDismissIssue: (issue: Issue) => Promise<void>;
  onProduce: (force?: boolean) => void;
  onAssetType: (value: "ambience" | "music" | "sfx") => void;
  onAssetSelect: (value: string) => void;
  onCueType: (value: "ambience" | "music" | "sfx") => void;
  onRenderMode: (value: "light" | "dramatized" | "all") => void;
  onGain: (value: number) => void;
  onSoundFile: (event: ChangeEvent<HTMLInputElement>) => void;
  onAddCue: () => Promise<void>;
  onAssemble: (mode: "clean" | "light" | "dramatized") => Promise<void>;
}) {
  const [filter, setFilter] = useState<"all" | "needs_review" | "unresolved_dialogue" | "low_confidence" | "possible_scene" | "long_segment" | "mixed">("all");
  const possibleSceneIds = useMemo(
    () => new Set(warnings.filter((item) => item.evidence.code === "scene.possible_break_detected").map((item) => item.scopeId)),
    [warnings],
  );
  const filteredSegments = useMemo(
    () =>
      segments.filter((segment) => {
        const evidence = segment.parserEvidence ?? {};
        const productionType = String(evidence.productionType ?? segment.segmentType ?? "");
        const warningCodes = Array.isArray(evidence.warningCodes) ? evidence.warningCodes.map(String) : [];
        if (filter === "needs_review") return segment.status !== "ready";
        if (filter === "unresolved_dialogue") return segment.segmentType === "dialogue" && !segment.speakerCandidate;
        if (filter === "low_confidence") return segment.segmentType === "dialogue" && Number(segment.speakerConfidence ?? 0) < 0.8;
        if (filter === "possible_scene") return possibleSceneIds.has(segment.sceneId);
        if (filter === "long_segment") return segment.textContent.length > 900;
        if (filter === "mixed") return productionType.includes("mixed") || warningCodes.includes("segment.mixed_dialogue_and_narration");
        return true;
      }),
    [filter, possibleSceneIds, segments],
  );
  const filterOptions: Array<{ id: typeof filter; label: string; count?: number }> = [
    { id: "all", label: "All", count: segments.length },
    { id: "needs_review", label: "Needs review", count: segments.filter((item) => item.status !== "ready").length },
    { id: "unresolved_dialogue", label: "Unresolved dialogue", count: quality?.unresolvedDialogueCount },
    { id: "low_confidence", label: "Low-confidence speaker", count: segments.filter((item) => item.segmentType === "dialogue" && Number(item.speakerConfidence ?? 0) < 0.8).length },
    { id: "possible_scene", label: "Possible scene break", count: quality?.possibleSceneBreakCount },
    { id: "long_segment", label: "Long segment", count: quality?.longSegmentCount },
    { id: "mixed", label: "Mixed", count: quality?.mixedSegmentWarningCount },
  ];
  const structureJobRunning = Boolean(structureJob && ["queued", "running"].includes(structureJob.status));

  if (!chapters.length) {
    return (
      <section className="structure-view story-map-panel" aria-labelledby="story-map-title">
        <div>
          <p className="eyebrow">03 / Structure & Cast Draft</p>
          <h2 id="story-map-title">Story Map</h2>
          <p className="lede">Edit chapters, scenes, and segment-level performance direction while preserving renderable line history.</p>
        </div>
        <StructureJobProgress job={structureJob} />
        <EmptyState title="No story map yet." description="Import a manuscript first, then extract chapters, scenes, and lines." onAction={onGoManuscript} actionLabel="Go to manuscript" />
      </section>
    );
  }

  return (
    <section className="structure-view story-map-panel" aria-labelledby="story-map-title">
      <div>
        <p className="eyebrow">03 / Structure & Cast Draft</p>
        <h2 id="story-map-title">Story Map</h2>
        <p className="lede">Edit chapters, scenes, and segment-level performance direction while preserving renderable line history.</p>
        <button type="button" className="small-button direction-infer" disabled={busy} onClick={onInferDirections}>
          Infer directions
        </button>
      </div>
      <StructureJobProgress job={structureJob} />
      <div className="structure-quality" aria-label="Structure quality summary">
        <article><b>Chapters</b><strong>{quality?.chapterCount ?? chapters.length}</strong></article>
        <article><b>Scenes</b><strong>{quality?.sceneCount ?? scenes.length}</strong></article>
        <article><b>Segments</b><strong>{quality?.segmentCount ?? segments.length}</strong></article>
        <article><b>Dialogue</b><strong>{quality?.dialogueSegmentCount ?? segments.filter((item) => item.segmentType === "dialogue").length}</strong></article>
        <article><b>Attribution</b><strong>{`${quality?.dialogueAttributionCoverage ?? 100}%`}</strong></article>
        <article><b>Unresolved</b><strong>{quality?.unresolvedDialogueCount ?? 0}</strong></article>
        <article><b>Cast</b><strong>{quality?.castCandidateCount ?? 0}</strong></article>
        <article><b>Duplicates</b><strong>{quality?.possibleDuplicateCastCount ?? 0}</strong></article>
        <article><b>Offset issues</b><strong>{quality?.offsetValidationFailureCount ?? 0}</strong></article>
        <article><b>Unclosed quotes</b><strong>{quality?.quoteUnclosedCount ?? 0}</strong></article>
        <article><b>Warnings</b><strong>{quality?.warningsNeedingReviewCount ?? warnings.length}</strong></article>
        <article><b>LLM</b><strong>{structureJobRunning ? "running" : quality?.llmRefinementUsed ? `${quality.llmAcceptedBatchCount}/${quality.llmAcceptedBatchCount + quality.llmRejectedBatchCount}` : "local off"}</strong></article>
      </div>
      <div className="structure-filters" aria-label="Segment review filters">
        {filterOptions.map((item) => (
          <button key={item.id} type="button" className={filter === item.id ? "active" : ""} onClick={() => setFilter(item.id)}>
            {item.label}
            <span>{item.count ?? 0}</span>
          </button>
        ))}
      </div>
      <StructureWarnings
        warnings={warnings}
        issues={issues}
        characters={characters}
        busy={busy}
        onApplyIssue={onApplyIssue}
        onRejectMerge={onRejectMerge}
        onDismissIssue={onDismissIssue}
      />
      <div className="structure-columns">
        <ChapterList chapters={chapters} selectedChapterId={selectedChapter?.id} onOpen={onOpenChapter} />
        <SceneList scenes={scenes} onOpen={onOpenScene} />
        <SegmentList
          segments={filteredSegments}
          voices={voices}
          editing={editing}
          draft={draft}
          directions={directions}
          supportedDirection={supportedDirection}
          busy={busy}
          onStartEdit={onStartEdit}
          onDraftChange={onDraftChange}
          onCancelEdit={onCancelEdit}
          onSaveEdit={onSaveEdit}
          onToggleLock={onToggleLock}
          onSplit={onSplit}
          onMerge={onMerge}
          onInspect={onInspect}
          onOverride={onOverride}
          onSaveDirection={onSaveDirection}
        />
      </div>
      {selectedChapter ? (
        <>
          <div className="production-bar">
            <div>
              <strong>{status?.reason || `${status?.currentSegments ?? 0}/${status?.totalSegments ?? 0} segments current`}</strong>
              <small>05 / Chapter Production uses segment override, approved character voice, then narrator fallback.</small>
            </div>
            <span>
              <button type="button" disabled={busy || !status?.ready || job?.status === "running"} onClick={() => onProduce(false)}>
                {uiCopy.produceChapterAudio}
              </button>
              <ConfirmAction
                label={uiCopy.rebuildAllAudio}
                confirmLabel="Rebuild all"
                message="This creates fresh segment audio for the whole selected chapter. Existing render history remains available."
                className="secondary"
                disabled={busy || !status?.ready}
                onConfirm={() => onProduce(true)}
              />
            </span>
          </div>
          <ChapterAudioPlayer chapter={selectedChapter} activeRender={status?.activeRender} job={job} provider={provider} />
          <RenderQueuePanel items={renderQueue} comparison={renderCompare} />
          <SoundDesignPanel
            assets={soundAssets}
            cues={soundCues}
            selectedAssetId={selectedSoundAssetId}
            currentSceneId={currentSceneId}
            assetType={soundAssetType}
            cueType={soundCueType}
            renderMode={soundRenderMode}
            gain={soundGain}
            busy={busy}
            onAssetType={onAssetType}
            onAssetSelect={onAssetSelect}
            onCueType={onCueType}
            onRenderMode={onRenderMode}
            onGain={onGain}
            onFile={onSoundFile}
            onAddCue={onAddCue}
            onAssemble={onAssemble}
          />
        </>
      ) : null}
    </section>
  );
}

function StructureJobProgress({ job }: { job: Job | null }) {
  if (!job || !["queued", "running"].includes(job.status)) return null;
  const percent = jobProgressPercent(job);
  const current = typeof job.progress.current === "number" ? job.progress.current : null;
  const total = typeof job.progress.total === "number" ? job.progress.total : null;
  const phase = typeof job.progress.phase === "string" ? job.progress.phase.replaceAll("_", " ") : "queued";
  return (
    <div className="chapter-progress structure-job-progress" aria-live="polite">
      <div className="chapter-progress-row">
        <span>{jobProgressMessage(job, "Structure & Cast Draft is running")}</span>
        <span>{percent === null ? job.status : `${percent}%`}</span>
      </div>
      <progress aria-label="Structure and cast draft progress" className="chapter-progress-bar" value={percent ?? undefined} max={percent === null ? undefined : 100} />
      <p className="chapter-progress-detail">
        {current !== null && total ? `${phase} · ${current}/${total}` : phase}. Keep this project open while Echodraft works locally.
      </p>
    </div>
  );
}
