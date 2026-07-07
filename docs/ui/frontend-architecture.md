# Frontend Architecture v2

See also: [design-system.md](design-system.md), [target-architecture.md](../architecture/target-architecture.md), [extraction-pipeline-v2.md](../architecture/extraction-pipeline-v2.md), [product-vision-v2.md](../product/product-vision-v2.md), [cross-platform-strategy.md](../platform/cross-platform-strategy.md), [architecture.md](../architecture/architecture.md)

## Purpose

Echodraft's web client is a single 553-line client component (`apps/web/app/project-dashboard.tsx`) driving eight string-switched "steps" behind one URL. It freezes the browser tab on real books ("page unresponsive"), looks and feels like a prototype, and cannot be embedded in a desktop/mobile shell as-is because it has no real navigation surface to host. This document is the target frontend architecture: real routes, a server-cache data layer, a push-based progress channel, virtualized lists, and a component structure that a future Tauri/Capacitor shell can embed unmodified.

This is a **re-architecture**, not a rewrite-from-scratch mandate — [Incremental Migration Plan](#incremental-migration-plan) below keeps the app shippable at every step.

## Goals

Hard performance budgets (measured, not aspirational — see [Performance Verification](#performance-verification)):

| Budget | Target | Why |
|---|---|---|
| Main-thread block | never exceed 50ms per task | Chrome's own "unresponsive" heuristic fires around ~5s of cumulative blocking; 50ms is the `longtask` threshold and the number below which input stays perceptibly instant |
| Scroll framerate | 60fps scrolling a 7,000-segment book | 6,995 segments is the real measured book from a production run (§ Root-Cause Analysis) — the design target is the actual worst case, not a hypothetical |
| Interaction latency | under 100ms from keypress/click to visible feedback | RAIL model's "response" budget |
| Initial route load | under 2s to interactive on a cold cache | a route is a screen now, not a step; it must feel like opening a native app panel |

Architectural goals:

1. **No God component.** No component owns state unrelated to what it renders. State either lives in the server cache (TanStack Query), in the URL (route params/search params), or in a narrowly-scoped local/ephemeral store.
2. **Mutation → targeted invalidation**, never "refresh everything." Every mutation in the app today ends in a hand-written `refreshX()` that re-fetches 3-6 endpoints; v2 replaces this with cache-key-scoped invalidation.
3. **Push over poll.** Long-running jobs (structure extraction, chapter production, model install) report progress over a real event stream, with polling only as a degraded-mode fallback.
4. **Virtualize anything that scales with the book.** Segments, transcript lines, characters, and warnings are all O(book length); none may render as one DOM node per item once the list exceeds a couple hundred rows.
5. **Route-addressable everything.** Every screen a user can reach must be a deep-linkable URL, so it can be bookmarked, reloaded, and — later — mapped 1:1 onto native shell navigation.
6. **Shell-ready.** The SPA must run unmodified inside a desktop (Tauri) or mobile (Capacitor) WebView pointed at a locally-bound engine, per [cross-platform-strategy.md](../platform/cross-platform-strategy.md).

## Non-goals

- This document does not specify the **visual** design language (tokens, palette, type scale, motion) — that is [design-system.md](design-system.md). This doc treats design-system components as an opaque primitives layer it consumes.
- This document does not specify the **event/job orchestration backend** (DAG, resumability, SSE transport implementation) — that is [target-architecture.md](../architecture/target-architecture.md). This doc specifies the frontend's *consumption* contract for that stream and falls back gracefully if it isn't there yet.
- This document does not redesign the **extraction pipeline** itself (why it takes 5-6 hours, LLM-first vs deterministic-first) — that is [extraction-pipeline-v2.md](../architecture/extraction-pipeline-v2.md). This doc assumes flag volume drops substantially and designs the review UI so it doesn't matter if it doesn't drop all the way to zero.
- No native-shell packaging detail (installers, code signing, model download managers) — [cross-platform-strategy.md](../platform/cross-platform-strategy.md).
- No server-side rendering push. The app stays a client-rendered SPA (see [Desktop/Mobile Shell Readiness](#desktopmobile-shell-readiness) for why).

## Root-Cause Analysis: Why the Current UI Freezes

The freeze is not one bug — it's four independent problems that multiply:

**1. One God component holds all state.** `ProjectDashboard` (`apps/web/app/project-dashboard.tsx:41-58`) declares roughly 45 `useState` hooks — projects, source, pages, cleaning issues, structure warnings, chapters, scenes, segments, editing draft, five different job objects, TTS settings, voices, production settings, status, issues, comments, exports, characters, speaker attributions, segment directions, render queue, render comparison, segment inspector, review timeline, chapter approval, pronunciations, sound assets/cues, readiness, notices, busy flags, and a dozen form fields — in a single function component. Any `setState` call here re-renders the entire tree below it, because React has no way to know that, say, updating `exportTitle` doesn't affect `segments`.

**2. Five independent polling loops tick against that same state.** `project-dashboard.tsx` runs five recursive `setTimeout` effects — import job at 750ms (`:110-128`), structure job at 1000ms (`:129-147`), production job at **500ms** (`:148-166`), Kokoro setup at 750ms (`:167-183`), local-AI install at 900ms (`:184-205`) — plus a 250ms×80 `waitFor` busy-poll used by several mutation handlers (`:225`). Every tick calls `setJob`/`setStructureJob`/etc. on the God component's top-level state.

**3. Zero memoization anywhere in the render path.** A grep of the codebase turns up no `React.memo` usage and only 3 `useMemo` calls total (`project`, `workflowSteps`, `workflowActions` — `project-dashboard.tsx:60,66,84`). No component memoizes, no callback is wrapped in `useCallback`. Every one of the ~45 state slices changing forces a full re-render of every mounted panel and every row inside every list, because nothing in the tree is allowed to bail out.

**4. The heavy lists are unvirtualized DOM, and one is DOM-per-audio-sample.** `SegmentList` (`apps/web/app/components/structure/SegmentList.tsx`) renders one heavyweight `SegmentEditorCard` (`apps/web/app/components/structure/SegmentEditorCard.tsx`, 155 lines — toolbar, evidence JSON drawer, direction sub-form, voice select) per segment with no windowing. `ChapterTranscriptReview` and `ChapterTimeline` (`apps/web/app/components/review/ChapterTimeline.tsx`) render one `<button>` per segment for the whole chapter transcript, because the server already ships the entire chapter timeline in one JSON payload (no list endpoint paginates — confirmed in both `apps/web/app/api.ts` and the FastAPI routes). The waveform renders one DOM node per amplitude bucket plus one per issue marker, rebuilt from scratch on every poll tick. A 500-page book's structure screen is 6,995 `SegmentEditorCard` instances, not 6,995 canvas pixels.

**The multiplication:** every 500ms-1000ms, a poll tick lands → sets top-level state on the God component → with no memoization anywhere, React re-renders the entire mounted tree → which includes thousands of unvirtualized `SegmentEditorCard`/transcript-row/waveform-bucket DOM nodes being diffed and, on data change, repainted. On a 500+ page book (6,995 segments, measured job `job_3c8fbf0189cd4c8e`, 6h57m wall time) this reconciliation pass alone can exceed the 50ms `longtask` threshold by an order of magnitude, several times a second, for the entire duration of a multi-hour job — which is exactly when Chrome shows "page unresponsive." Typing a single character into one segment's editor re-renders every other segment in the same scene, because `editing`/`draft` are also top-level state (`:45`) threaded through every `SegmentEditorCard` as props.

None of these four problems is individually exotic; the fix is proportionally unglamorous — see [Incremental Migration Plan](#incremental-migration-plan) for how much of this is fixable in days, not weeks.

Two secondary contributors, out of scope for this document but worth naming: `loadProject` fires 14 concurrent `GET`s on every project switch (`project-dashboard.tsx:210`, one `Promise.allSettled` array with `getSource`, `listChapters`, `listStructureWarnings`, `getStructureQuality`, `listVoices`, `getProductionSettings`, `listIssues`, `listExports`, `listCharacters`, `listSpeakerAttributions`, `listSegmentDirections`, `listPronunciations`, `listSoundAssets`, `listProjectJobs`), and there is no code-splitting (`next/dynamic` is unused anywhere in `apps/web`), so all of it ships in one JS bundle regardless of which "step" is active.

## Information Architecture v2

### The zero-touch reframing

Today's IA is a linear 8-step wizard (`apps/web/app/lib/workflow.ts`, `buildWorkflowSteps`/`buildWorkflowActions`) because today's pipeline needs a human to babysit every stage: import → voice engine → manuscript → structure+produce → voices & cast → review & patch → export. [extraction-pipeline-v2.md](../architecture/extraction-pipeline-v2.md) and [automatic-casting-v2.md](../pipeline/casting/automatic-casting-v2.md) change that premise: extraction, cast discovery, speaker attribution, and voice assignment become automatic pipeline stages the user does not drive step-by-step — they *watch happen* and *listen to the result*, intervening only where confidence is genuinely low.

The primary screen inside a project therefore stops being "step 1 of 8" and becomes a **book overview**: a pipeline-progress rail plus a listen-first player, with a short "needs your attention" list (durable `issues` at `blocking`/`error` severity only — not `warnings`, which are lower-severity per-scope findings that the pipeline should be resolving on its own per the v2 confidence model). The old step-wizard doesn't disappear; it **demotes** from primary navigation to a set of drill-down editing routes the overview links into, plus a single "next best action" suggestion chip (the direct descendant of today's `buildWorkflowActions`).

### Route map

Real routes, real deep links, via the Next.js App Router (already the framework in `apps/web` — `next@16.2.9` — just not used for routing yet; today there is exactly one route, `apps/web/app/page.tsx`).

| Route | Screen | Primary data source | Replaces (current single-URL step) |
|---|---|---|---|
| `/projects` | Library: grid of books, create-new | paged project summaries | `ProjectLibraryPanel` + `NewProjectPanel` ("project" step) |
| `/projects/[projectId]` | **Overview** — pipeline progress + listen-first review | project summary/aggregate, pipeline phase, latest chapter render | `StudioHero` + workflow sidebar (was implicit, not a screen) |
| `/projects/[projectId]/manuscript` | Manuscript intake — upload, OCR page review, cleaning issues | source doc, source pages, cleaning issues | `ManuscriptIntakePanel` ("manuscript" step) |
| `/projects/[projectId]/structure` | Structure drill-down — chapter/scene tree, structure warnings, quality | chapters, scenes, structure warnings (paged), structure quality | `ChapterList`+`SceneList`+`StructureWarnings` slice of `StoryMapPanel` |
| `/projects/[projectId]/cast` | Cast — character bible, voice assignment, pronunciations | characters (paged), voices, speaker attributions | `VoiceBiblePanel` ("voices-cast" step) |
| `/projects/[projectId]/produce/[chapterId]` | Produce — segment list, direction editing, render queue, audio player | segments (paged/virtualized), render queue, production status | remaining slice of `StoryMapPanel` ("structure"/"produce" step) |
| `/projects/[projectId]/review/[chapterId]` | Review — waveform, transcript, inspector drawer, issue queue | windowed review timeline, issues, segment inspector | `ReviewPatchPanel` ("review-patch" step) |
| `/projects/[projectId]/export` | Export — format/metadata form, package history, blockers | exports, export estimate | `ExportPanel` ("export" step) |
| `/settings/engine` | Engine — TTS provider choice, Model Center, local AI catalog | TTS settings/providers, local AI catalog | voice-engine step + `ModelCenter` (project-scoped today; global by nature) |

All project-scoped routes nest under `/projects/[projectId]/...` (App Router route group `apps/web/app/(app)/projects/[projectId]/...`), so the project is always in the URL and reload-safe. `/settings/engine` sits outside the project tree because engine/model setup is a machine-level concern, not a per-book one — the current design incorrectly repeats it per-project.

### Per-route wireframes (text)

Wireframes reference design-system primitives (`docs/ui/design-system.md`) by anticipated name — reconcile naming once that doc lands; the structural intent (what's on screen, what's in a drawer, what's counted vs. listed) is what matters here.

**`/projects` — Library**
```
AppShell (nav: Library / Settings)
  Header            "Your books"                      [+ New book]
  Grid<Card>         cover placeholder · title · StatusPill(phase)
                      · ProgressBar(pipeline %)
  EmptyState         "No books yet" + primary CTA
```

**`/projects/[projectId]` — Overview (the new primary screen)**
```
AppShell
  Header            title / author · StatusPill(phase)
  PipelineRail      Ingest ● → Structure ● → Cast ● → Direction ○
                     → TTS ○ → Assemble ○ → QA ○   (per-phase ProgressBar)
  ListenFirstCard    latest ready chapter · waveform thumbnail · Play
                      · "N of M chapters ready"
  NeedsAttentionList top 5 blocking/error issues only · "View all →" (/review)
  NextBestAction     single suggestion chip (was buildWorkflowActions)
```
No JSON, no evidence, no per-segment detail lives here — this screen answers "is my book done yet, and does it sound right," nothing else.

**`/projects/[projectId]/manuscript`**
```
AppShell
  ImportDropzone     file picker · rights checkbox
  ImportProgress     job status (SSE-driven, see below)
  SourcePreviewCard  paged text preview
  CleaningIssueList  virtualized List<ListRow> · counts by severity in header
                      · row expands inline; "Why?" opens Drawer(evidence)
```

**`/projects/[projectId]/structure`**
```
AppShell
  Tabs               Chapters | Warnings | Quality
  Chapters tab:       Tree<ChapterList → SceneList> (lazy-expand, not
                       all-scenes-mounted)
  Warnings tab:       virtualized List, filter chips (severity/scopeType),
                       row → Drawer(evidence) on demand
  Quality tab:        StatCard grid (aggregate numbers only — this is where
                       the current 12-stat-tile quality bar belongs, not
                       stapled onto every other screen)
```

**`/projects/[projectId]/cast`**
```
AppShell
  Tabs               Characters | Cast review | Pronunciations
  Characters tab:     virtualized Grid<CharacterCard> (name, voice badge,
                       role badge) · row → Drawer(full character form:
                       aliases, traits, merge/split, voice suggestions)
  Cast review tab:    virtualized List of speaker-attribution items needing
                       review only (status=needs_review) — not the full set
  Pronunciations tab: simple List + inline add form
```

**`/projects/[projectId]/produce/[chapterId]`**
```
AppShell
  ChapterHeader       title · ChapterAudioPlayer (compact) · Produce button
  Split view:
    left  — virtualized SegmentList (row = 1-2 lines: speaker badge,
            text excerpt, status dot; click expands in place)
    right — Inspector drawer (opens on row select): direction sub-form,
            voice override, evidence, render history — never inline
  RenderQueuePanel    collapsed by default; badge shows in-flight count
  SoundCues           moved into a drawer tab here, not a permanently
                       mounted panel (see decluttering below)
```

**`/projects/[projectId]/review/[chapterId]`**
```
AppShell
  WaveformCanvas      single <canvas> (see List Virtualization section) ·
                       issue markers · playhead · scrub
  TranscriptList      virtualized, synced scroll position with waveform
                       window
  IssueDrawer         opens per-issue: comments, patch action, apply/dismiss
  ApprovalBar         "Mark listened & approved" (was buried mid-panel)
```

**`/projects/[projectId]/export`**
```
AppShell
  ChapterChecklist    which chapters to include
  MetadataForm        title/author/album/publisher/language/cover — a real
                       form (react-hook-form, see Component Architecture)
  EstimateCard        size/blocker preview, debounced on form change
  ExportHistory       List<ExportPackage> with QA scorecard badges
```

**`/settings/engine`**
```
AppShell
  ProviderPicker      mock / kokoro / piper / xtts_v2
  ProviderStatus      capability + readiness
  ModelCenter         catalog table, install/verify actions, progress via
                       the same SSE job stream as everything else
```

### Decluttering the 7-panel Structure screen

Today's `StoryMapPanel` (`apps/web/app/components/structure/StoryMapPanel.tsx`, 321 lines) mounts seven distinct sub-panels simultaneously regardless of what the user is doing: `ChapterList`, `SceneList`, `SegmentList` (+`SegmentEditorCard`), `StructureWarnings`, `ChapterAudioPlayer`, `RenderQueuePanel`, and `SoundDesignPanel`. All seven render props are threaded through the God component's ~45 states even when six of the seven aren't visible. v2 splits this along the read-vs-work seam:

- **Organize** (chapters/scenes/warnings — low-frequency, structural) → `/projects/[projectId]/structure`.
- **Work** (segment editing, direction, rendering, listening — high-frequency) → `/projects/[projectId]/produce/[chapterId]`.
- **Sound design** stops being a permanently-mounted panel and becomes a drawer tab reachable from the produce screen — it's an occasional-use feature, not a constant-presence one.

This alone cuts the components mounted on any given screen from seven to two or three, which is a direct, measurable reduction in what re-renders on every state change even before any memoization work lands.

### Progressive disclosure rules

1. **Evidence and JSON never render inline in a list row.** `parserEvidence`, `evidence`, and the current `<pre>` JSON dumps only ever appear inside an `Inspector`/`Drawer`, opened explicitly (a "Why?" affordance), and code-split via `next/dynamic(() => import(...), { ssr: false })` since nothing needs it until opened.
2. **Rows default to 1-2 lines.** Full edit affordances expand the row in place (local state, scoped to that row only — see [Row component design](#row-component-design)); full diagnostic detail opens a drawer instead of expanding the row further.
3. **Advanced/rare controls stay behind an explicit disclosure**, not top-level chrome — e.g., the "Advanced: use a custom voice adapter" and "Advanced local capability setup" sections already correctly use `<details>` today (`project-dashboard.tsx` voice-engine block); this pattern generalizes as a `Disclosure` design-system primitive everywhere, including Model Center's install logs.
4. **Collections default to counts + top-N, not full dumps.** Character grids, warning lists, and issue queues show an aggregate count and a short list with "View all N →"; the full paged/virtualized view lives on its own route or drawer, never mounted by default on the overview.

## State & Data Layer

### Server cache: TanStack Query

**Decision: adopt `@tanstack/react-query` (v5) as the server-state cache, not SWR.**

Justification:
- **Selective invalidation matches the "no refresh-everything" goal directly.** `queryClient.invalidateQueries({ queryKey: [...], exact: false })` invalidates by key *prefix*, which maps cleanly onto the normalized key families below (invalidate `["project", id, "characters"]` without touching `["project", id, "issues"]`). SWR supports similar patterns via a key-matching function, but it's a bolt-on, not the primary invalidation model.
- **First-class mutation lifecycle** (`onMutate`/`onError`/`onSettled`, automatic rollback context) is exactly the optimistic-update shape needed for segment edits, direction saves, and issue actions — see [Optimistic updates](#optimistic-updates).
- **`useInfiniteQuery` gives cursor pagination for free**, which every paginated endpoint in [API Contract Requirements](#api-contract-requirements) needs (segments, characters, issues, warnings).
- **Ecosystem locality.** `@tanstack/react-virtual` (adopted below for list virtualization) is the same vendor/scope as `@tanstack/react-query`; consistent API conventions and one devtools story reduce tooling surface, which matters for a small team maintaining a desktop-shell-bound app.
- **`refetchInterval` as a function of query state** is exactly the shape needed for the polling *fallback* in the real-time section — one mechanism serves both "poll because SSE isn't wired up yet" and "poll because SSE dropped."

Add `apps/web/app/lib/query-client.ts` exporting a singleton `QueryClient` with `staleTime` tuned per query family (structural data like chapters/characters: minutes; job status: 0, always driven by the event stream or its polling fallback), and mount `<QueryClientProvider>` once in `apps/web/app/layout.tsx`. In development, mount `@tanstack/react-query-devtools` behind `process.env.NODE_ENV !== "production"` so it never ships in the production/shell bundle.

### Route-level state colocation

State ownership rule: **a piece of state lives in the smallest scope that needs it**, and by default that's not the route, let alone the app.

- **Server data** → TanStack Query, keyed by the entity, fetched by the feature hook that needs it (`features/produce/hooks/useSegmentsPage.ts`), not lifted to a route component and prop-drilled.
- **URL-shaped state** (selected chapter, selected tab, filter/search params) → the URL itself, via route params (`[chapterId]`) and `useSearchParams`/`nuqs`-style search-param state, not `useState`. This is also what makes deep links actually work — today's `activeSection`/`selectedChapter` are pure React state, so refreshing the page loses your place.
- **Ephemeral UI state local to one row/panel** (is this row expanded, is this drawer open, current draft text before save) → `useState` *inside that row/panel component*, never lifted.
- **Cross-cutting ephemeral state that many isolated components must read without re-rendering each other** (live job progress ticks) → a small external store (zustand) — see [Real-Time Job & Progress Channel](#real-time-job-progress-channel).

### Eliminating the God component

Target end state: **no component owns unrelated state.** `project-dashboard.tsx` is deleted (see migration plan); its ~45 `useState` calls are redistributed as:

| Old state (project-dashboard.tsx) | New home |
|---|---|
| `projects`, `source`, `chapters`, `scenes`, `segments`, `characters`, `voices`, `issues`, `exports`, `speakerAttributions`, `segmentDirections`, `renderQueue`, `soundAssets`, `soundCues`, `pronunciations`, `structureWarnings`, `structureQuality` | TanStack Query caches, fetched by the feature hook of the route that renders them |
| `job`, `setupJob`, `importJob`, `structureJob`, `localAiJob` | one `useQuery(queryKeys.job(id))` per active job, patched by the SSE stream, rendered by isolated `<JobStatusBadge jobId>` subscriber components |
| `editing`, `draft` | local `useState` inside the segment row that owns it |
| `notice`, `error` | a `Toast` overlay manager (see [Component Architecture](#component-architecture)), pushed by mutation `onError`/`onSuccess` callbacks, not top-level state read by a giant conditional |
| `busy`, `sectionBusy` | replaced by `mutation.isPending`/`query.isFetching` read locally where the spinner is drawn |
| `selectedProjectId`, `selectedChapter`, `activeSection` | URL route params |
| all the form fields (`title`, `author`, `voiceName`, `exportTitle`, …) | `react-hook-form` state local to each form component |

Mutations follow one pattern everywhere: call the mutation → on success, invalidate only the query keys that mutation can affect (declared as part of the mutation hook itself, e.g. `useUpdateSegment` invalidates `queryKeys.segmentsPage(sceneId)` and `queryKeys.reviewTimeline(chapterId)`, nothing else) → optionally patch the cache optimistically before the network round-trip resolves.

### Query key design

A single key-factory module (`apps/web/app/lib/query-keys.ts`) is the source of truth so invalidation prefixes stay consistent across features:

```ts
export const queryKeys = {
  projects: () => ["projects"] as const,
  project: (projectId: string) => ["project", projectId] as const,
  projectSummary: (projectId: string) => ["project", projectId, "summary"] as const,

  source: (projectId: string) => ["project", projectId, "source"] as const,
  sourcePages: (sourceId: string) => ["source", sourceId, "pages"] as const,
  cleaningIssues: (sourceId: string) => ["source", sourceId, "cleaning-issues"] as const,

  chapters: (projectId: string) => ["project", projectId, "chapters"] as const,
  chapter: (chapterId: string) => ["chapter", chapterId] as const,
  scenes: (chapterId: string) => ["chapter", chapterId, "scenes"] as const,
  segmentsPage: (sceneId: string, cursor: string | null) =>
    ["scene", sceneId, "segments", cursor ?? "start"] as const,
  segmentsRoot: (sceneId: string) => ["scene", sceneId, "segments"] as const, // invalidation prefix

  structureWarnings: (projectId: string, cursor: string | null) =>
    ["project", projectId, "structure-warnings", cursor ?? "start"] as const,
  structureQuality: (projectId: string) => ["project", projectId, "structure-quality"] as const,

  characters: (projectId: string, cursor: string | null) =>
    ["project", projectId, "characters", cursor ?? "start"] as const,
  charactersRoot: (projectId: string) => ["project", projectId, "characters"] as const,

  speakerAttributions: (projectId: string, status?: string) =>
    ["project", projectId, "speaker-attributions", status ?? "all"] as const,

  voices: (projectId: string) => ["project", projectId, "voices"] as const,
  production: (projectId: string) => ["project", projectId, "production-settings"] as const,
  productionStatus: (projectId: string, chapterId: string) =>
    ["project", projectId, "chapter", chapterId, "production-status"] as const,

  renderQueue: (projectId: string, chapterId: string) =>
    ["project", projectId, "chapter", chapterId, "render-queue"] as const,
  segmentInspector: (projectId: string, segmentId: string) =>
    ["project", projectId, "segment", segmentId, "inspector"] as const,

  reviewTimeline: (chapterId: string, windowMs?: [number, number]) =>
    windowMs
      ? (["chapter", chapterId, "review-timeline", windowMs] as const)
      : (["chapter", chapterId, "review-timeline"] as const), // no windowMs = invalidation prefix

  issues: (projectId: string, filters: IssueFilters, cursor: string | null) =>
    ["project", projectId, "issues", filters, cursor ?? "start"] as const,
  issuesSummary: (projectId: string) => ["project", projectId, "issues-summary"] as const,

  jobs: (projectId: string) => ["project", projectId, "jobs"] as const,
  job: (jobId: string) => ["job", jobId] as const,

  soundAssets: (projectId: string) => ["project", projectId, "sound-assets"] as const,
  soundCues: (chapterId: string) => ["chapter", chapterId, "sound-cues"] as const,
  pronunciations: (projectId: string) => ["project", projectId, "pronunciations"] as const,

  ttsSettings: () => ["settings", "tts"] as const,
  ttsProviders: () => ["settings", "tts", "providers"] as const,
  localAiCatalog: () => ["settings", "local-ai", "catalog"] as const,

  exports: (projectId: string) => ["project", projectId, "exports"] as const,
  exportEstimate: (projectId: string, params: ExportEstimateParams) =>
    ["project", projectId, "export-estimate", params] as const,
} as const;
```

Every list-shaped family has a corresponding "root" key with no cursor/filter suffix, used purely for prefix invalidation (`invalidateQueries({ queryKey: queryKeys.segmentsRoot(sceneId) })` after a split/merge, without needing to know which page a given segment was on).

### Optimistic updates

Editing patterns (segment text edit, direction save, issue apply/dismiss, character merge) use TanStack Query's mutation lifecycle:

```ts
function useUpdateSegmentText(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; text: string }) => updateSegment(vars.id, vars.text),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.segmentsRoot(sceneId) });
      const previous = queryClient.getQueriesData({ queryKey: queryKeys.segmentsRoot(sceneId) });
      queryClient.setQueriesData(
        { queryKey: queryKeys.segmentsRoot(sceneId) },
        (page: SegmentsPage | undefined) =>
          page && {
            ...page,
            items: page.items.map((s) => (s.id === vars.id ? { ...s, textContent: vars.text, revision: s.revision + 1 } : s)),
          },
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      context?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.segmentsRoot(sceneId) }),
  });
}
```

The row that calls this mutation feels instant (text updates in the cache before the network round-trip completes); a real failure rolls the cache back to the captured snapshot and the row's own error affordance fires — no top-level `error` state needed.

### Abort on route change

Every feature-hook fetch function accepts and forwards an `AbortSignal`; TanStack Query supplies one automatically via the `QueryFunctionContext` (`queryFn: ({ signal }) => fetchSegmentsPage(sceneId, cursor, signal)`), so navigating away from `/produce/[chapterId]` while a segments page is in flight cancels the underlying `fetch` instead of letting it land and update a cache nobody's reading — this is a built-in behavior of `useQuery`/`useInfiniteQuery`, not something to hand-roll, and it directly replaces the current `api.ts`'s complete lack of abort/cancel support (`apps/web/app/api.ts:79-88`'s `request()` takes no signal today).

## Real-Time Job & Progress Channel

### Replacing the five polling loops

[target-architecture.md](../architecture/target-architecture.md) specifies an event-push channel from the job orchestrator. The frontend's contract with it: one Server-Sent Events stream per project (`GET /api/v1/projects/{projectId}/events`, `Accept: text/event-stream`), named events per job/entity change, consumed by a single hook and turned into targeted cache patches — never a global refetch.

```
Backend job runner --events--> SSE stream --> useProjectEventStream(projectId)
                                                     |
                                    +----------------+----------------+
                                    |                                 |
                        queryClient.setQueryData             useJobProgressStore
                        (patches ONE query key)               (ephemeral, per-tick)
                                    |                                 |
                         route components re-render            <JobProgressBar jobId>
                         only if they read that key            re-renders alone
```

### `useProjectEventStream` hook design

```ts
function useProjectEventStream(projectId: string): { connected: boolean } {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const base = getApiBase(); // relative/runtime-overridable, see Desktop/Mobile Shell Readiness
    const source = new EventSource(`${base}/api/v1/projects/${projectId}/events`);

    source.addEventListener("open", () => setConnected(true));
    source.addEventListener("error", () => setConnected(false)); // triggers polling fallback below

    source.addEventListener("job.progress", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as JobProgressEvent;
      queryClient.setQueryData(queryKeys.job(payload.jobId), (prev: Job | undefined) =>
        prev ? { ...prev, status: payload.status, progress: payload.progress } : prev,
      );
      useJobProgressStore.getState().setProgress(payload.jobId, payload.progress);
    });

    source.addEventListener("job.completed", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as JobCompletedEvent;
      queryClient.setQueryData(queryKeys.job(payload.jobId), payload.job);
      // patch only what that job type is documented to affect:
      for (const key of jobAffectedQueryKeys(payload.jobType, payload)) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    });

    source.addEventListener("issue.created", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as IssueEvent;
      queryClient.invalidateQueries({ queryKey: queryKeys.issuesSummary(projectId) });
      queryClient.invalidateQueries({ queryKey: ["project", projectId, "issues"], exact: false });
    });

    source.addEventListener("segment.render.completed", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as SegmentRenderEvent;
      queryClient.invalidateQueries({ queryKey: queryKeys.reviewTimeline(payload.chapterId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.renderQueue(projectId, payload.chapterId) });
    });

    return () => source.close();
  }, [projectId, queryClient]);

  return { connected };
}
```

`jobAffectedQueryKeys(jobType, payload)` is a small lookup table living next to the hook — e.g. `structure.extract` completing invalidates `chapters`, `structureWarnings`, `structureQuality`, `charactersRoot`, `speakerAttributions`; `chapter.produce` completing invalidates that chapter's `productionStatus`, `renderQueue`, `reviewTimeline`. This table is the direct replacement for today's hand-written `refreshStructureDraft`/`refreshProduction`/etc. helpers (`project-dashboard.tsx:234-266`), made declarative instead of imperative.

### Fallback polling with backoff

When `connected` is `false` (SSE never opened, or dropped), affected `useQuery`/`useInfiniteQuery` calls for in-flight jobs switch on a `refetchInterval` fallback:

```ts
function useJob(jobId: string | null, streamConnected: boolean) {
  const [attempt, setAttempt] = useState(0);
  return useQuery({
    queryKey: queryKeys.job(jobId!),
    queryFn: ({ signal }) => getJob(jobId!, signal),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      if (streamConnected) return false; // SSE is doing the work
      const status = query.state.data?.status;
      if (status === "succeeded" || status === "failed" || status === "cancelled") return false;
      return Math.min(1000 * 2 ** attempt, 15_000); // 1s, 2s, 4s, 8s, capped 15s
    },
  });
}
```

`attempt` increments on each poll that doesn't change `status` and resets to 0 the moment `streamConnected` flips back to `true`. This single mechanism is also what backs every screen during the migration window before the SSE endpoint exists at all (`enabled` stays true, `streamConnected` stays permanently `false`, so it behaves like clean polling with backoff instead of today's fixed-interval loops) — see [Incremental Migration Plan](#incremental-migration-plan) step 1.

### Isolated progress subscribers

Job progress ticks arrive as often as the backend chooses to emit them (potentially several per second during structure extraction). Piping every tick through `queryClient.setQueryData` and letting every `useQuery(queryKeys.job(id))` consumer re-render on each tick is *better* than today (scoped to one key) but still means every screen showing a progress percentage re-renders every tick.

For ephemeral, high-frequency, purely-visual progress data, add a small **zustand** store — deliberately not TanStack Query, and deliberately not lifted React state:

```ts
import { create } from "zustand";

type JobProgressState = {
  progress: Record<string, JobProgress>;
  setProgress: (jobId: string, progress: JobProgress) => void;
};

export const useJobProgressStore = create<JobProgressState>((set) => ({
  progress: {},
  setProgress: (jobId, progress) =>
    set((state) => ({ progress: { ...state.progress, [jobId]: progress } })),
}));
```

A dedicated leaf component subscribes with a selector, so it — and only it — re-renders on each tick:

```tsx
function JobProgressBar({ jobId }: { jobId: string }) {
  const progress = useJobProgressStore((state) => state.progress[jobId]);
  return <ProgressBar value={progress?.percent ?? 0} label={progress?.message} />;
}
```

Because zustand's subscription is a plain external store subscribe/selector (via `useSyncExternalStore` under the hood), mounting `<JobProgressBar jobId="job_123" />` inside the Overview's `PipelineRail` or the Produce screen's header does not cause the segment list, the transcript, or any sibling to re-render — the content tree is completely insulated from tick frequency. This is the direct fix for today's failure mode where a poll tick re-renders the entire God component tree.

## List Virtualization & Rendering Discipline

### `@tanstack/react-virtual` adoption

Every list whose size scales with the book adopts `@tanstack/react-virtual`'s `useVirtualizer`:

| List | Component (new) | Est. max rows (500pg book) |
|---|---|---|
| Segment list (produce screen) | `features/produce/components/SegmentListVirtual.tsx` | ~7,000 |
| Chapter transcript / timeline (review screen) | `features/review/components/TranscriptListVirtual.tsx` | ~7,000 per chapter set, windowed per-chapter (~50-300) |
| Character grid (cast screen) | `features/cast/components/CharacterGridVirtual.tsx` | 100-300+ |
| Structure warnings / issue queues | `features/structure/components/WarningListVirtual.tsx`, `features/review/components/IssueListVirtual.tsx` | thousands (2,453 + 731 warnings measured on one real run) |

Each uses a fixed or measured `estimateSize`, `overscan` tuned to ~6-10 rows, and — critically — is fed by `useInfiniteQuery` pages (see [API Contract Requirements](#api-contract-requirements)) so the virtualizer's total `count` reflects the server-reported `totalCount` and only fetched pages populate real rows; unfetched ranges render a lightweight skeleton row rather than blocking.

### Row component design

The rule that fixes "typing one character re-renders every card in the scene" (current `SegmentEditorCard` behavior, since `editing`/`draft` are God-component state passed to every card): **editing state moves down into the row.**

```tsx
const SegmentRow = memo(function SegmentRow({ id }: { id: string }) {
  const segment = useSegment(id); // reads this row's slice only, via `select` on the page query
  const [localDraft, setLocalDraft] = useState<string | null>(null);
  const updateText = useUpdateSegmentText(segment.sceneId);

  const isEditing = localDraft !== null;
  const text = isEditing ? localDraft : segment.textContent;

  return (
    <ListRow>
      {isEditing ? (
        <TextArea value={text} onChange={(e) => setLocalDraft(e.target.value)} onBlur={commit} />
      ) : (
        <Text onClick={() => setLocalDraft(segment.textContent)}>{text}</Text>
      )}
    </ListRow>
  );

  function commit() {
    if (localDraft !== null && localDraft !== segment.textContent) {
      updateText.mutate({ id: segment.id, text: localDraft });
    }
    setLocalDraft(null);
  }
}, (prev, next) => prev.id === next.id);
```

Two properties make this scale:
1. **The only prop is `id`.** It's stable across parent re-renders (list virtualization already keys rows by id), so `memo`'s shallow comparison never sees a new prop unless the row itself is recycled to a different item.
2. **The mutation hook is instantiated per-row and bound to that row's id.** There is no id-keyed callback map to maintain and no lifted `onEdit(id)`/`onSave(id)` prop threaded from the list root — each row owns its own `useMutation` instance, so a keystroke in row 4,021 updates only `localDraft` in row 4,021's local state and touches nothing else. Where a genuinely shared callback is unavoidable (e.g., a list-level "select all" action), it's created once with `useCallback(() => ..., [])` against a functional `setState` updater so its identity never changes across renders.

The same pattern applies to `IssueCard`, `CharacterCard`/`VoiceProfileCard`, and transcript rows: `memo`, id-only props, row-owned local/mutation state.

### Waveform: a single `<canvas>`

The current waveform is one DOM node per amplitude bucket plus one per issue marker, rebuilt on every poll tick (`ChapterTimeline`/review timeline rendering today). Replace it with two stacked canvases so the expensive draw (buckets + markers) and the cheap, high-frequency draw (playhead) never share a repaint:

```tsx
function WaveformCanvas({ buckets, issueMarkers, durationMs, audioRef }: WaveformCanvasProps) {
  const staticRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);

  // Redraw the expensive layer only when the underlying data changes.
  useEffect(() => {
    drawStaticLayer(staticRef.current!, { buckets, issueMarkers, durationMs });
  }, [buckets, issueMarkers, durationMs]);

  // Redraw only the thin playhead layer, driven by rAF while audio is playing.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    let raf: number;
    const tick = () => {
      drawPlayhead(overlayRef.current!, audio.currentTime * 1000, durationMs);
      if (!audio.paused) raf = requestAnimationFrame(tick);
    };
    audio.addEventListener("play", () => (raf = requestAnimationFrame(tick)));
    audio.addEventListener("pause", () => cancelAnimationFrame(raf));
    audio.addEventListener("seeked", () => drawPlayhead(overlayRef.current!, audio.currentTime * 1000, durationMs));
    return () => cancelAnimationFrame(raf);
  }, [audioRef, durationMs]);

  return (
    <div className="waveform" style={{ position: "relative" }}>
      <canvas ref={staticRef} width={WIDTH} height={96} role="img" aria-label="Chapter waveform" />
      <canvas ref={overlayRef} width={WIDTH} height={96} style={{ position: "absolute", inset: 0 }} />
    </div>
  );
}
```

`drawStaticLayer` draws amplitude buckets as a single `fillRect`-per-bucket pass on `staticRef` (still cheap even at thousands of buckets, since canvas drawing is not DOM reconciliation) plus issue markers as small colored ticks; it only re-runs when `buckets`/`issueMarkers`/`durationMs` actually change (i.e., on data load or a new chapter render — not on every poll tick, since progress ticks no longer touch this data per the isolated-subscriber design above). `drawPlayhead` clears and redraws only the thin overlay canvas, driven by `requestAnimationFrame` gated to actual `play`/`pause` events, not a timer. Accessibility: the canvas carries `role="img"` with a text `aria-label` summary; the synced `TranscriptListVirtual` remains the primary, fully keyboard-navigable way to move through the chapter — the canvas is a supplementary visualization, not the only interaction path.

### `useTransition` / `useDeferredValue` for filters

Filter/search inputs across warning, issue, and character lists (severity filter, category filter, search-by-name) wrap the filtered-list computation in `useDeferredValue`, and any state update that triggers a large re-render (e.g., switching the Cast Review tab's status filter across thousands of attribution rows) is dispatched inside `startTransition` from `useTransition`, so the input itself stays responsive (<100ms budget) even while React works through re-rendering the filtered virtualized list in the background at lower priority.

### Code-splitting per route

The App Router already code-splits per route segment by default once real routes exist (each `page.tsx` becomes its own chunk) — today's single `app/page.tsx` gets none of this because everything is one client component. On top of the router's default splitting, wrap genuinely heavy, occasionally-used panels in `next/dynamic` with `ssr: false` (none of this is server-renderable data anyway, per [Non-goals](#non-goals)):

- `EvidenceViewer` (JSON/evidence drawer content)
- `WaveformCanvas`
- `ModelCenter` (Model Center catalog + install UI, behind the `/settings/engine` route already, but its own chunk since it's rarely opened)
- `ExportPanel`'s metadata form (react-hook-form + zod resolver bundle isolated from routes that don't export)

## API Contract Requirements

These are backend changes the frontend needs; sequence and own alongside [target-architecture.md](../architecture/target-architecture.md) so pagination work isn't done twice against two different endpoint shapes.

### Cursor pagination

Every list endpoint whose size scales with the book gets cursor pagination. Cursor shape — opaque to the client, base64 of a small JSON envelope so ordering survives inserts/deletes between pages:

```json
{
  "items": [ { "id": "seg_01h...", "orderIndex": 4021, "...": "..." } ],
  "pageInfo": {
    "nextCursor": "eyJvIjo0MDIxLCJpZCI6InNlZ18wMWguLi4ifQ==",
    "hasMore": true,
    "totalCount": 6995
  }
}
```

Cursor payload before base64-encoding, e.g. for segments: `{"o": <orderIndex>, "id": "<segment id>"}`. Endpoints affected, with suggested query params:

| Endpoint | New params |
|---|---|
| `GET /api/v1/scenes/{sceneId}/segments` | `?cursor=&limit=200` |
| `GET /api/v1/projects/{id}/characters` | `?cursor=&limit=100&sort=displayName` |
| `GET /api/v1/projects/{id}/structure-warnings` | `?cursor=&limit=200&severity=&scopeType=` |
| `GET /api/v1/projects/{id}/issues` | `?cursor=&limit=100&status=&severity=&category=&chapterId=` |
| `GET /api/v1/projects/{id}/speaker-attributions` | `?cursor=&limit=200&status=` (status filter already exists; add cursor) |

`limit` is capped server-side (e.g. 500) regardless of what the client requests, so a malicious or buggy client can't force a full-table fetch back into existence.

### Summary/aggregate endpoints

Overview-class screens must never fetch a full collection to show a count. New/extended endpoints:

- `GET /api/v1/projects/{id}/summary` — chapter/scene/segment/character counts, current pipeline phase, latest job per stage, latest ready chapter render reference. This is what backs `/projects/[projectId]`'s `PipelineRail` and `ListenFirstCard` without pulling `chapters`, `characters`, or `segments` collections at all.
- `GET /api/v1/projects/{id}/issues/summary` — counts grouped by `severity` × `category`, plus the top-N blocking/error issues inline (small, bounded payload) for the Overview's `NeedsAttentionList`.
- `GET /api/v1/projects/{id}/structure/quality` — already exists and is already exactly this pattern (aggregate numbers, no collection); model the two new summary endpoints on it directly.

### Windowed chapter-timeline endpoint

`GET /api/v1/projects/{id}/chapters/{chapterId}/review-timeline` today returns the entire chapter's waveform array and every segment in one payload (confirmed shape in `apps/web/app/api.ts:46`, `ChapterReviewTimeline.segments`/`.waveform`). Add windowing:

```
GET /api/v1/projects/{id}/chapters/{chapterId}/review-timeline?startMs=0&endMs=120000&maxSegments=400
```

Response adds `bucketResolutionMs` (so the client knows the waveform sampling density it received) and returns only segments whose `[startMs, endMs)` overlaps the requested window, plus waveform buckets for that window only. `TranscriptListVirtual` requests windows lazily as the user scrolls, matching the virtualizer's visible range instead of the whole-chapter payload.

### Cheap revalidation (ETag / updatedAt)

All list endpoints above gain an `updatedAt` field per item (several already have it — e.g. `SpeakerAttribution.updatedAt`; extend the rest) and support:

- **`If-None-Match`/`ETag`**: server computes a weak ETag from `hash(count, max(updatedAt))` for the requested filter/cursor combination; a matching `If-None-Match` on a subsequent request returns `304 Not Modified` with no body.
- **`updatedSince` query param**: an alternative, simpler cheap-revalidation path for the polling-fallback mode from [Fallback polling with backoff](#fallback-polling-with-backoff) — `GET /api/v1/projects/{id}/issues?updatedSince=2026-07-07T12:00:00Z` returns only rows changed after that timestamp, so a degraded-mode client polling every few seconds isn't re-fetching thousands of unchanged rows every tick.

As a smaller, optional companion improvement: `docs/api/api-spec.yaml` already exists as the OpenAPI source of truth — generating `apps/web/app/lib/api-types.ts` from it (e.g. via `openapi-typescript`) would remove the current hand-maintained duplication between backend Pydantic models and the ~50 hand-written `type X = {...}` declarations at the top of `apps/web/app/api.ts`, and would make the pagination/summary shapes above type-safe on the frontend automatically once added to the spec. Not required for this migration, but worth sequencing in alongside it.

## Component Architecture

### Feature-folder structure

```
apps/web/app/
  (app)/
    layout.tsx                     # QueryClientProvider, OverlayProvider, AppShell chrome
    projects/
      page.tsx                     # -> features/library
      [projectId]/
        page.tsx                   # -> features/overview
        manuscript/page.tsx        # -> features/manuscript
        structure/page.tsx         # -> features/structure
        cast/page.tsx              # -> features/cast
        produce/[chapterId]/page.tsx   # -> features/produce
        review/[chapterId]/page.tsx    # -> features/review
        export/page.tsx            # -> features/export
    settings/
      engine/page.tsx              # -> features/engine
  features/
    overview/{components,hooks,api}/
    manuscript/{components,hooks,api}/
    structure/{components,hooks,api}/
    cast/{components,hooks,api}/
    produce/{components,hooks,api}/
    review/{components,hooks,api}/
    export/{components,hooks,api}/
    engine/{components,hooks,api}/
    jobs/                          # cross-cutting: shared by every feature
      hooks/useProjectEventStream.ts
      hooks/useJob.ts
      store/jobProgressStore.ts
  design-system/                   # implements docs/ui/design-system.md
    tokens.css
    components/
      Button.tsx  Card.tsx  Badge.tsx  ProgressBar.tsx  Drawer.tsx
      Modal.tsx  Toast.tsx  Tabs.tsx  ListRow.tsx  EmptyState.tsx  ...
  lib/
    api-client.ts                  # fetch wrapper: base URL, AbortSignal passthrough, error shape
    query-client.ts
    query-keys.ts
  layout components (AppShell, nav) stay at the (app) route-group level, not per-feature
```

Each `features/<name>/` folder owns:
- `components/` — presentational pieces specific to that feature (a `CharacterCard` used only in `features/cast` lives there, not in the shared design-system layer).
- `hooks/` — the feature's data hooks (`useSegmentsPage`, `useChapters`, `useUpdateSegmentText`), each a thin wrapper over `useQuery`/`useInfiniteQuery`/`useMutation` plus the feature's slice of `queryKeys`.
- `api/` — the actual `fetch` call functions for that feature's endpoints (the direct successor to today's monolithic `apps/web/app/api.ts`, split by feature rather than one 184-line file with ~90 exports).

This is a straightforward decomposition of the existing `apps/web/app/components/{structure,review,voices,manuscript,export,production,sound}` directories (already organized by feature today, just not routed or state-isolated) plus the existing `apps/web/app/lib/` helpers — the reorganization is mostly a move, not a rewrite.

### The design-system primitives layer

`design-system/` implements the tokens and components specified in [design-system.md](design-system.md) (monochrome palette, thin typography, spacing/type scale, motion spec) as the only place raw HTML form controls and hand-rolled CSS are allowed. Every feature component composes these primitives instead of raw `<select>`/`<input type="range">`/`<details>`/ad-hoc `<button>` styling (the current state — see Root-Cause Analysis's visual-design notes in the research brief). This doc does not define the primitives' visual spec; it defines the boundary: **no feature component owns raw DOM styling for interactive controls** — that's a design-system violation to flag in review, the same way a feature component owning cross-feature state is.

### Overlay system

A single `OverlayProvider`, mounted once in `apps/web/app/(app)/layout.tsx`, replaces the current situation of zero modal/drawer/toast infrastructure (confirmed absent from `apps/web/app/components/common/` today — only `ActionButton`, `ConfirmAction`, `EmptyState`, `InlineNotice`, `StatusBadge`, `StudioCard` exist, no `Modal`/`Drawer`/`Toast`).

```ts
type OverlayState = {
  drawers: OverlayEntry[];
  modals: OverlayEntry[];
  toasts: ToastEntry[];
};

// zustand store, same rationale as job progress: overlay open/close is
// high-frequency-adjacent (many features open/close drawers) and must not
// force a re-render of whatever route is mounted underneath.
export const useOverlayStore = create<OverlayState & OverlayActions>((set) => ({ ... }));

export function useDrawer() {
  const open = useOverlayStore((s) => s.openDrawer);
  const close = useOverlayStore((s) => s.closeDrawer);
  return { open, close };
}

export function useToast() {
  const push = useOverlayStore((s) => s.pushToast);
  return { push }; // e.g. push({ tone: "error", message })
}
```

Overlays render via `createPortal` from a single mount point in the root layout — one `Drawer` stack, one `Modal` stack, one `Toast` stack for the entire app, regardless of which feature opened them. This directly replaces `notice`/`error` top-level state (`project-dashboard.tsx:51`) and the ad-hoc `activeIssue`/inspector state currently used to fake a drawer.

### Form patterns

Multi-field forms (New Project, Export metadata, Direction editor, Character edit) use `react-hook-form` with `@hookform/resolvers/zod` schema validation. Two reasons this matters for performance specifically, not just ergonomics: `react-hook-form` is uncontrolled by default, so keystrokes in one field do not re-render the rest of the form (unlike today's pattern of one `useState` per field on the God component, e.g. `exportTitle`/`exportAuthor`/`exportAlbum`/`exportPublisher`/`exportLanguage`/`exportCoverPath` — six separate top-level states for one form); and its validation/submit state (`formState.isSubmitting`, `formState.errors`) replaces the hand-rolled `busy`/`error` flags per form.

## Performance Verification

### Synthetic fixture

A deterministic synthetic fixture — 500 pages, ~7,000 segments, ~120 characters, ~600 mixed warnings/issues — matching the real measured worst case in [Root-Cause Analysis](#root-cause-analysis-why-the-current-ui-freezes). Because `test-assets/` is git-ignored and never committed (per repo convention), the fixture is **generated, not checked in**: a backend seeding script (e.g. `apps/api/scripts/seed_large_project.py`, invoked from Playwright's `globalSetup`) inserts chapters/scenes/segments/characters/warnings directly via the repository layer — no LLM calls, no real extraction run — so it's fast and fully deterministic across CI runs. This keeps the *structural* shape (segment count, nesting, warning density) real without needing a 7-hour pipeline run in CI.

### Main-thread-block assertions

New Playwright spec `apps/web/tests/perf-large-book.spec.ts`, alongside the existing `apps/web/tests/foundations.spec.ts` and reusing `apps/web/playwright.config.ts`'s existing API+web `webServer` bootstrap:

1. Seed the large-book fixture via the API before navigating.
2. Install a `PerformanceObserver({ entryTypes: ["longtask"] })` via `page.evaluate` before the interaction under test, collecting entries onto `window.__longtasks`.
3. Drive the actual interaction: type into an open segment row on `/produce/[chapterId]`, scroll the virtualized segment list by several thousand rows, open an inspector drawer.
4. Read back `window.__longtasks` and assert no entry exceeds 50ms (budget from [Goals](#goals)) during the interaction window.
5. Measure `/projects/[projectId]` cold-load-to-interactive and assert under 2s.

### React Profiler budget checks

Wrap route subtrees in `<Profiler>` under a `NEXT_PUBLIC_PROFILE=1` build-time flag only (never in the production/shell bundle), with an `onRender` callback pushing `{ id, phase, actualDuration }` samples to `window.__profilerSamples`. Two specific budget assertions the Playwright perf spec checks against these samples:
- No `update`-phase sample exceeds 16ms (one frame) for the route-level `Profiler` during a single-row edit.
- Tagging each virtualized row with its own `Profiler id={`segment-row-${id}`}`, assert that editing row A produces **zero** samples for any other row's `Profiler` id — the direct regression test for today's "typing re-renders every card in the scene" bug.

### Bundle-size budget per route

A script (`apps/web/scripts/check-bundle-budget.mjs`) reads the Next.js build output (`.next/app-build-manifest.json` / route-level First Load JS reported by `next build`) and asserts each route stays under a budget, excluding the shared framework chunk:

| Route | Budget (gzip, first load JS, route-specific) |
|---|---|
| `/projects` | 130 KB |
| `/projects/[projectId]` | 150 KB |
| `/projects/[projectId]/structure` | 220 KB (virtualization + tree UI) |
| `/projects/[projectId]/produce/[chapterId]` | 240 KB (virtualization + waveform/audio) |
| `/projects/[projectId]/review/[chapterId]` | 240 KB |
| `/projects/[projectId]/cast`, `/export`, `/manuscript` | 180 KB each |
| `/settings/engine` | 160 KB |

### CI gates

Add a `perf` job to `.github/workflows/ci.yml` (new — proposed, not yet added), running after the existing `smoke` job: `npm run web:test:perf` (new script wrapping the perf Playwright spec) plus `node apps/web/scripts/check-bundle-budget.mjs`. Recommend landing this job as `continue-on-error: true` for the first migration phase (budgets will be volatile while routes are actively being extracted — see migration plan), then flipping it to blocking once two consecutive weeks of green runs establish the budgets are realistic, mirroring how the existing `backend`/`web`/`migrations`/`smoke` jobs are already structured as sequential gates in that file.

## Incremental Migration Plan

Ordered so the app stays fully working — and deployable — after every single step. Each step is independently shippable; none requires the next to be safe to merge.

**1. Introduce TanStack Query alongside the God component — days.**
Add `@tanstack/react-query`, mount `QueryClientProvider` in the existing layout, and convert only the highest-value reads to `useQuery`/polling-with-backoff: the `job`/`structureJob` polling effects (`project-dashboard.tsx:129-166`, currently 1000ms/500ms fixed `setTimeout` loops) become `useQuery({ refetchInterval: backoffFn })`. Nothing else in the God component changes yet — the query cache and the remaining ~40 `useState` calls coexist.
> **Quick win, callable out on its own:** replacing just those two polling effects with query-driven polling, combined with wrapping `SegmentEditorCard` in `React.memo` with an id-stable comparator (a few lines, no structural change needed), removes two of the five fixed-interval full-tree re-render sources and the single worst per-keystroke re-render source simultaneously. This is realistically a 1-2 day change and is very likely to visibly eliminate most "page unresponsive" incidents on its own, before any routing work starts.

**2. Memoize the remaining hot leaves — days.**
`React.memo` on `IssueCard`, `VoiceProfileCard`, `CharacterBible`'s row renderer, `SegmentList`'s row renderer; `useCallback` on the ~30 inline handlers `project-dashboard.tsx` passes into `StoryMapPanel`/`ReviewPatchPanel`/`VoiceBiblePanel`. No behavior change, pure performance.

**3. Virtualize the two worst offenders in place — days to about a week.**
Drop `@tanstack/react-virtual` into `SegmentList` and `ChapterTimeline`/`ChapterTranscriptReview` while they still live inside the monolith and still receive the full unpaginated array from the backend (virtualizing the DOM is valuable even before the backend ships cursor pagination — it just means the virtualizer's data source is a full in-memory array for now, upgraded to paged fetches in step 7).

**4. Extract routes one screen at a time, heaviest first — weeks.**
Each extraction: create the new route under `apps/web/app/(app)/projects/[projectId]/...`, build its `features/<name>/` hooks against TanStack Query directly (no God-component props), and leave `project-dashboard.tsx` serving the remaining not-yet-migrated sections. Order, heaviest/most re-render-prone first:
   - a. `/produce/[chapterId]` (the segment editing surface — `StoryMapPanel` + `SegmentList` + audio player + render queue) — highest impact, ~1-2 weeks.
   - b. `/structure` (chapters/scenes/warnings, split out of `StoryMapPanel`) — ~1 week.
   - c. `/cast` (`VoiceBiblePanel` split into character bible / cast review / voice profiles) — ~1 week.
   - d. `/review/[chapterId]` (`ReviewPatchPanel` + the canvas waveform rewrite) — ~1-2 weeks.
   - e. `/export`, `/manuscript`, `/settings/engine`, `/projects` — lighter, less state; ~1 week combined.

**5. Wire the SSE event stream once the backend endpoint from [target-architecture.md](../architecture/target-architecture.md) lands — backend-gated, ~1-2 weeks on the frontend side.**
Add `useProjectEventStream`, keep the step-1 polling-with-backoff path wired but dormant (`enabled: !connected`) as the automatic degraded-mode fallback. This step is explicitly decoupled from steps 1-4 so frontend work isn't blocked on backend job-orchestration timing.

**6. Retire `project-dashboard.tsx` entirely.**
Once every section has a route, delete the God component, `apps/web/app/page.tsx`'s single-route shell, and `apps/web/app/lib/workflow.ts`'s step machine (replaced by route-driven navigation plus the Overview's single "next best action" chip).

**7. Apply the design-system primitives pass.**
Swap raw `<select>`/`<input type="range">`/`<details>`/ad-hoc CSS for `design-system/components/*` across all routes. Independent of steps 1-6 and can run in parallel once [design-system.md](design-system.md)'s primitives exist — it's a styling/markup change, not a state or data-flow change.

`npm run web:test:smoke` (and, from step onward where it exists, `npm run web:test:perf`) must stay green after every one of these steps; update `apps/web/tests/foundations.spec.ts`'s navigation assumptions incrementally as each route lands rather than in one big-bang rewrite at the end.

## Desktop/Mobile Shell Readiness

Full packaging detail (installers, model download managers, hardware tiering) is [cross-platform-strategy.md](../platform/cross-platform-strategy.md); this section covers only what the frontend architecture must guarantee so that document's shell strategy is viable:

- **Already true today, keep it true:** the app is `"use client"` all the way down (`project-dashboard.tsx:1`) with no Next.js server actions, no API routes under `app/api/*`, and no server-only Node APIs (`fs`, `child_process`) anywhere in `apps/web/app`. This means the app is already, structurally, a pure client SPA that happens to be served by `next dev`/`next start` today — nothing in this migration should introduce a server-only dependency. Recommend a lint rule (`no-restricted-imports` for `fs`/`net`/`child_process`/`node:*` under `apps/web/app/**`) to keep this invariant enforced rather than just observed.
- **Relative, runtime-overridable API base.** Today's API base is a build-time env var (`process.env.NEXT_PUBLIC_API_URL`, `apps/web/app/api.ts:76`), which is fine for the web dev server but not for a shell that doesn't know at build time which local port its embedded engine will bind. Add a runtime override the native shell can inject before hydration (e.g. `window.__ECHODRAFT_API_BASE__` set by a bootstrap script the Tauri/Capacitor wrapper injects), read by `getApiBase()` in `apps/web/app/lib/api-client.ts` with the current env var as the fallback for plain-browser/dev usage. This is the same `getApiBase()` referenced in the SSE hook above — one function, one source of truth for both `fetch` calls and `EventSource` URLs.
- **Static export compatibility.** For embedding in Tauri, the app should be buildable as a static export (`next build` with `output: "export"`, or served by a minimal static file server bundled into the shell) so no Node runtime is required at runtime inside the desktop app — only the FastAPI engine (already a self-contained local process per [architecture.md](../architecture/architecture.md)) needs to run. This constrains route design to avoid anything that requires the Next.js server runtime (server components fetching at request time, server actions, dynamic API routes) — consistent with this doc's routes all being client components reading from TanStack Query against the FastAPI backend.
- **SSE in embedded WebViews.** `EventSource` is available in Capacitor's WebView and Tauri's WebView on all target platforms, but verify behavior on older Android system WebViews specifically; the polling-with-backoff fallback from [Real-Time Job & Progress Channel](#real-time-job-progress-channel) already covers this automatically if `EventSource` construction fails or never opens — no shell-specific branch needed in application code.
- **Mobile layout is out of scope for this pass** — routes and data layer are shell-agnostic, but responsive/touch layout for Capacitor is a [design-system.md](design-system.md) concern, not this doc's.

## Risks & Open Questions

- **SSE has no custom-header auth story.** `EventSource` cannot set arbitrary request headers, which is fine for a local-only, unauthenticated engine today but would need revisiting (likely a move to `fetch` + `ReadableStream` or WebSocket) if [target-architecture.md](../architecture/target-architecture.md) or a future hosted mode adds auth. Flag for joint resolution with that document.
- **Zustand vs. TanStack Query alone for ephemeral progress.** This doc chooses a separate zustand store for job-progress ticks specifically to guarantee zero re-render of unrelated components via selector-based external-store subscription. If TanStack Query v5's per-observer `notifyOnChangeProps` fine-graining proves sufficient in practice during step 5's implementation, the zustand store could be dropped in favor of one less dependency — worth revisiting with real profiling data rather than deciding it up front.
- **Cursor pagination is real backend migration work** across roughly five endpoints, with real risk of being redesigned twice if sequenced independently of [target-architecture.md](../architecture/target-architecture.md)'s own data-model changes. Needs a shared owner before implementation starts on either side.
- **Canvas accessibility** requires deliberate testing: the waveform's `aria-label` summary and the synced transcript list must be verified as a genuinely sufficient non-visual navigation path, not just a checkbox — recommend a manual screen-reader pass on `/review/[chapterId]` before considering that route done.
- **Fixture generation ownership.** The synthetic 500-page/7,000-segment fixture in [Performance Verification](#performance-verification) is specified as a backend seeding script invoked from Playwright, but could instead live purely in the frontend test suite calling only public API endpoints (slower, but zero backend-internals coupling). Decide before implementing step-9-equivalent CI work, since the two approaches have different maintenance owners.
- **`react-hook-form` and `zustand` are new dependencies** not currently in `apps/web/package.json` (today's dependency list is just `next`/`react`/`react-dom`) — same for `@tanstack/react-query` and `@tanstack/react-virtual`. None are exotic or heavy, but all four should be added deliberately in step 1/3's PRs with bundle-size budget checks (once they exist, per [Performance Verification](#performance-verification)) run against the very PR that introduces them, not after the fact.
