import type { ChangeEvent } from "react";
import type {
  Chapter,
  Direction,
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
  TtsProvider,
  VoiceProfile,
} from "../../api";
import { uiCopy } from "../../lib/copy";
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
  directions,
  warnings,
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
  directions: SegmentDirection[];
  warnings: StructureParserWarning[];
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
  if (!chapters.length) {
    return <EmptyState title="No story map yet." description="Import a manuscript first, then extract chapters, scenes, and lines." onAction={onGoManuscript} actionLabel="Go to manuscript" />;
  }

  return (
    <section className="structure-view story-map-panel">
      <div>
        <p className="eyebrow">03 / Structure & Cast Draft</p>
        <h2>Story Map</h2>
        <p className="lede">Edit chapters, scenes, and segment-level performance direction while preserving renderable line history.</p>
        <button type="button" className="small-button direction-infer" disabled={busy} onClick={onInferDirections}>
          Infer directions
        </button>
      </div>
      <StructureWarnings warnings={warnings} />
      <div className="structure-columns">
        <ChapterList chapters={chapters} selectedChapterId={selectedChapter?.id} onOpen={onOpenChapter} />
        <SceneList scenes={scenes} onOpen={onOpenScene} />
        <SegmentList
          segments={segments}
          voices={voices}
          editing={editing}
          draft={draft}
          directions={directions}
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
