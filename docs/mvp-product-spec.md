# MVP Product Spec

See also: [project-overview.md](project-overview.md), [architecture.md](architecture.md), [qa-rulebook.md](qa-rulebook.md), [api-spec.yaml](api-spec.yaml)

## Product goal
Ship a usable local-first MVP that transforms a manuscript into a premium draft audiobook with:
- one stable narrator voice,
- distinct character voices for important speakers,
- basic direction controls,
- optional light ambience,
- chaptered export,
- selective patching instead of chapter-wide rerenders.

## Supported inputs and outputs
### Inputs
- TXT
- Markdown
- DOCX
- EPUB
- pronunciation dictionaries
- user voice assignments
- editorial overrides

### Outputs
- chaptered WAV
- chaptered MP3
- M4B package
- speech and ambience stems where applicable
- project-local manifests and render artifacts

## Core user stories
### Ingestion
- Import a manuscript without manual reformatting.
- Detect chapters automatically and allow correction.
- Preserve text with paragraph-level fidelity.

### Structuring
- Split a chapter into scenes and segments that are editable.
- Surface parser warnings such as malformed text or uncertain structure.
- Keep speaker attribution uncertainty visible rather than hidden.

### Casting
- Assign one stable narrator voice to the title.
- Assign distinct voices to major characters.
- Merge, split, and rename detected characters.
- Persist voice assignments and pronunciation rules across sessions.

### Direction
- Mark scenes with mood and pacing defaults.
- Override individual segments for urgency, pauses, emphasis, whispering, or similar delivery choices.
- Keep expressive direction within restrained audiobook norms.

### Generation
- Generate audio at segment level.
- Reuse cached renders when config and text are unchanged.
- Regenerate only the affected segment when quality is poor.

### Review
- Preview a line, scene, or chapter.
- Track QA issues and comments against chapter and segment anchors.
- Mark a segment or chapter reviewed once acceptable.

### Export
- Export sample chapters or a full project package.
- Attach title and author metadata.
- Block export if rights declaration is missing or blocking issues remain.

## Core user flow
1. Create project and acknowledge rights status.
2. Import manuscript source.
3. Normalize text and detect chapters.
4. Structure chapters into scenes and segments.
5. Build character registry and review uncertain speaker attribution.
6. Assign narrator and character voice profiles.
7. Set pronunciation rules and direction defaults.
8. Generate segment audio and assemble chapter output.
9. Review issues, patch weak segments, and reassemble affected chapters.
10. Export chaptered audiobook artifacts.

## Major screens
### Project dashboard
- project summary
- rights declaration state
- source import status
- chapter status list
- generation progress
- export actions

### Manuscript parser
- source preview
- chapter boundary editor
- scene and dialogue detection review
- parser warnings panel

### Cast and voice bible
- narrator card
- character cards
- voice preview controls
- pronunciation editor
- consistency notes

### Scene director
- scene list
- mood tags
- pace and intensity settings
- ambience profile suggestion
- explicit no-ambience lock

### Chapter audio editor
- transcript and segment list
- waveform or timeline view
- active render state
- regenerate segment action
- issue list and comments
- speech/ambience balance controls

### Export screen
- format selection
- metadata form
- loudness normalization toggle
- chapter scope selection
- export history

## Production modes
### Clean narration
- narrator-forward output
- minimal character variation
- no ambience by default

### Multi-voice narrative
- narrator plus assigned character voices
- dialogue differentiation is prioritized
- ambience remains off unless enabled

### Light cinematic
- same voice structure as multi-voice mode
- optional ambience bed and restrained transition design
- speech clarity remains dominant over production texture

## Acceptance requirements
### Functional
- Import valid manuscripts up to novel scale.
- Structure at least one full manuscript into browseable chapters/scenes/segments.
- Support at least 20 mapped characters in one project.
- Regenerate a single line without rewriting adjacent history.
- Export a chaptered audiobook draft.

### Non-functional
- Local-first execution on Apple Silicon.
- Clear progress and status for long-running jobs.
- Crash or retry behavior must not destroy prior valid renders.
- Artifacts remain recoverable from manifests and persisted state.
- No silent cloud upload in MVP.

## Success criteria
- Users reliably identify major characters.
- Narration stays stable across a chapter.
- Technical defects are rare and patchable.
- Ambience remains subtle and non-distracting.
- Listeners prefer the result over generic single-voice TTS.

## MVP exit criteria
The MVP is ready when:
- a novella or novel can be imported,
- at least one full chapter can be generated with narrator plus character voices,
- problem lines can be selectively regenerated,
- a chaptered draft can be exported,
- early users consistently report higher immersion than generic TTS.
