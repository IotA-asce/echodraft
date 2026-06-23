# Stage 07 — Review and selective patching

## Outcome

Make audio defects visible, reviewable, and fixable without regenerating an entire chapter.

## Implement

- Add `Issue` and `Comment` models with project/chapter/segment scope, category, severity, status, author, timestamps, and links to affected renders.
- Implement automated QA checks for missing audio, unreadable/corrupt files, clipping, excessive silence, very short duration, truncation heuristics, and mismatch between source text and render request.
- Run QA after segment generation and chapter assembly. Store results as durable issue records, not log-only messages.
- Add APIs and UI actions to create/comment on issues, resolve/reopen them, mark segments and chapters reviewed, and filter review queues.
- Implement a selective patch flow: choose a segment, modify text/speaker/direction/pronunciation, create a new segment revision or render, run QA, then reassemble only the affected chapter.
- Preserve links between an issue, attempted patch, old render, new render, and resulting chapter render.
- Surface blocking conditions before export: unresolved critical issues, missing active renders, and stale chapter assembly.

## Validation

- Test every QA rule with controlled audio fixtures and ensure expected issues are created exactly once per render revision.
- Test review state transitions and authorization assumptions for local single-user use.
- Confirm a user can identify a bad line, regenerate only that line, reassemble the chapter, and retain the complete before/after history.

## Done when

The user has a practical review queue and can repair a single defective segment without losing history or regenerating unrelated audio.
