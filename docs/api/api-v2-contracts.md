# API v2 Contracts — Consolidated Delta

## Purpose

The v2 target-architecture suite (`docs/architecture/target-architecture.md`,
`docs/ui/frontend-architecture.md`, `docs/pipeline/casting/automatic-casting-v2.md`,
`docs/pipeline/assembly/generative-sound-design.md`,
`docs/pipeline/tts/tts-engine-strategy.md`, `docs/platform/cross-platform-strategy.md`,
`docs/architecture/extraction-pipeline-v2.md`) each propose API-surface changes
independently, from their own vantage point, while researching a specific
pipeline stage or client concern. Read together they do not fully agree with
each other — different pagination envelopes, different event-stream paths,
overlapping cursor conventions — because each document sequenced its own
proposal before this doc existed to reconcile them.

**This document is that reconciliation.** It is the single place that:

1. States the API design conventions every v2 endpoint must follow (versioning,
   errors, auth, idempotency).
2. Defines the **one** pagination, summary, event-stream, and caching contract
   every endpoint below adopts — explicitly overriding any sibling document
   that sketched a different shape.
3. Specifies every new and changed endpoint proposed across the suite, with
   concrete request/response JSON and error cases, so a backend implementer
   does not have to cross-reference six documents to build one endpoint.

## Scope

This is a **delta document against [`api-spec.yaml`](api-spec.yaml)**, not a
replacement for it. `api-spec.yaml` remains the OpenAPI source of truth for
today's shipped v1 surface (and, per the `openapi-typescript` idea floated in
[`frontend-architecture.md`](../ui/frontend-architecture.md), the eventual
generator input for the frontend's typed client). This document:

