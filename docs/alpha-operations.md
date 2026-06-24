# Alpha Operations

## Recovery

- Jobs interrupted by an application restart are marked failed; restart the workflow from its persisted source, render, or chapter artifact.
- Validation errors require correcting the request. Filesystem errors require checking local disk capacity and permissions.
- Do not include manuscript text or generated audio in bug reports unless the tester explicitly consents.

## Triage

Use `blocking` for an inability to import, render, assemble, patch, or export. Include reproduction steps, job ID, app version, and the redacted error message.

## Known Limits

- In-process jobs cannot resume mid-operation.
- MP3 and M4B exports require a future local media adapter.
- Ambience asset mixing remains intentionally deferred; speech-only output is the stable alpha path.
