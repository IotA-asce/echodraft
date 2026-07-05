# TTS Production Upgrade

Stage 9 formalizes local TTS providers behind a single provider contract.

## Providers

- `mock`: built-in silent WAV provider for workflow validation.
- `kokoro`: managed ONNX setup or custom adapter. Kokoro remains the default real local voice path.
- `piper`: local CLI fallback. It requires a Piper executable and local `.onnx` model; optional config and voice registry paths can be supplied.
- `xtts_v2`: local Coqui XTTS-v2 adapter. It is opt-in and fails closed unless a local reference WAV path and explicit reference-voice consent are configured.

No provider silently falls back to cloud execution or another provider.

## Direction Capability Matrix

`capabilities.direction` on `GET /api/v1/settings/tts/providers` is **truthful**: it
lists only the controls the system actually honors for that engine — never a control
the engine cannot receive. Pace is transmitted engine-native where a real CLI/API hook
exists; the per-segment pause spacing (`pauseBeforeMs`/`pauseAfterMs`) is honored
engine-independently by chapter assembly (see
[`current-pipeline-behavior.md`](../../architecture/current-pipeline-behavior.md)), so
every real provider that reaches assembly declares the pause controls.

| Provider | Honored direction | How |
| --- | --- | --- |
| `kokoro` managed ONNX | `pace`, `pauseBeforeMs`, `pauseAfterMs` | wrapper `--speed {pace:.3f}`; pauses at assembly |
| `piper` local CLI | `pace`, `pauseAfterMs`, `pauseBeforeMs` | `--length-scale` + `--sentence-silence`; pauses at assembly |
| `kokoro` custom adapter | `pauseBeforeMs`, `pauseAfterMs` | no CLI contract to transmit pace; pauses at assembly only |
| `xtts_v2` | `pauseBeforeMs`, `pauseAfterMs` | `tts_to_file` exposes no style/pace hook; pauses at assembly only |
| `mock` | full set | test double, honors everything nominally |

The custom Kokoro and XTTS-v2 adapters previously advertised `pace`/`stylePrompt` and
echoed them in `effectiveDirection` despite having no way to send them; both now report an
empty engine-native `effectiveDirection` and only claim the pauses assembly applies. The
managed Kokoro wrapper self-heals on render: an older on-disk wrapper that hardcoded
`speed=1.0` is rewritten to the current source so pace transmission works without a manual
repair.

## Resident Managed Kokoro Worker

Managed Kokoro ONNX can run through a resident app-local worker. The worker starts lazily
on the first managed Kokoro preview or segment render, loads the Kokoro model once, and
accepts newline-delimited JSON synthesis requests from the API process. Requests remain
serialized inside the worker manager so local model access is predictable, and provider
settings changes or API shutdown stop the resident process.

The one-shot subprocess path remains available for setup validation, direct adapter use,
custom Kokoro adapters, Piper, XTTS-v2, and tests. Render fingerprints still use provider
and model identity, not worker mode, so enabling the resident worker does not make existing
audio stale by itself. Render metadata records `tts.workerMode` as `resident` or
`subprocess` for traceability.

Runtime status is exposed at `GET /api/v1/settings/tts/worker`. The response reports the
active provider/setup mode, worker mode, state, process id when running, request count, and
last worker error.

## Render Freshness

Segment render fingerprints now include:

- canonical segment text and revision;
- synthesis text after pronunciation replacement;
- resolved voice profile and provider voice ID;
- resolved direction;
- active TTS provider identity and model version;
- applied pronunciation entries.

Changing a pronunciation entry, active provider, model path, direction, voice assignment, or segment text stales only affected segment renders.

## Queue And Compare

Chapter production creates `render_queue_items` rows for each segment. Rows move through `queued`, `running`, `succeeded`, or `failed` and store metadata references only.

The render compare endpoint reports the latest segment render, its parent render, and changed request fields. This supports local review without rewriting render history.

## Reference Voices

XTTS-v2 reference voices are treated as local user-provided assets. Users must set `referenceVoiceConsent` before Echodraft will attempt synthesis. The relational database stores configuration metadata only; reference audio remains a filesystem path.
