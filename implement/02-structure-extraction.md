# Stage 02 — Structure extraction

## Outcome

Turn canonical manuscript text into editable chapters, scenes, and renderable segments.

## Implement

- Define durable entities for `Chapter`, `Scene`, and `Segment`, including order, source offsets, normalized text, revision number, status, and parent IDs.
- Implement deterministic chapter detection using headings, EPUB navigation metadata, and fallback heuristics. Preserve an `unresolved` result when confidence is too low.
- Implement scene segmentation using chapter boundaries, whitespace, scene-break markers, and configurable heuristics. Do not infer scene boundaries silently when confidence is low.
- Split scenes into TTS-sized segments that preserve speaker turns and sentence boundaries. Record original and normalized character offsets.
- Write `manifests/structure_manifest.json` containing the parser configuration, detected hierarchy, confidence values, and source ranges.
- Persist hierarchy records in SQLite and expose list/detail APIs for chapters, scenes, and segments.
- Build a viewer that navigates project → chapter → scene → segment, shows source text, and allows safe text edits with revision history.
- Add an initial character-candidate extractor that flags likely speakers and confidence without automatically assigning voices.

## Validation

- Test chapter, scene, and segment extraction on prose, dialogue-heavy text, headings-only text, and malformed/OCR text.
- Test edit operations preserve parent ordering and invalidate only downstream derived artifacts.
- Test segment length limits and guarantee that no segment begins or ends mid-sentence unless explicitly overridden.

## Done when

An imported manuscript is browseable as chapters, scenes, and segments; users can correct structure without reimporting; and the hierarchy is persisted in both database records and a manifest.
