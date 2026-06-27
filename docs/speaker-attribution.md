# Speaker Attribution

Speaker attribution turns parser speaker candidates into reviewable, production-aware cast decisions.

## Flow

1. Structure extraction creates segment-level speaker candidates when deterministic rules find patterns such as `Name:` or `Name said`.
2. Cast Review runs `POST /api/v1/projects/{projectId}/speaker-attributions/run`.
3. Echodraft writes one `speaker_attributions` row per segment.
4. Rows with matched characters and sufficient confidence are approved automatically.
5. Unmatched or low-confidence dialogue remains `needs_review`.
6. Reviewers can assign a character, approve narrator delivery, or lock the row.

## Local LLM Fallback

The run endpoint accepts `useLocalLlm=true`. When enabled, unresolved rows are sent to the local Ollama-backed LLM service with a schema-constrained prompt. Failures fail closed; there is no cloud fallback.

## Production Voice Resolution

Chapter production resolves voices in this order:

1. segment-level voice override
2. approved speaker attribution with a linked character voice
3. project narrator voice

This means character voice assignment changes can make affected segment renders stale because the render request fingerprint includes the resolved voice profile.

## Review Safety

- `userLocked` rows are not overwritten by reruns.
- Unknown dialogue stays visible until approved or assigned.
- Evidence stores the source rule, parser candidate, segment type, and text preview.
