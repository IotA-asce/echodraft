# Direction Studio

Direction Studio stores delivery controls per segment without changing canonical manuscript text.

## Controls

- controlled emotion: `neutral`, `warm`, `tense`, `quiet`, `urgent`, `somber`, `bright`, `fearful`, `angry`
- pace from `0.5` to `2.0`
- intensity from `0.0` to `1.0`
- pause before and after in milliseconds
- emphasis and whisper flags
- optional style prompt

## Inference

`POST /api/v1/projects/{projectId}/directions/infer` runs deterministic local inference across project segments by default. It uses text cues such as exclamation marks, questions, whisper words, and somber terms. Locked rows are preserved.

The endpoint also accepts an optional local-LLM payload:

```json
{ "useLocalLlm": true, "model": "qwen3:4b" }
```

When `useLocalLlm=true`, Echodraft first writes the deterministic fallback for unlocked rows, then sends bounded same-scene windows to the local Ollama extractor. The prompt marks `TARGET` and `CONTEXT` segments, includes segment type, parser speaker candidates, approved speaker attribution when available, nearby scene context, and the existing deterministic direction as a hint. Only returned rows for target segment IDs are applied; invalid, missing, or context-only results leave the deterministic row in place. Local LLM failures create a warning review issue and do not block the job.

LLM-applied rows use `source="llm_inferred"`, stay unlocked, and store review evidence on the segment direction row: reason, `llmRunId`, model, confidence, scene-window segment IDs, target segment IDs, speaker name, text preview, and the LLM evidence note.

## Production Resolution

Direction resolution follows this order:

1. legacy segment production override direction
2. Segment Direction record
3. project default direction
4. neutral segment default

The resolved direction payload is part of the segment render fingerprint, so changing a segment direction marks only affected segment renders stale.

## Engine Capability And What Is Actually Honored

Not every engine can honor every control, and Echodraft never pretends otherwise.
Each provider advertises a truthful `capabilities.direction` list (full matrix in
[`tts-production-upgrade.md`](../tts/tts-production-upgrade.md)):

- `pace` reaches managed Kokoro (wrapper `--speed`) and Piper (`--length-scale`). The
  custom Kokoro and XTTS-v2 adapters have no CLI/API hook for it, so they do not claim it.
- `pauseBeforeMs`/`pauseAfterMs` are honored engine-independently by chapter assembly, which
  inserts `max(prev.pauseAfterMs, next.pauseBeforeMs, default_gap)` of silence between
  consecutive segments (default gap 350 ms within a scene, 800 ms across a scene boundary),
  clamped to the 0–5000 ms bounds. Every real provider therefore honors the pause controls.
- Controls no engine transmits (`intensity`, `emotion`, `tone`, `emphasis`, `whisper`,
  `stylePrompt`) are stored and surfaced in render metadata as `unsupportedDirection`.

The Direction Studio UI annotates any control the active engine does not honor with a
"not honored by current engine" hint rather than disabling it, because a render can switch
engine later.

## API

- `GET /api/v1/projects/{projectId}/segment-directions`
- `GET /api/v1/projects/{projectId}/segments/{segmentId}/direction`
- `PUT /api/v1/projects/{projectId}/segments/{segmentId}/direction`
- `POST /api/v1/projects/{projectId}/directions/infer`
