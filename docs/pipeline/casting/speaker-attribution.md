# Speaker Attribution

Speaker attribution turns parser speaker candidates into reviewable, production-aware cast decisions.

## Flow

1. Structure extraction creates segment-level speaker candidates when deterministic rules find patterns such as `Name:` or `Name said`.
2. Structure extraction automatically runs Cast Discovery after refined segments are saved.
3. Cast Discovery creates high-confidence unique Character Bible records and leaves ambiguous candidates as review issues.
4. Speaker attribution then writes one `speaker_attributions` row per segment.
5. Rows with matched characters and sufficient confidence are approved automatically.
6. Unmatched or low-confidence dialogue remains `needs_review`.
7. Unlabeled quote segments can receive nearby-turn, speech-action, pronoun-coreference, two-speaker active-roster exchange, or two-speaker alternation hints; inferred rows remain `needs_review` until confirmed.
8. Reviewers can assign a character, approve narrator delivery, or lock the row.
9. A confirmed same-speaker assignment propagates to unresolved sibling rows with the same normalized speaker name when the chosen character matches that speaker name or alias.
10. If a high-confidence parser speaker label has no Character Bible match, speaker attribution asks Cast Discovery to propose the missing cast record using the same duplicate and confidence gates as normal cast discovery.

The manual Cast Review action can be rerun from the dashboard or by calling `POST /api/v1/projects/{projectId}/speaker-attributions/run`.

## Local LLM Fallback

The run endpoint accepts `useLocalLlm=true`. When enabled, unresolved rows are sent to the local Ollama-backed LLM service inside bounded contiguous same-scene windows with a schema-constrained prompt. Prompt rows are marked as `TARGET` or `CONTEXT`: the model may use context lines as evidence, but only target segment IDs are accepted back into attribution rows. Each window also includes an `Active speakers in this scene:` roster derived from confident same-scene dialogue labels. Up to five approved, user-locked speaker rows from the same project are included as reviewer-confirmed examples so corrections compound inside the book. Failures keep deterministic review rows and create a local review issue; there is no cloud fallback.

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
- Nearby-turn rows record `reason = "nearby_dialogue_turn"` plus previous/next speaker and pronoun cue evidence.
- Speech-action rows record `reason = "speech_action_cue"` and identify the current or adjacent action-beat cue.
- Pronoun-coreference rows record `reason = "pronoun_coreference"` when exactly one active same-scene speaker has the matching `gender:*` trait.
- Interruption-exchange rows record `reason = "interruption_exchange"`, the `interruptedSpeaker`, and the two-speaker `activeSpeakers` roster when the previous same-scene dialogue line trails off or is cut off.
- Vocative-exchange rows record `reason = "vocative_exchange"`, the `addressedSpeaker`, and the two-speaker `activeSpeakers` roster when a quoted line begins by addressing the other active speaker by name or alias.
- Two-speaker alternation rows record `reason = "turn_taking_alternation"` with prior, previous, and next speaker evidence.
- Cast-back proposals record `castProposal = "proposed_cast_from_speaker_attribution"` on the attribution evidence.
- Propagated rows record `evidence.method = "propagated_from_confirmation"` and the source attribution id.
- LLM rows record `sceneWindowSegmentIds`, `targetSegmentIds`, and `activeSpeakers`; context-only segment IDs returned by the model are ignored.
