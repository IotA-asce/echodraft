# Stage 10 — Alpha hardening

## Outcome

Make the local-first MVP reliable enough for external alpha testers to complete the core workflow without engineering intervention.

## Implement

- Add resumable job execution. On startup, reconcile persisted jobs and artifacts, identify safely resumable work, and clearly mark irrecoverable jobs.
- Classify errors as validation, parser, adapter, media-tool, filesystem, cancellation, or unexpected failures. Provide user-facing recovery guidance for each class.
- Improve structured logs and create a privacy-conscious debug bundle containing redacted configuration, logs, job history, manifests, environment diagnostics, and optional sample metadata—but never manuscript text or generated audio unless explicitly included.
- Build an end-to-end sample-book test matrix covering TXT/DOCX/EPUB, dialogue density, malformed source, long chapters, unknown speakers, failed TTS, stale renders, and export failures.
- Add performance instrumentation for import, extraction, preview, segment render, chapter assembly, and export latency.
- Run accessibility and usability review for keyboard navigation, progress status, error states, audio controls, and destructive-action confirmations.
- Create an alpha triage process: reproducible issue template, severity definitions, known-limitations list, telemetry policy, and prioritized stabilization backlog.
- Freeze scope: do not add new product capabilities during hardening; fix reliability, recoverability, and workflow blockers.

## Validation

- Run the full sample-book matrix on a clean local environment.
- Simulate process interruption during import, generation, assembly, and export; verify recoverable jobs resume or fail safely.
- Have external testers complete import → structure → casting → segment render → chapter assembly → patch → export without direct engineering support.

## Done when

External alpha users can complete the core workflow reliably, failures are diagnosable and recoverable, and the remaining issues are documented and prioritized.