- Uses markdown + JSON code blocks, per the doc-suite convention, precisely
  because the shapes here are still proposals under review — folding them into
  `api-spec.yaml` as real OpenAPI schemas is follow-up work once a shape is
  accepted, tracked in [§10](#10-compatibility--rollout). **This file does not
  edit `api-spec.yaml`.**
- Covers only endpoints that are **new** or **changed** by the v2 docs.
  Unlisted `api-spec.yaml` endpoints (rights, exports, pronunciation, source
  import mechanics, structure locks, comments, etc.) are unaffected and keep
  their current v1 shape.
- Does not restate pipeline algorithms (extraction confidence model, casting
  scoring, sound-plan derivation, TTS engine tiering) — those live in their
  owning docs and are linked from each endpoint section. This document only
  specifies the **wire contract** those algorithms are invoked and observed
  through.

---

## 1. API design conventions v2

### 1.1 Versioning strategy: stay on `/api/v1`, evolve additively

**Decision: no `/api/v2` URL prefix.** Every endpoint below is added under the
existing `/api/v1` namespace.

**Rationale.** URL versioning (`/api/v1` vs `/api/v2` as parallel, independently
deployed trees) exists to let old and new clients hit the same server
simultaneously during a slow rollout. Echodraft does not have that problem: per
[`cross-platform-strategy.md`](../platform/cross-platform-strategy.md) §3
("Sidecar lifecycle"), the FastAPI engine is a **private sidecar process spawned
by, and versioned with, its own UI** — there is no independent third-party
client, no server shared across app versions, and no scenario where a v1 UI
build talks to a v2 engine build or vice versa. A URL version fork would only
buy compatibility we structurally cannot need, at the cost of maintaining two
live route trees. Instead:

- Breaking changes use the **per-endpoint deprecation window** defined in
  [§2](#2-pagination-standard) and [§10](#10-compatibility--rollout) (old shape
  kept until the corresponding frontend migration step lands, per
  [`frontend-architecture.md`](../ui/frontend-architecture.md)'s Incremental
  Migration Plan), not a parallel URL tree.
- "v2" in this suite's file names refers to the **feature generation**
  (extraction v2, casting v2, TTS v2, sound design v2), not a URL version — all
  of it ships under `/api/v1`.
- If a future **optional**, non-mandatory hosted/companion mode (already
  gestured at in [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md)
  §6's "Companion mode") ever needs to serve genuinely independent client
  versions against one long-lived server, that is the point to introduce real
  URL versioning — revisit then, not preemptively.

### 1.2 Error envelope

Today: bare FastAPI `HTTPException(status_code, detail=str(...))` →
`{"detail": "..."}`, with no machine-readable error code anywhere in the
codebase (confirmed throughout `apps/api/src/echodraft_api/main.py`). v2
introduces a structured envelope for every 4xx/5xx response:

```json
{
  "error": {
    "code": "casting.narrator_locked",
    "message": "Cannot reassign narrator voice: locked by user.",
    "details": { "characterId": "char_042", "lockedVoiceId": "voice_009" },
    "requestId": "req_9f3c2a1b"
  }
}
```

- **`code`** — stable, dot-namespaced (`<domain>.<reason>`), safe to branch on
  in client code; never changes wording across releases.
- **`message`** — human-readable, safe to show directly in the UI's toast/error
  surface (the `useToast` pattern in `frontend-architecture.md`).
- **`details`** — optional structured context specific to `code`; shape varies
  per error, documented per endpoint below where non-obvious.
- **`requestId`** — correlates to the structured log line (`echodraft_api/logging.py`)
  for support/debugging; also useful for the debug-bundle capture described in
  `target-architecture.md` §8.
- **Validation errors (422)** keep FastAPI's per-field structure, nested at
  `details.fields` as an array of `{loc, msg, type}` (unchanged from Pydantic's
  native shape) rather than inventing a new validation format.

**Compatibility.** Because engine and UI ship as one versioned unit (§1.1),
there is no fleet of old clients parsing `{"detail": ...}"` against a new
server — the switch to the structured envelope happens in one deploy step (see
rollout Phase 0 in [§10](#10-compatibility--rollout)), not behind a
content-negotiation flag.

### 1.3 Auth: localhost token from the desktop shell

Reconciles [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md)
§3.4–3.5. Today, `127.0.0.1:8000` accepts requests from any local process,
unauthenticated. Packaging is the point this closes:

- The packaged production entrypoint (`echodraft_api.server`, new — see
  cross-platform-strategy.md §3.3) mints a bearer token per process launch and
  writes it to the runtime handoff file (`.echodraft/runtime/engine.json`). The
  desktop shell reads it and sends `Authorization: Bearer <token>` on every
  request.
- Missing or stale token → `401` with `error.code` = `auth.missing_token` or
  `auth.invalid_token`.
- **Dev-mode fallback.** The existing dev entrypoint
  (`uvicorn.run("echodraft_api.main:app", ...)` in `main.py`) keeps running in
  "open" mode (no auth required) for local development ergonomics — auth
  enforcement is gated by `ECHODRAFT_REQUIRE_AUTH`, default `false` for
  `main.py`'s dev server and `true` for the packaged `echodraft_api.server`
  entrypoint. This preserves today's zero-friction `uv run` workflow.
- **SSE special case.** Browser `EventSource` cannot set custom request
  headers — a gap `frontend-architecture.md` flags under Risks as needing
  "joint resolution with [target-architecture.md]". Resolution: the
  `GET /api/v1/projects/{projectId}/events` endpoint ([§4](#4-event-stream-contract))
  additionally accepts the token as a query parameter (`?token=`), since it is
  the one endpoint a browser-native `EventSource` must reach without a header.
  This is a deliberate, narrow exception — flagged as an open question in
  [§11](#11-open-questions) because a token in a URL can leak into logs/history
  more easily than a header.

### 1.4 Idempotency keys for mutating pipeline operations

New: an optional `Idempotency-Key` request header, honored on every endpoint
that **launches a job** (extraction start, speaker-attribution run, direction
inference, casting auto-run, chapter/segment generate, chapter assemble, sound
plan run, sound asset regenerate, export create, source import/reparse, voice
preview). None of the six source documents specify this — it is a genuine gap:
the SSE-reconnect-with-polling-fallback design in
[§4](#4-event-stream-contract) means a client can legitimately be unsure
whether its last mutating POST landed after a dropped connection, and
re-submitting a 30-minute extraction job by accident is exactly the kind of
failure this product cannot afford to reintroduce.

- Server stores `(idempotencyKey, endpoint, requestBodyHash) → response` in a
  new small `idempotency_keys` table, TTL 24h (metadata only — no different
  from any other row in this codebase's SQLite-metadata-only convention).
- A replayed request with the same key and same body hash gets the **original**
  response replayed verbatim (same status code, same body) — no second job is
  launched.
- A replayed request with the same key but a **different** body hash gets
  `409` with `error.code = "idempotency.key_reused_with_different_payload"`.
- Omitting the header preserves today's behavior exactly (at-most-once is
  opt-in, never forced on a caller that doesn't send the header).

---

## 2. Pagination standard

### Reconciling two drafts

[`target-architecture.md`](../architecture/target-architecture.md) §7.1
sketched `?limit=&cursor=` → `{items, nextCursor, total}`.
[`frontend-architecture.md`](../ui/frontend-architecture.md) "API Contract
Requirements" independently specified a richer envelope
(`{items, pageInfo: {nextCursor, hasMore, totalCount}}`) with a concrete cursor
payload and a five-endpoint table. **This document adopts the
`frontend-architecture.md` envelope as canonical** and treats
`target-architecture.md`'s `{items, nextCursor, total}` sketch as an earlier,
superseded draft of the same idea — the `pageInfo` wrapper is strictly more
useful (explicit `hasMore` boolean rather than requiring the client to infer
"no more pages" from `nextCursor` being `null`, which is easy to get wrong when
`nextCursor` might legitimately be absent vs. explicitly `null`) and
`frontend-architecture.md` did the harder work of enumerating the affected
endpoints and their sort keys, which this document extends.

### Cursor format

Opaque, base64url-encoded (no padding), never constructed or parsed by the
client — only round-tripped. The payload **before** encoding is a compact JSON
object naming the sort key and a tie-breaking id:

```json
{ "k": 4021, "id": "seg_01h8x9v2t3q7z" }
```

`k` holds whatever value the endpoint's sort key uses (an integer for
`orderIndex`, an ISO-8601 string for `updatedAt`/`createdAt`). Including `id`
as a secondary key means pagination stays stable even when two rows share the
same primary sort value, and survives inserts/deletes between page fetches
(the classic offset-pagination failure mode this design deliberately avoids).

### Request / response shape

```
GET /api/v1/scenes/{sceneId}/segments?cursor=eyJrIjo0MDIxLCJpZCI6InNlZ18wMWguLi4ifQ&limit=200
```

```json
{
  "items": [
    { "id": "seg_01h8x9v2t3q7z", "sceneId": "scene_014", "orderIndex": 4021, "...": "..." }
  ],
  "pageInfo": {
    "nextCursor": "eyJrIjo0MjIxLCJpZCI6InNlZ18wMWguLi4ifQ",
    "hasMore": true,
    "totalCount": 6995
  }
}
```

`nextCursor` is `null` (and `hasMore` is `false`) on the last page.
`totalCount` is the full filtered count, computed once per distinct filter
combination and cheap to keep accurate because it is a `COUNT(*)` over an
already-indexed query, not a full row fetch.

`limit` is **always clamped server-side** to the endpoint's max regardless of
what the client requests — this is a deliberate hardening the current v1 API
lacks entirely (there is no limit of any kind today), closing off a
buggy-client-forces-a-full-table-fetch failure mode by construction.

### Endpoints adopting pagination

| Endpoint | Default limit | Max limit | Sort key |
|---|---|---|---|
| `GET /api/v1/scenes/{sceneId}/segments` | 200 | 500 | `orderIndex` |
| `GET /api/v1/projects/{projectId}/chapters/{chapterId}/segments` *(new — flat chapter-scoped segment list; see [§8](#8-changed-endpoints))* | 200 | 500 | `orderIndex` |
| `GET /api/v1/projects/{projectId}/characters` | 100 | 500 | `displayName` |
| `GET /api/v1/projects/{projectId}/structure-warnings` *(deprecated — see [§8](#8-changed-endpoints))* | 200 | 500 | `createdAt` |
| `GET /api/v1/projects/{projectId}/review-tasks` *(new, [§6.1](#61-extraction-v2))* | 50 | 200 | `createdAt` desc |
| `GET /api/v1/projects/{projectId}/issues` | 100 | 500 | `createdAt` desc |
| `GET /api/v1/projects/{projectId}/speaker-attributions` | 200 | 500 | `updatedAt` |
| `GET /api/v1/voice-catalog` *(new, [§6.2](#62-casting-v2))* | 100 | 500 | `displayName` |
| `GET /api/v1/projects/{projectId}/casting/decisions` *(new, [§6.2](#62-casting-v2))* | 100 | 500 | `prominenceRank` |
| `GET /api/v1/jobs/{jobId}/checkpoints` *(new, [§5](#5-job-control))* | 100 | 1000 | `unitKey` |

`GET /api/v1/projects/{projectId}/chapters` and `GET /api/v1/local-ai/catalog`
are deliberately **not** paginated — chapter counts and the model catalog are
both bounded (tens, not thousands) by nature, and pagination there would add
ceremony with no benefit.

### Deprecation path for unpaginated responses

Every endpoint gaining pagination keeps its **existing bare-array response as
the default** — a request with neither `cursor` nor `limit` present returns
the same unpaginated `[...]` shape it does today, plus a new
`X-Pagination-Available: true` response header so a client can detect
readiness without probing. A request that supplies `cursor` and/or `limit`
opts into the new `{items, pageInfo}` envelope immediately.

The **compatibility window** for each endpoint ends — and the bare-array
default is removed — when the frontend route that owns that data finishes
migration per [`frontend-architecture.md`](../ui/frontend-architecture.md)'s
Incremental Migration Plan §10 steps 4a–4e (mapped explicitly in
[§10](#10-compatibility--rollout) below). This ties the backend's compatibility
window to a concrete, already-planned frontend milestone instead of an
arbitrary time-based sunset, matching the "shippable at every step" philosophy
both `target-architecture.md` §9 and `frontend-architecture.md` §10 already
commit to.

---

## 3. Summary/aggregate endpoints

Overview-class screens must never fetch a full collection to render a count —
the root cause of `loadProject`'s 14-concurrent-GET storm today. Three
endpoints, modeled directly on the one summary endpoint that already exists
and already gets this right (`GET /api/v1/projects/{projectId}/structure/quality`,
per `frontend-architecture.md`'s own instruction to "model the two new summary
endpoints on it directly"):

### `GET /api/v1/projects/{projectId}/summary`

Backs the Overview route's `PipelineRail` and `ListenFirstCard` without
touching `chapters`, `characters`, or `segments` collections.

```json
{
  "projectId": "proj_853c19aa7bbb4706",
  "counts": {
    "chapters": 42, "scenes": 611, "segments": 6995,
    "characters": 118, "openIssues": 23, "openReviewTasks": 6
  },
  "pipelinePhase": "casting",
  "latestJobPerStage": {
    "structure": { "jobId": "job_3c8fbf01", "status": "succeeded", "finishedAt": "2026-07-07T10:02:11Z" },
    "casting":   { "jobId": "job_9a21ee44", "status": "running", "startedAt": "2026-07-07T11:58:00Z" }
  },
  "latestReadyChapterRender": { "chapterId": "chap_001", "renderId": "rndr_77c1", "durationMs": 812340 }
}
```

### `GET /api/v1/projects/{projectId}/issues/summary`

Backs the Overview's `NeedsAttentionList`: counts grouped by severity ×
category, plus a small bounded inline list of the highest-priority items so
the Overview never needs a separate paginated fetch just to show "3 things
need you."

```json
{
  "totalOpen": 23,
  "bySeverityAndCategory": {
    "blocking": { "cast_discovery": 1, "render_qa": 2 },
    "warning":  { "cast_discovery": 4, "attribution": 9, "casting_quality": 3 },
    "info":     { "attribution": 4 }
  },
  "topIssues": [
    { "id": "iss_0091", "severity": "blocking", "category": "render_qa", "title": "Chapter 12: missing_audio on 1 segment", "chapterId": "chap_012" }
  ]
}
```

`topIssues` is capped at 10 server-side regardless of query params — it exists
to make the Overview screen's "needs attention" chip cheap, not to replace the
paginated `/issues` list.

### `GET /api/v1/projects/{projectId}/chapters/summary`

Backs chapter readiness at a glance (the per-chapter row in the Overview and
the `PipelineRail`) without fetching each chapter's scenes/segments. One row
per chapter, still cheap even at hundreds of chapters:

```json
{
  "chapters": [
    {
      "chapterId": "chap_012", "title": "Chapter 12", "orderIndex": 11,
      "status": "structure_complete", "segmentCount": 187,
      "readyForRender": true, "blockingIssueCount": 1,
      "latestRender": { "renderId": "rndr_5521", "status": "succeeded", "durationMs": 743210 }
    }
  ]
}
```

`readyForRender` is `true` iff every non-empty segment has a successful render
and there is no `blocking`-severity open issue scoped to the chapter — the
same precondition `POST .../assemble` already enforces (422 on failure today),
surfaced ahead of time so the UI can show readiness without attempting and
failing an assemble call.

---

## 4. Event stream contract

### Path: reconciling the endpoint location

`target-architecture.md` §7.2 proposed a flat, query-scoped path:
`GET /api/v1/events?projectId=&jobId=&stage=`. This document instead adopts
**`GET /api/v1/projects/{projectId}/events`** as the canonical path —
consistent with every other project-scoped resource in this API (`/issues`,
`/chapters`, `/characters`, ...) being a path segment under `/projects/{projectId}`,
not a query filter on a flat collection. `jobId` and `stage` remain valid
**optional query filters** to narrow an already project-scoped stream:

```
GET /api/v1/projects/{projectId}/events?jobId=job_3c8fbf01&stage=speaker_attribution
Accept: text/event-stream
Authorization: Bearer <token>          (or ?token=<token>, see §1.3)
Last-Event-ID: 84210                   (optional — reconnect/replay)
```

### Event envelope

The envelope itself is taken from `target-architecture.md` §3.6 largely as
specified — it is well designed — with two additions this document makes
definitive:

```json
{
  "schemaVersion": "1.0.0",
  "eventId": 84213,
  "ts": "2026-07-07T12:00:00.123Z",
  "jobId": "job_3c8fbf0189cd4c8e",
  "projectId": "proj_853c19aa7bbb4706",
  "type": "unit.completed",
  "stage": "speaker_attribution",
  "scope": { "chapterId": "chap_002", "sceneId": "scene_014" },
  "payload": {
    "unitKey": "b1946ac9...",
    "status": "done",
    "durationMs": 3120,
    "cacheHit": false
  }
}
```

On the wire, this becomes a standard SSE frame with `id:` set to `eventId` (the
value `Last-Event-ID` replay keys off) and `event:` set to `type`:

```
id: 84213
event: unit.completed
data: {"schemaVersion":"1.0.0","eventId":84213, ... }

```

### Event type taxonomy (definitive)

`target-architecture.md` §3.6 sketched an initial taxonomy. This is the
definitive version — it renames `job.running` → `job.started` for symmetry
with `stage.started`/`unit.started`, adds the terminal `job.completed_with_issues`
state that §3.7's failure-isolation design requires but the original taxonomy
omitted, adds an `entity.updated` family (needed for the cache-invalidation
composition in [§9](#9-caching--consistency), which no source document fully
specified), adds `render.completed` (segment/chapter render artifacts,
narrower than the coarser `artifact.ready`), and fixes all type names to
dot-namespacing throughout (no hyphens) so client-side `switch` dispatch is
uniform. It also standardizes on the codebase's existing American-English
spelling (`canceled`, matching the shipped `POST /jobs/{jobId}/cancel`
endpoint) rather than the double-`l` spelling used loosely in planning prose.

| `type` | `payload` shape | Meaning |
|---|---|---|
| `job.queued` | `{}` | Job accepted, not yet running |
| `job.started` | `{}` | First unit dispatched |
| `job.progress` | `{stages: [{id, done, total, failed, status}]}` | Coarse fan-out snapshot, throttled to ~1/sec even if units complete faster |
| `job.succeeded` | `{}` | All units done, no failures |
| `job.completed_with_issues` | `{failedUnitCount, issueIds: [...]}` | Terminal but non-fatal — some units failed, durable issues were opened, manifest is coherent (`target-architecture.md` §3.7) |
| `job.failed` | `{reason}` | A structural precondition failed; job did not complete |
| `job.canceled` | `{}` | User-requested stop landed |
| `job.resumed` | `{}` | A `RESUMABLE` job was restarted |
| `stage.started` / `stage.completed` | `{stage}` | Per-stage boundary |
| `stage.progress` | `{stage, done, total, failed}` | Per-stage fan-out tick |
| `unit.started` / `unit.completed` / `unit.failed` / `unit.retrying` | `{unitKey, status, durationMs, cacheHit}` | Per-unit fan-out (scene-level granularity) |
| `entity.updated` | `{entityType, entityId, action}` — `entityType ∈ {chapter, scene, segment, character, issue, reviewTask, voiceProfile, castingDecision, soundCue}`, `action ∈ {created, updated, deleted}` | Drives client-side query-cache invalidation ([§9](#9-caching--consistency)) |
| `render.completed` | `{scope: "segment"\|"chapter", scopeId, renderId, status}` | A segment or chapter render finished (narrower than `artifact.ready`, which also covers non-render artifacts like a sound-plan manifest) |
| `artifact.ready` | `{artifactType, path}` | Any durable, playable/inspectable artifact became available (drives progressive audio per `target-architecture.md` §5) |
| `issue.opened` / `issue.resolved` | `{issueId, category, severity}` | Review-queue deltas |

### Replay / reconnect semantics

- Every event is persisted to `job_events` (already specified in
  `target-architecture.md` §6.1) keyed by a monotonically increasing
  `event_id` **per project** (not global), which is exactly the value used as
  the SSE `id:` field.
- On reconnect, the client sends `Last-Event-ID: <lastSeenEventId>`. The server
  replays `SELECT * FROM job_events WHERE project_id = ? AND event_id > ? ORDER BY event_id`,
  streamed before the live tail resumes.
- **Bounded backlog.** If the gap exceeds 1,000 events or 5 minutes of
  wall-clock (whichever is hit first — a client that was disconnected far
  longer than that has almost certainly missed enough state that incremental
  replay is no longer cheaper than a fresh fetch), the server does not replay
  the full backlog. Instead it emits one `resync` event
  (`{"type": "resync", "reason": "backlog_exceeded"}`) and resumes the live
  tail from "now" — the client's response to `resync` is to re-fetch the
  relevant summary/list endpoints directly rather than trust incremental
  catch-up. This bound did not exist in any source document and is added here
  because unbounded replay on a stale reconnect (e.g., a laptop waking from
  sleep after hours) could otherwise flood the client with a backlog larger
  than the state it describes.

### Heartbeats

A `: keep-alive` SSE comment every ~15 seconds, per `target-architecture.md`
§3.6 — keeps intermediate proxies/timeouts from closing an idle-but-healthy
connection, and gives the client a liveness signal distinct from "no events
because nothing happened."

### Polling fallback contract

`frontend-architecture.md`'s migration step 5 explicitly requires "the step-1
polling-with-backoff path wired but dormant... as the automatic degraded-mode
fallback" for when `EventSource` fails to construct or open (e.g., an older
Android system WebView). This document defines that fallback's server side, a
JSON-polling twin of the SSE stream that no source document specified in full:

```
GET /api/v1/projects/{projectId}/events/poll?since=84210&limit=200
```

```json
{
  "events": [ { "eventId": 84211, "type": "unit.completed", "...": "..." } ],
  "nextSince": 84231,
  "hasMore": false
}
```

Same replay/backlog-bound semantics as SSE reconnect (`since` plays the role of
`Last-Event-ID`; a backlog gap beyond the bound returns a synthetic
`{"type": "resync"}` entry instead of the full history). Recommended client
backoff schedule, chosen to mirror the orchestrator's own retry backoff shape
in `target-architecture.md` §3.7 (`base=1s, cap=30s`) for consistency across
the codebase's two backoff policies:

| Attempt | Delay |
|---|---|
| 1 | 1s |
| 2 | 2s |
| 3 | 5s |
| 4 | 10s |
| 5+ | 30s (cap) |

A successful poll that returns at least one event resets the backoff to 1s (an
active job warrants tight polling; a quiet project does not).

---

## 5. Job control

Extends the existing `GET /api/v1/jobs/{jobId}`, `POST /api/v1/jobs/{jobId}/cancel`,
and `GET /api/v1/projects/{projectId}/jobs` (all already shipped in `main.py`).

### New endpoints

```
POST /api/v1/jobs/{jobId}/pause     -> Job (RUNNING -> PAUSED)
POST /api/v1/jobs/{jobId}/resume    -> Job (PAUSED|RESUMABLE -> RUNNING)
POST /api/v1/jobs/{jobId}/retry     -> Job (re-enqueues failed units only, stays same jobId)
GET  /api/v1/jobs/{jobId}/report    -> run_report_manifest.json (target-architecture.md §8)
GET  /api/v1/jobs/{jobId}/checkpoints  -> paginated job_checkpoints rows (§2)
```

**Reconciling "pause" vs. "cancel."** The task set for this document names four
verbs (pause/resume/cancel/retry); `target-architecture.md` §3.7/§7.3 only
specifies two states that both resume the same way (`CANCELED`, described as
"fully resumable later," and `RESUMABLE`). Rather than inventing a third
engine-level state, `pause` and `cancel` share the exact same cooperative-stop
mechanism (§3.7: the cancel flag is checked between units, in-flight units
finish and checkpoint normally) and both endpoints resume via the same
`POST .../resume`. The only difference is **intent and the state value
returned**: `pause` is a short, user-initiated break the same user expects to
resume (`status: "paused"`); `cancel` is a more final stop
(`status: "canceled"`) that may never be resumed. This keeps the state machine
`target-architecture.md` already designed intact while giving the UI the two
distinct affordances it needs.

### Job detail shape (fan-out progress)

`GET /api/v1/jobs/{jobId}` response gains a `stages` array — additive, so
existing consumers reading only `id`/`status`/`progress` are unaffected:

```json
{
  "id": "job_3c8fbf0189cd4c8e",
  "projectId": "proj_853c19aa7bbb4706",
  "jobType": "structure.extract",
  "status": "running",
  "progress": { "phase": "speaker_attribution" },
  "stages": [
    { "id": "block_map", "done": 6995, "total": 6995, "failed": 0, "status": "completed" },
    { "id": "cast_discovery", "done": 601, "total": 601, "failed": 0, "status": "completed" },
    { "id": "speaker_attribution", "done": 412, "total": 971, "failed": 3, "status": "running" }
  ],
  "createdAt": "2026-07-07T10:00:00Z",
  "startedAt": "2026-07-07T10:00:02Z",
  "finishedAt": null
}
```

### Checkpoint inspection

```
GET /api/v1/jobs/{jobId}/checkpoints?cursor=&limit=200&status=failed
```

```json
{
  "items": [
    {
      "unitKey": "b1946ac9...", "stage": "speaker_attribution",
      "scope": { "chapterId": "chap_002", "sceneId": "scene_014" },
      "status": "failed", "attempt": 4,
      "lastError": "ollama connection reset", "outputRef": null,
      "updatedAt": "2026-07-07T11:58:03Z"
    }
  ],
  "pageInfo": { "nextCursor": null, "hasMore": false, "totalCount": 3 }
}
```

This is what lets a stalled or `completed_with_issues` job be diagnosed from
the UI (or a support session) without pulling a full debug bundle — a direct
answer to "why did this take so long / what exactly failed" that the current
v1 API has no path to at all.

### Error cases

| Case | Status | `error.code` |
|---|---|---|
| Pause/cancel a job already terminal | 409 | `jobs.already_terminal` |
| Resume a job that is not `PAUSED`/`RESUMABLE` | 409 | `jobs.not_resumable` |
| Retry a job with zero failed units | 200 (no-op, returns unchanged `Job`) | — |

---

## 6. New feature endpoints

### 6.1 Extraction v2

Owning doc: [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md).
That document specifies the confidence model and the "grouped review task"
aggregation policy in prose (three-tier auto-accept/audit/flag policy, tasks
grouped per-character/per-scene/per-span, budget `< 20 tasks/book`) but does
not give a wire contract — this section is that contract.

**Start extraction, with options.**

```
POST /api/v1/projects/{projectId}/extraction/start
```
```json
{
  "narrativeVoiceAnalysis": true,
  "confidenceProfile": "default",
  "votingEnabled": true,
  "stages": ["structure", "cast_discovery", "speaker_attribution", "direction"]
}
```
→ `202`, body: `Job` (`jobType: "extraction.run"`). `stages` lets a power user
re-run a subset (the "editable plan" question `target-architecture.md` §10
leaves open) — omitted, it runs the full pipeline as today's `structure.extract`
does. Error: `422 extraction.no_source_document` if no source has been
imported yet.

**Grouped review tasks — list.**

```
GET /api/v1/projects/{projectId}/review-tasks?cursor=&limit=50&status=open&kind=
```
```json
{
  "items": [
    {
      "id": "rtask_0044",
      "kind": "attribution_ambiguity",
      "scopeType": "chapter", "scopeId": "chap_012",
      "title": "Chapter 12: 4 dialogue turns are ambiguous between Reyes and Okonkwo",
      "severity": "warning",
      "memberCount": 4,
      "status": "open",
      "createdAt": "2026-07-07T10:05:00Z", "updatedAt": "2026-07-07T10:05:00Z"
    }
  ],
  "pageInfo": { "nextCursor": null, "hasMore": false, "totalCount": 6 }
}
```
This is the endpoint the confidence model's `< 20 tasks/book` budget is
designed around — see [§8](#8-changed-endpoints) for how it relates to (and
replaces) `structure-warnings`.

**Grouped review task — detail (with member evidence).**

```
GET /api/v1/review-tasks/{taskId}
```
```json
{
  "id": "rtask_0044", "kind": "attribution_ambiguity",
  "scopeType": "chapter", "scopeId": "chap_012",
  "title": "Chapter 12: 4 dialogue turns are ambiguous between Reyes and Okonkwo",
  "severity": "warning", "status": "open",
  "members": [
    {
      "memberType": "speaker_attribution", "memberId": "attr_9911",
      "segmentId": "seg_04412",
      "evidence": { "candidates": ["char_reyes", "char_okonkwo"], "voteMargin": 0.12 }
    }
  ]
}
```

**Resolve a grouped review task.**

```
POST /api/v1/review-tasks/{taskId}/resolve
```
```json
{ "action": "confirm", "memberIds": ["attr_9911"], "value": { "characterId": "char_reyes" } }
```
→ `200`, body: updated `ReviewTask` (status `resolved` once every member is
resolved, otherwise stays `open` with a reduced `memberCount`). Confirmations
**propagate to sibling rows** exactly as today's speaker-attribution PATCH
already does (unchanged mechanism, new entry point) — resolving one member of
a grouped task is not required to resolve every occurrence individually.
Error: `409 review_tasks.member_already_resolved` if a member was resolved by
a separate, more specific call (e.g. a direct `PATCH .../speaker-attributions/{id}`)
in the interim.

**Confidence threshold configuration.**

```
GET /api/v1/projects/{projectId}/extraction/confidence-config
```
```json
{
  "stages": {
    "structure_repair":     { "high": 0.92, "mid": 0.75 },
    "speaker_attribution":  { "high": 0.95, "mid": 0.80 },
    "cast_reconciliation":  { "high": 0.90, "mid": 0.70 },
    "direction":            { "high": 0.85, "mid": 0.60 }
  },
  "calibrationVersion": "2026.07-qwen3:4b",
  "source": "calibrated_default"
}
```
```
PUT /api/v1/projects/{projectId}/extraction/confidence-config
```
Same shape; `source` flips to `"user_override"` on save. Per
`extraction-pipeline-v2.md`'s calibration methodology (§"Calibration"),
lowering `mid` trades more auto-accepted (and potentially wrong) rows for fewer
review tasks — the UI should present this as an explicit trade-off, not a
free lunch. Error: `422 extraction.threshold_out_of_range` if `mid > high` or
either value is outside `[0, 1]`.

### 6.2 Casting v2

Owning doc: [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md),
which already specifies this endpoint set and its purposes in its own
"Data model & API impact" section — this section adds the request/response
JSON that doc left implicit.

**Run auto-cast.**

```
POST /api/v1/projects/{projectId}/casting/auto-run
```
```json
{ "scope": "all", "castingStylePreset": "warm_neutral" }
```
→ `202`, body: `Job` (`jobType: "casting.auto_run"`). `scope: "all" | "unlocked_only"`
— `unlocked_only` is what a rerun after a Character Bible correction uses
(locked assignments, including the narrator, are never touched either way per
the override model).

**Casting proposal (preview a rerun's diff).**

```
GET /api/v1/projects/{projectId}/casting/proposal
```
```json
{
  "proposalId": "cprop_2201",
  "generatedAt": "2026-07-07T12:00:00Z",
  "changes": [
    {
      "characterId": "char_042", "role": "character",
      "currentVoiceId": null, "proposedVoiceId": "voice_catalog_0091",
      "reason": "unassigned_character", "score": 4.82
    },
    {
      "characterId": "char_009", "role": "character",
      "currentVoiceId": "voice_catalog_0033", "proposedVoiceId": "voice_catalog_0071",
      "reason": "catalog_updated_better_match", "score": 5.10
    }
  ],
  "unchangedCount": 41
}
```

**Apply a proposal.**

```
POST /api/v1/projects/{projectId}/casting/proposal/{proposalId}/apply
```
```json
{ "characterIds": ["char_042"] }
```
→ `200`, body: `{ "applied": ["char_042"], "skipped": [] }`. Omitting
`characterIds` applies every change in the proposal. Error:
`410 casting.proposal_expired` if the catalog or cast changed since the
proposal was generated (proposals are a point-in-time snapshot, not a live
query).

**Voice catalog — list.**

```
GET /api/v1/voice-catalog?cursor=&limit=100&engine=chatterbox&gender=female&ageRange=adult
```
```json
{
  "items": [
    {
      "id": "voice_catalog_0091", "engine": "chatterbox", "engineVoiceId": "cb_f_low_03",
      "gender": "female", "ageRange": "adult", "accent": "en-GB",
      "timbre": ["warm", "low"], "energyDefault": "medium",
      "licenseSummary": "MIT", "sampleAudioUrl": "/api/v1/voice-catalog/voice_catalog_0091/sample.wav"
    }
  ],
  "pageInfo": { "nextCursor": null, "hasMore": false, "totalCount": 3 }
}
```

**Kick off a catalog audition pass** (post-install labeling, per
`tts-engine-strategy.md`'s bake-off/labeling need and
`automatic-casting-v2.md`'s migration step 1):

```
POST /api/v1/voice-catalog/audition-jobs
```
```json
{ "engine": "chatterbox" }
```
→ `202`, body: `Job` (`jobType: "voice_catalog.audition"`).

**Casting decision (superset of today's `voice-suggestions`).**

```
GET /api/v1/characters/{characterId}/casting-decision
```
```json
{
  "characterId": "char_042", "role": "character",
  "chosenVoiceId": "voice_catalog_0091", "prominenceClass": "major",
  "algorithmVersion": "1.0.0", "catalogVersion": "2026.07.01",
  "candidateScores": [
    { "voiceId": "voice_catalog_0091", "score": 4.82, "facetMatch": 3.0, "timbreMatch": 1.6, "distinctivenessPenalty": 0.0 },
    { "voiceId": "voice_catalog_0033", "score": 4.10, "facetMatch": 3.0, "timbreMatch": 1.1, "distinctivenessPenalty": 0.0 }
  ],
  "userLocked": false
}
```
The existing `GET /api/v1/characters/{characterId}/voice-suggestions`
(`main.py:1166`) stays live during the migration window (see [§10](#10-compatibility--rollout))
so the current "pick a different suggestion" UI keeps working unmodified.

**Override / lock voice (extends the existing endpoint).**

```
POST /api/v1/characters/{characterId}/assign-voice
```
```json
{ "voiceId": "voice_catalog_0091", "lockAssignment": true, "allowNarratorReuse": false }
```
Error: `422 casting.narrator_reuse_blocked` if `voiceId` is the reserved
narrator voice and `allowNarratorReuse` is not `true` — the machine-checked
form of the voice-bible's "narrator voice must never be assigned to
non-narrator characters unless explicitly approved" rule.

### 6.3 TTS v2

Owning doc: [`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md).
Unlike casting and sound design, that document specifies engine tiering,
voice-identity generation, and the direction→engine contract in detail but
does not propose endpoint shapes at all — this section designs them fresh,
following the existing `/settings/tts*` and `/local-ai/*` conventions already
shipped in `api-spec.yaml` so TTS v2 doesn't invent a third pattern.

**List engines (extends `GET /api/v1/settings/tts/providers`).**

```
GET /api/v1/tts/engines
```
```json
[
  {
    "engineId": "kokoro", "displayName": "Kokoro-82M (ONNX)", "tier": "A",
    "installState": "installed", "ready": true,
    "directionSupport": ["pace", "pauseBeforeMs", "pauseAfterMs"],
    "hardwareEligible": true
  },
  {
    "engineId": "chatterbox", "displayName": "Chatterbox", "tier": "S",
    "installState": "not_installed", "ready": false,
    "directionSupport": ["pace", "intensity", "tone", "emotion", "pauseBeforeMs", "pauseAfterMs"],
    "hardwareEligible": true
  }
]
```
`directionSupport` is only ever populated with controls the bake-off in
`tts-engine-strategy.md` §10 has actually confirmed for that engine — this
list is the wire-level enforcement of that document's "truthfulness rule"
(never advertise a control the engine cannot receive).

**Engine status (detail).**

```
GET /api/v1/tts/engines/{engineId}/status
```
```json
{
  "engineId": "chatterbox", "tier": "S", "installState": "installed",
  "ready": true, "devicePlan": "cuda", "modelVersion": "0.1.2",
  "loaded": true, "message": null
}
```

**Install an engine (reuses the Model Center job pattern).**

```
POST /api/v1/tts/engines/{engineId}/install
```
```json
{ "confirmNetworkDownload": true, "confirmThirdPartyLicense": true }
```
→ `202`, body: `Job` — identical shape to
`POST /api/v1/local-ai/models/{model_key}/install`, deliberately, since a TTS
engine install is a Model Center install (§6.5) with a TTS-specific alias path
for discoverability. Error: `422 tts.hardware_ineligible` if `hardwareEligible`
was `false` (e.g. a Tier-S GPU model requested on a CPU-only host).

**Select engine/tier for a project (extends the existing production settings endpoint).**

```
PATCH /api/v1/projects/{projectId}/production-settings
```
```json
{ "ttsTierPin": "S", "ttsEngineId": "chatterbox" }
```
Reuses `GET/PUT /api/v1/projects/{projectId}/production-settings`
(`main.py:990`) rather than adding a new settings surface — `ttsTierPin` and
`ttsEngineId` join `narratorCastingDecisionId`/`castingStylePreset`/`autoCastEnabled`
(from [§6.2](#62-casting-v2)) and `autoSoundDesignJson` (from
[§6.4](#64-sound-design-v2)) as v2 additions to the same record, all following
this project's existing "one flexible JSON-backed settings row" convention
rather than one table per feature.

**Voice synthesis — create a character voice.**

```
POST /api/v1/characters/{characterId}/voice-identity
```
```json
{ "engine": "chatterbox", "method": "embedding" }
```
→ `202`, body: `Job` (`jobType: "voice_identity.generate"`) — runs
`tts-engine-strategy.md` §6.2's collision-avoiding embedding-sampling or
seed-conditioned generation algorithm and persists a voice identity record.
On completion:

```
GET /api/v1/characters/{characterId}/voice-identity
```
```json
{
  "voiceIdentityId": "vid_7f3a2c91", "characterId": "char_042",
  "engine": "chatterbox", "engineModelVersion": "0.1.2",
  "method": "embedding", "seed": 480213,
  "profileConstraints": { "gender": "female", "ageBand": "adult", "accent": "en-GB", "timbre": "warm-low" },
  "sampleAudioUrl": "/api/v1/characters/char_042/voice-identity/sample.wav"
}
```
Error: `422 tts.collision_avoidance_exhausted` if `N` sampling attempts all
land within `D_MIN` of an existing identity — surfaced as a `casting_quality`
issue rather than silently returning a too-similar voice, matching the
distinctiveness-enforcement pattern in `automatic-casting-v2.md`.

**Regenerate acting-refs (per-character emotion clip bank).**

```
POST /api/v1/characters/{characterId}/voice-identity/acting-refs/regenerate
```
```json
{ "emotions": ["angry", "whisper"] }
```
→ `202`, body: `Job` (`jobType: "voice_identity.acting_refs_regenerate"`).
Omitting `emotions` regenerates the full bucket set
(`neutral, warm, tense, urgent, somber, fearful, angry, whisper`, per
`tts-engine-strategy.md` §5.4). Only meaningful for reference-conditioned
engines without a native emotion parameter (XTTS/F5-class); calling it for an
engine with a direct emotion vector/tag mechanism returns
`422 tts.acting_refs_not_applicable`.

### 6.4 Sound design v2

Owning doc: [`generative-sound-design.md`](../pipeline/assembly/generative-sound-design.md)
§"API additions" — reproduced here with full JSON so this is a complete
reference on its own, plus the "swap" half of "cue mute/swap" that the source
document only specified `muted` for.

**Get / regenerate a chapter's sound plan.**

```
GET /api/v1/projects/{projectId}/chapters/{chapterId}/sound-plan
```
```json
{
  "manifestType": "sound_plan_manifest", "schemaVersion": "0.1.0",
  "chapterId": "chap_014", "status": "completed",
  "renderMode": "light_cinematic",
  "plannedCues": [
    { "sceneId": "scene_0041", "kind": "ambience", "rule": "scene_ambience_bed", "bedSignature": ["tavern", "interior", "none", "night"] }
  ],
  "budgets": { "sfxUsed": 2, "sfxLimit": 2 }
}
```
```
POST /api/v1/projects/{projectId}/chapters/{chapterId}/sound-plan
```
```json
{ "scope": "chapter", "force": false }
```
→ `202`, body: `Job` (`jobType: "sound_design.plan"`). `scope: "chapter" | "scene"`
with an optional `sceneId` when scoped to one scene (the "scene or chapter
scope" the task set for this document calls for). Idempotent per
`generative-sound-design.md`: re-running with `force: false` skips scenes
whose atmosphere profile/plan is unchanged and never touches `user_locked`
cues; `force: true` re-runs regardless (still never touching locked cues).

**Cue mute / swap.**

```
PATCH /api/v1/projects/{projectId}/sound-cues/{cueId}
```
```json
{ "muted": true }
```
or, to swap the underlying asset without moving/retiming the cue:
```json
{ "assetId": "asset_0087" }
```
Both fields are optional and independent; `assetId` swap is new relative to
`generative-sound-design.md`'s source spec (which only documented `muted`) —
added here because "cue mute/swap" was explicitly in scope for this document
and a cue's timing/fade/ducking metadata is deliberately decoupled from which
asset fills it, matching the append-only-asset-history model already used for
regeneration below. Error: `409 sound.cue_locked` if the cue is `userLocked`
and the request did not also set `unlock: true` in the same call.

**Regenerate an asset with a new seed.**

```
POST /api/v1/projects/{projectId}/sound-assets/{assetId}/regenerate
```
```json
{ "seed": 991823, "prompt": "tavern interior, low murmur, distant fire crackle" }
```
→ `202`, body: `Job` (`jobType: "sound_design.regenerate_asset"`). Omitting
`prompt` reuses the asset's existing prompt with only a new seed. Produces a
**new** `AmbienceAssetRecord` row (append-only asset history, per
`generative-sound-design.md`) and repoints the cue(s) referencing the old
asset — existing renders that already mixed the old asset are untouched until
the owning chapter is reassembled.

### 6.5 Model Center v2

Owning doc: [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md)
§4–5. Extends the existing `/api/v1/local-ai/*` surface rather than replacing
it — the consent-flag pattern, job-runner-backed install flow, and
health/verification split all carry forward unchanged in spirit per that
document.

**Catalog with per-platform artifacts (changed).**

```
GET /api/v1/local-ai/catalog
```
gains an `artifacts` map per entry, keyed by `{os}-{arch}-{accelerator}`:
```json
[
  {
    "modelKey": "llama_cpp_runtime", "displayName": "llama.cpp Runtime",
    "capability": "local_llm_runtime", "installType": "bundled_runtime",
    "artifacts": {
      "windows-x64-cpu":  { "sizeMb": 40,  "sha256": "..." },
      "windows-x64-cuda": { "sizeMb": 180, "sha256": "..." },
      "macos-arm64":      { "sizeMb": 35,  "sha256": "..." },
      "linux-x64-cpu":    { "sizeMb": 45,  "sha256": "..." }
    },
    "recommendedArtifact": "windows-x64-cuda"
  }
]
```
`recommendedArtifact` is computed server-side from the `HardwareProbe` result
(`target-architecture.md` §4.3) so the client never has to replicate the
OS/arch/accelerator matching logic.

**Download progress via events (changed).** Today, install progress is only
observable by polling `GET /api/v1/local-ai/jobs/{jobId}`. v2 additionally
emits the standard job event stream ([§4](#4-event-stream-contract)) for every
model install — `job.progress` payloads carry byte-level detail
(`{bytesDownloaded, bytesTotal}`) sourced from the resumable/verified
downloader's existing progress-reporting hook
(`kokoro_setup.py`'s `PHASES`/`_progress` mechanism, generalized). The polling
endpoint is **kept**, unchanged, as the fallback path for a client not
subscribed to the event stream — this is additive, not a replacement.

**Verify (unchanged).** `POST /api/v1/local-ai/models/{model_key}/verify`
keeps its current shape exactly.

**Evict.**

```
GET /api/v1/local-ai/storage
```
```json
{ "budgetBytes": 20000000000, "usedBytes": 14200000000, "models": [
  { "modelKey": "orpheus_3b_q4", "sizeBytes": 4200000000, "lastUsedAt": "2026-06-01T00:00:00Z", "evictable": true }
]}
```
```
POST /api/v1/local-ai/storage/evict
```
```json
{ "modelKeys": ["orpheus_3b_q4"] }
```
or, to free space toward a target rather than naming models explicitly:
```json
{ "reclaimBytes": 5000000000 }
```
→ `200`, body: `{ "evicted": ["orpheus_3b_q4"], "freedBytes": 4200000000 }`.
This is distinct from the existing `DELETE /api/v1/local-ai/models/{model_key}`
(a single, user-initiated removal): `evict` is the policy-driven operation
described in `cross-platform-strategy.md` §5 ("evict least-recently-used,
unreferenced models first"), which can act on multiple models in one call and
**must** apply the same "never evict a model referenced by unrendered/unexported
render history" guard that `target-architecture.md` §4.4's `ensure_loaded`
already enforces for in-memory eviction — extended here to on-disk eviction.
Error: `409 local_ai.evict_blocked_by_render_history` per model that is still
referenced, with `details.blockingChapterIds` listing what to export/re-render
first; the call still evicts every other requested model rather than failing
atomically.

---

## 7. Job-launching endpoints and idempotency

Per [§1.4](#14-idempotency-keys-for-mutating-pipeline-operations), the
following endpoints — existing and new — accept `Idempotency-Key`:

`POST /source/import`, `POST /source/reparse`, `POST /extraction/start`,
`POST /speaker-attributions/run`, `POST /directions/infer`,
`POST /casting/auto-run`, `POST /voice-catalog/audition-jobs`,
`POST /characters/{id}/voice-identity`,
`POST /characters/{id}/voice-identity/acting-refs/regenerate`,
`POST /generate/chapters`, `POST /chapters/{id}/generate`,
`POST /segments/{id}/generate`, `POST /chapters/{id}/assemble`,
`POST /chapters/{id}/sound-plan`, `POST /sound-assets/{id}/regenerate`,
`POST /tts/engines/{id}/install`, `POST /local-ai/models/{key}/install`,
`POST /exports`.

---

## 8. Changed endpoints

| Endpoint | Change | Notes |
|---|---|---|
| `GET /api/v1/scenes/{sceneId}/segments` | Paginated ([§2](#2-pagination-standard)) | Compatibility window: until FE step 4a (`/produce/[chapterId]`) lands |
| `GET /api/v1/projects/{projectId}/chapters/{chapterId}/segments` | **New** flat, chapter-scoped, paginated alternative | Lets the review/produce routes fetch one chapter's segments without walking scene-by-scene; existing per-scene endpoint is unaffected |
| `GET /api/v1/projects/{projectId}/chapters` | Unchanged (unpaginated — bounded collection) | — |
| `GET /api/v1/projects/{projectId}/characters` | Paginated ([§2](#2-pagination-standard)) | Compatibility window: until FE step 4c (`/cast`) lands |
| `GET /api/v1/projects/{projectId}/issues` | Paginated + gains `updatedSince` filter ([§9](#9-caching--consistency)) | Compatibility window: until FE step 4d (`/review/[chapterId]`) lands |
| `GET /api/v1/projects/{projectId}/speaker-attributions` | Paginated (existing `status` filter kept) | Compatibility window: until FE step 4c |
| `GET /api/v1/projects/{projectId}/structure-warnings` | **Deprecated**, replaced by `GET /api/v1/projects/{projectId}/review-tasks` ([§6.1](#61-extraction-v2)) | Kept read-only, unpaginated, for the duration of the extraction-v2 rollout (`extraction-pipeline-v2.md` migration step 7: "retire per-segment `structure_parser_warnings` firehose in favor of aggregated issues"); removed once `review-tasks` covers 100% of what it surfaced — see the open question in [§11](#11-open-questions) on whether `review-tasks` is a new table or a grouped view over `issues` |
| `GET /api/v1/projects/{projectId}/chapters/{chapterId}/review-timeline` | **Windowed** (see below) | Compatibility window: until FE step 4d lands |
| `GET /api/v1/characters/{characterId}/voice-suggestions` | Kept, unchanged, alongside new `casting-decision` ([§6.2](#62-casting-v2)) | Not deprecated in this rollout — `automatic-casting-v2.md` explicitly wants the current "pick a suggestion" UI to keep working unmodified |
| `POST /api/v1/characters/{characterId}/assign-voice` | Extended with `lockAssignment`, `allowNarratorReuse` | Backward compatible — both optional, default `false` |
| `PATCH /api/v1/projects/{projectId}/sound-cues/{cueId}` | **New** — no PATCH exists today | Adds `muted`, `assetId` swap ([§6.4](#64-sound-design-v2)) |
| `GET/PUT /api/v1/projects/{projectId}/production-settings` | Extended with `ttsTierPin`, `ttsEngineId`, `narratorCastingDecisionId`, `castingStylePreset`, `autoCastEnabled`, `autoSoundDesignJson` | All optional/additive |
| `GET /api/v1/local-ai/catalog` | Gains `artifacts`/`recommendedArtifact` ([§6.5](#65-model-center-v2)) | Additive |
| `GET /api/v1/jobs/{jobId}` | Gains `stages[]` fan-out ([§5](#5-job-control)) | Additive |

### Windowed chapter-timeline endpoint (full spec)

Today `GET /api/v1/projects/{projectId}/chapters/{chapterId}/review-timeline`
returns the entire chapter's `waveform` array and every `segment` in one
payload (confirmed shape: `ChapterReviewTimeline` in
`libs/domain-models/src/echodraft_domain/models.py:1009`, consumed via
`apps/web/app/api.ts:166`). For a long chapter this is exactly the kind of
whole-chapter-in-one-JSON payload the UI research brief identifies as a
freeze cause.

```
GET /api/v1/projects/{projectId}/chapters/{chapterId}/review-timeline?startMs=0&endMs=120000&maxSegments=400
```

```json
{
  "projectId": "proj_853c19aa7bbb4706",
  "chapterId": "chap_014",
  "chapterTitle": "Chapter 14",
  "chapterRender": { "id": "rndr_5521", "status": "succeeded", "durationMs": 812340 },
  "windowStartMs": 0,
  "windowEndMs": 120000,
  "bucketResolutionMs": 250,
  "waveform": [0.02, 0.04, "...windowed buckets only..."],
  "segments": [
    {
      "id": "seg_04412", "sceneId": "scene_014", "sceneIndex": 3, "orderIndex": 4021,
      "text": "\"You shouldn't have come back,\" Reyes said.",
      "segmentType": "dialogue", "speaker": "Reyes", "characterId": "char_reyes",
      "startMs": 41200, "endMs": 44100, "renderId": "rndr_seg_991",
      "issueMarkers": []
    }
  ],
  "issueMarkers": [ { "atMs": 41200, "issueId": "iss_0091", "severity": "warning" } ]
}
```

- Returns only segments whose `[startMs, endMs)` overlaps the requested
  window, plus waveform buckets for that window only.
- `bucketResolutionMs` tells the client the sampling density it actually
  received (so a client that requested a huge window and got coarsened
  buckets knows not to expect sample-accurate zoom without a narrower
  re-request).
- Omitting `startMs`/`endMs`/`maxSegments` returns the full legacy payload —
  same "no params, old shape" compatibility rule as list pagination
  ([§2](#2-pagination-standard)) — until FE step 4d retires the unwindowed
  caller.
- `TranscriptListVirtual` (per `frontend-architecture.md`) requests windows
  lazily as the user scrolls, matching the virtualizer's visible range.

---

## 9. Caching / consistency

### Picking one convention

`frontend-architecture.md` proposed **both** `ETag`/`If-None-Match` and an
`updatedSince` query parameter as if they were two options for the same job.
This document resolves that into a single hierarchy rather than two competing
caching schemes, because they don't actually solve the same problem at the
same layer:

**`ETag`/`If-None-Match` is the caching/consistency convention** for every
endpoint in this document — GETs on single resources and on paginated
collections alike compute a weak ETag as `hash(count, max(updatedAt))` over the
requested filter/cursor combination. A matching `If-None-Match` returns `304
Not Modified` with no body. This is the standard HTTP mechanism, composes for
free with any intermediate cache, and works uniformly whether or not a caller
holds a live SSE connection.

**`updatedSince` is demoted to a query filter, not a caching mechanism.** It
answers a narrower question — "give me only the rows that changed" — which is
useful specifically for the SSE **polling fallback**'s degraded mode
([§4](#4-event-stream-contract)): a client stuck polling every few seconds
because `EventSource` failed to connect should not re-fetch and re-diff
thousands of unchanged rows on every tick. `updatedSince` composes with
pagination (`?updatedSince=2026-07-07T12:00:00Z&cursor=&limit=`) to bound that
payload. It is not an alternative to ETag-based revalidation; a client that
holds a valid ETag should use `If-None-Match`, not `updatedSince`, for a
plain "has this changed" check.

Every list endpoint item gains an `updatedAt` field (several already have
it — e.g. `SpeakerAttribution.updatedAt` — the rest are extended to match).

### Composing with SSE invalidation

In the common case (a live SSE connection is open), `entity.updated` events
are the **primary** invalidation signal — the client's query cache
(`TanStack Query`, per `frontend-architecture.md`) evicts/refetches the exact
entity named in the event, with no polling and no ETag round-trip needed at
all. ETag/`If-None-Match` is the **fallback validator**, consulted only:

1. On initial page load (no event history to have invalidated anything yet).
2. On cold reconnect after a `resync` event ([§4](#4-event-stream-contract)) —
   the client doesn't know what it missed, so it revalidates via ETag instead
   of trusting stale cache data.
3. For any caller with no live SSE connection at all (a script, a health
   check, or a client that has fallen back to polling).

```
live SSE:        entity.updated ──► cache evicted ──► refetch (ETag irrelevant, data already known stale)
cold load/resync: GET + If-None-Match ──► 304 (cache still valid) or 200 + fresh body
degraded polling: GET ?updatedSince=<last poll ts> ──► small delta ──► merge into cache
```

---

## 10. Compatibility & rollout

Ordered to match [`frontend-architecture.md`](../ui/frontend-architecture.md)'s
own Incremental Migration Plan step-for-step, so no backend phase ships ahead
of a frontend consumer that needs it, and no frontend step is blocked waiting
on backend work it didn't actually need yet.

| Phase | Backend ships | Paired frontend step | What the current UI keeps using meanwhile |
|---|---|---|---|
| **0** | Error envelope (§1.2), auth token plumbing (§1.3, packaging-gated so it's a no-op in dev), idempotency keys (§1.4) | — (no FE dependency; purely additive) | Existing `{"detail": ...}` parsing keeps working since the envelope change is additive at the transport layer until FE explicitly reads `error.code` |
| **1** | `GET /jobs/{jobId}` gains `stages[]` (§5) | FE step 1 (TanStack Query polling) | The two fixed-interval `setTimeout` loops keep polling the unchanged `status`/`progress` fields; `stages[]` is simply unread until step 4 |
| **2** | Cursor pagination for segments/characters/structure-warnings→review-tasks/issues/speaker-attributions (§2); windowed `review-timeline` (§8) — all behind the "no params = legacy array" rule | FE steps 2–3 (memoize, virtualize in place) | Virtualization can start against the full in-memory array immediately (§3 of that doc's plan already says this explicitly); paginated fetching is adopted once each route is extracted in step 4 |
| **3** | Summary endpoints (§3); casting v2 (§6.2); sound design v2 (§6.4); extraction v2 review-tasks + confidence-config (§6.1); TTS v2 engine list/select (§6.3, install can lag) | FE step 4a–4e (route-by-route extraction) | Each route flips its default pagination/window params and adopts the matching new feature endpoints exactly when *that* route is extracted — `/produce` (4a) needs windowed timeline + job control; `/cast` (4c) needs casting v2; `/review` (4d) needs windowed review-timeline + ETag; not-yet-extracted routes keep calling the legacy shapes served by the same endpoints |
| **4** | `GET /projects/{id}/events` SSE + polling-fallback twin (§4) | FE step 5 (SSE wiring) | Polling-with-backoff stays wired and live until this phase ships, then goes dormant (`enabled: !connected`) per that plan |
| **5** | Remove legacy unpaginated array defaults; remove `structure-warnings` once nothing reads it | FE step 6 (retire the God component) | By this point every consumer has been migrated in step 4, so removal is safe |
| **6** | Model Center v2 (§6.5); mandatory auth token enforcement toggle flipped on for packaged builds | FE step 7 (design-system pass) + cross-platform packaging milestone | Dev (`uv run`) usage is unaffected — enforcement only flips for the packaged `echodraft_api.server` entrypoint |

This mapping is also the answer to `frontend-architecture.md`'s own flagged
risk ("Cursor pagination is real backend migration work... needs a shared
owner before implementation starts on either side.") — Phase 2 above is that
shared plan.

---

## 11. Open questions

- **SSE token-in-URL.** `?token=` on the events endpoint (§1.3) is a real
  compromise — URLs land in server access logs and browser history more
  readily than headers. Worth revisiting if a future platform target's WebView
  supports `EventSource` with custom headers, or if the SSE client moves to
  `fetch` + `ReadableStream` (which `frontend-architecture.md` already flags as
  a possible fallback for exactly this reason).
- **`review-tasks` vs. `issues`: one table or two?** This document specifies
  `review-tasks` ([§6.1](#61-extraction-v2)) as a distinct list+resolve surface
  from the existing durable `issues` queue, because `extraction-pipeline-v2.md`
  describes them as a *grouping* over what would otherwise be individual flags.
  Whether that grouping is implemented as its own table or as a query/view over
  `issues` with a `groupKey` is an `extraction-pipeline-v2.md` data-model
  decision this document doesn't resolve — but the two-endpoint-families
  surface above is a real API-design risk if the underlying model turns out to
  be one table wearing two API shapes.
- **Pause vs. cancel — one verb?** §5's reconciliation makes `pause` and
  `cancel` mechanically identical, differing only in the returned status value.
  If that distinction proves not to matter to users in practice, collapsing to
  one verb (`cancel`, always resumable) would simplify the job-control surface.
- **Idempotency-key storage growth.** The `idempotency_keys` table (§1.4) has a
  24h TTL but no garbage-collection mechanism specified — needs a cheap sweep
  (e.g. piggybacked on the existing job-cleanup path) before it ships.
- **Model eviction races with in-flight jobs.** §6.5's `evict` endpoint returns
  `409` per-model when render history references it, but does not yet specify
  behavior if a job starts consuming a model in the moment between the
  eviction check and the actual delete — needs the same in-flight guard
  `target-architecture.md` §4.4 already applies to in-memory `unload()`,
  extended to the on-disk path.
- **`openapi-typescript` follow-up.** `frontend-architecture.md` suggests
  generating `apps/web/app/lib/api-types.ts` from `api-spec.yaml` once the
  pagination/summary shapes land. This document is the seed for that future
  `api-spec.yaml` update, but does not assign an owner for keeping the OpenAPI
  spec in sync with this markdown afterward — recommend folding accepted
  shapes into `api-spec.yaml` incrementally, per rollout phase (§10), rather
  than as one big-bang spec rewrite at the end.
- **Should the engine ever expose the extraction/casting DAG as an editable
  plan to the UI**, beyond the coarse `stages` opt-out already added to
  `POST /extraction/start` (§6.1)? `target-architecture.md` §10 leaves this
  open; this document only takes the smallest step needed (stage selection),
  not a full plan-editing surface.
