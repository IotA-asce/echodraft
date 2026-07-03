# AI Audiobook Studio — Product Requirements Documents

This document contains two PRDs for the same product vision:
1. **PRD A — MVP**: a local-first, creator-operated system that converts a book or manuscript into a premium multi-voice audiobook draft.
2. **PRD B — Final Product**: a full production platform for authors, indie publishers, studios, and enterprise publishing teams.

---

# PRD A — MVP

## 1. Product Name
**AI Audiobook Studio (MVP)**

## 2. Product Summary
A local-first desktop/web application that transforms book text into a high-production audiobook draft using:
- a dedicated narrator voice,
- multiple character voices,
- basic performance direction,
- light ambience/SFX,
- chaptered export,
- human-in-the-loop editing.

The MVP is designed for **single-machine execution on Apple Silicon (Mac mini / MacBook / Mac Studio)** and is intended for:
- authors producing audio versions of their own books,
- creators working with public-domain content,
- internal prototyping for publishing workflows,
- audio-first enthusiasts who want richer narration than single-voice audiobooks.

## 3. Vision
Reading a book aloud is not the same as adapting it into an immersive listening experience. The product should bridge the gap between:
- plain TTS,
- single-narrator audiobooks,
- fully dramatized audio productions.

The MVP should deliver a **"premium draft"**: good enough to feel cinematic and emotionally differentiated, while still allowing a human producer to refine the final result.

## 4. Problem Statement
Many audiobooks are produced with a single narrator, which can feel dry or insufficiently differentiated across characters. Current TTS tools can generate speech, but they usually fail at:
- consistent character casting,
- emotional scene-aware delivery,
- handling dialogue and narration separately,
- tasteful use of ambience and SFX,
- preserving continuity over long-form books,
- giving producers controllable edit points.

Users need a system that can **convert long-form text into a coherent, editable, multi-voice audio production** without requiring a full studio or expensive voice cast.

## 5. Why Now
- High-quality open TTS models are now small and capable enough for serious experimentation.
- Apple Silicon makes local AI audio workflows more practical for solo builders.
- Independent authors and creators increasingly want audio formats without full studio costs.
- Existing TTS products optimize for short clips, voice assistants, or generic narration—not long-form, chaptered storytelling.

## 6. Target Users
### Primary Users
1. **Indie authors**
   - Have manuscript rights.
   - Want fast audiobook creation.
   - Need a better output than generic TTS.

2. **Creative producers / solo makers**
   - Experiment with public-domain books or original fiction.
   - Care about mood, voice separation, and production feel.

3. **Small publishing teams**
   - Need a first-pass audio production workflow.
   - Want to reduce cost before final studio polish.

### Secondary Users
1. Fan-fiction / private hobby users (non-commercial only if rights are unclear).
2. Educators creating dramatic readings of licensed/public-domain material.
3. Accessibility-minded creators producing differentiated audio versions.

## 7. Jobs To Be Done
### Functional Jobs
- Turn a book into chaptered audio.
- Assign distinct voices to narrator and characters.
- Make dialogue sound like performance, not just speech.
- Add subtle ambience and SFX where appropriate.
- Export a listenable audiobook draft quickly.

### Emotional Jobs
- Feel that the story is “alive.”
- Avoid the disappointment of flat single-narrator delivery.
- Feel in creative control without doing full manual sound design.

### Social Jobs
- Share a polished audiobook sample with readers, publishers, or collaborators.
- Demonstrate a concept quickly for pitching or validation.

## 8. Product Principles
1. **Human-directed, AI-accelerated** — AI drafts; humans retain control.
2. **Taste over gimmicks** — restraint in music and SFX.
3. **Consistency matters more than raw novelty** — stable voices over flashy variability.
4. **Editability is mandatory** — every generation should remain revisable.
5. **Rights-first design** — only authorized content should be used commercially.
6. **Long-form native** — chapter, scene, and speaker continuity are first-class concerns.

## 9. Scope
### In Scope (MVP)
- Text/EPUB/DOCX ingestion.
- Chapter segmentation.
- Scene/dialogue parsing.
- Speaker attribution assistance.
- Voice casting for narrator + major characters.
- Emotion/style presets per line or scene.
- Batch TTS generation.
- Basic ambience/SFX recommendation.
- Timeline-like editor for chapter review.
- Export to WAV/MP3/M4B package.
- Project save/load.
- Local execution on Apple Silicon.

### Out of Scope (MVP)
- Fully autonomous, zero-edit final production.
- Marketplace of licensed celebrity voices.
- Collaborative cloud editing.
- Real-time co-listening/review.
- Automatic soundtrack composition.
- Publisher rights management suite.
- Mobile apps.
- Multi-tenant SaaS billing.

## 10. Success Definition
The MVP is successful if a solo creator can:
1. Import a book/manuscript.
2. Generate a coherent multi-voice chapter draft.
3. Review and patch only problem lines.
4. Export a polished audio sample or full audiobook draft.
5. Prefer the output over standard single-voice TTS.

## 11. User Stories
### Ingestion
- As an author, I want to upload my manuscript as EPUB/DOCX/TXT so that I can start without reformatting.
- As a producer, I want the app to detect chapters automatically so that I do not need to split the book manually.

### Casting
- As a producer, I want to assign a unique voice to each major character so that dialogue is clearly differentiated.
- As a creator, I want to keep one stable narrator voice across the whole book.

### Direction
- As a user, I want to mark a scene as tense, intimate, comedic, or reflective so the delivery changes appropriately.
- As a user, I want per-line overrides for pacing, intensity, whispering, and emphasis.

### Production
- As a user, I want optional ambience and SFX suggestions so scenes feel richer without hand-designing every moment.
- As a user, I want separate stems for speech and ambience so I can rebalance them.

### Review
- As a user, I want to preview a single line, paragraph, scene, or full chapter.
- As a user, I want to regenerate only the bad line instead of the entire chapter.
- As a user, I want pronunciation overrides for names and invented terms.

### Export
- As a user, I want chapter-based export so I can distribute or review chapter by chapter.
- As a user, I want an audiobook package with metadata and cover art placeholder support.

## 12. Core User Flow
1. Create project.
2. Import manuscript.
3. System parses chapters and scenes.
4. System detects possible speakers and builds character list.
5. User reviews character list and assigns voices.
6. User picks narrator voice and default style.
7. User chooses production intensity preset:
   - Clean narration only
   - Multi-voice narration
   - Light cinematic
8. System generates chapter draft.
9. User reviews chapter timeline and fixes errors.
10. User exports sample or full project.

## 13. Key Screens
### 13.1 Project Dashboard
- Project name
- Rights declaration checkbox
- Input file summary
- Generation progress
- Chapter status table
- Voice cast panel
- Export actions

### 13.2 Manuscript Parser Screen
- Input preview
- Chapter boundaries
- Scene boundaries
- Detected dialogue blocks
- Warnings: unknown speaker, malformed text, OCR-like noise

### 13.3 Cast & Voice Bible Screen
- Character cards
- Narrator card
- Voice preview button
- Voice style descriptors
- Age/gender/accent notes
- Consistency rules
- Pronunciation dictionary

### 13.4 Scene Director Screen
- Scene list
- Mood tags
- Pace slider
- Intensity preset
- Ambient profile suggestions
- “No SFX” lock

### 13.5 Chapter Audio Editor
- Waveform/timeline
- Transcript alignment
- Segment boundaries
- Regenerate segment button
- Version history per segment
- Stem gain controls
- Mute ambience/music toggle

### 13.6 Export Screen
- Output format
- Sample rate / bitrate
- Chapter splitting options
- Metadata fields
- Loudness normalization toggle
- Test export / final export

## 14. Functional Requirements

### 14.1 Ingestion & Parsing
- Support TXT, Markdown, DOCX, EPUB.
- Extract chapter headings.
- Detect dialogue spans.
- Detect paragraph breaks and scene transitions.
- Build a canonical internal script structure.
- Allow manual corrections for parser output.

**Acceptance Criteria**
- User can import a valid manuscript under 250k words.
- Chapters are detected with editable boundaries.
- Text is preserved with paragraph-level fidelity.

### 14.2 Character & Speaker Modeling
- Identify named characters from dialogue and narrative mentions.
- Create a character registry.
- Support aliases (e.g., “Doctor”, “Dr. Patel”, “Patel”).
- Allow user to merge/split detected characters.
- Assign narrator + N character voices.

**Acceptance Criteria**
- User can map at least 20 characters in one project.
- Voice assignments persist across sessions.
- Speaker attribution uncertainty is surfaced, not hidden.

### 14.3 Voice Generation
- Generate narrator voice.
- Generate character dialogue with assigned voices.
- Allow style prompts per voice or per segment.
- Support pronunciation lexicon overrides.
- Regenerate segment without changing neighboring segments.

**Acceptance Criteria**
- User can regenerate a single line in under a practical editing loop threshold.
- Adjacent segment timings remain stable enough for editing continuity.

### 14.4 Scene Direction
- Global presets: Neutral / Expressive / Cinematic.
- Scene mood tags.
- Per-line instruction overrides.
- Silence insertion rules.
- Pause handling around dialogue beats.

**Acceptance Criteria**
- User can change scene style and regenerate affected segments only.

### 14.5 Ambience & SFX
- Suggest ambience categories based on scene context.
- Support low-volume looping ambience.
- Support event SFX insertion on selected moments.
- Separate stems from speech.
- Default to conservative sound design.

**Acceptance Criteria**
- Export can be generated with speech-only or speech+ambience.
- User can globally reduce ambience intensity.

### 14.6 Review & Editing
- Segment-level playback.
- Text-audio alignment.
- Notes per segment.
- Version history of regenerated outputs.
- “Needs review” queue.

**Acceptance Criteria**
- User can review only uncertain/problematic segments without replaying entire chapter.

### 14.7 Export
- MP3, WAV, M4B.
- Chapterized outputs.
- Metadata entry.
- Cover image attachment.
- Batch export.

**Acceptance Criteria**
- A 10-chapter book can be exported as separate chapter files and as a packaged audiobook project.

## 15. Non-Functional Requirements
### Performance
- Must run on Apple Silicon locally.
- Must support resumable generation for long books.
- Must not require full-book generation in one pass.

### Reliability
- Crash-safe project save.
- Checkpoint chapter outputs.
- Recover from failed segments without corrupting project.

### Usability
- First meaningful output within the first session.
- Default settings should sound decent without advanced tuning.

### Privacy
- Entire pipeline may run locally.
- No cloud upload required for core workflows.
- Clear disclosure if optional cloud models are later added.

### Compliance
- Rights declaration before export.
- Explicit restrictions for commercial use if unsupported rights are not verified.

## 16. System Architecture (MVP)
### Major Components
1. **Ingestion Service**
   - Parses EPUB/DOCX/TXT.
2. **Narrative Structuring Engine**
   - Chapters, scenes, dialogue blocks, speaker candidates.
3. **Casting Engine**
   - Character registry + voice assignments.
4. **Direction Engine**
   - Maps scene mood and line-level instructions into generation prompts.
5. **TTS Engine**
   - Local speech synthesis.
6. **Audio Assembly Engine**
   - Concatenation, pauses, stem alignment, ambience layering.
7. **Editor UI**
   - Review, patch, regenerate.
8. **Export Engine**
   - Packaging and metadata.
9. **Project Store**
   - Local filesystem project format.

## 17. Data Model
### Project
- project_id
- title
- author
- rights_status
- source_file_path
- created_at
- updated_at
- settings

### Chapter
- chapter_id
- title
- order
- word_count
- generation_status

### Scene
- scene_id
- chapter_id
- mood_tags
- style_preset
- ambience_profile

### Segment
- segment_id
- scene_id
- text
- segment_type (narration/dialogue/sfx/silence)
- speaker_id
- direction_tags
- audio_path
- duration_ms
- review_status
- version

### Character
- character_id
- display_name
- aliases
- description
- voice_profile_id
- pronunciation_notes

### Voice Profile
- voice_profile_id
- provider/model
- base_voice
- style_prompt
- speaking_rate
- warmth
- gravel
- consistency_seed/settings

## 18. Technical Assumptions
- The first implementation prioritizes smaller and faster local models over absolute state-of-the-art cloud quality.
- The system will generate audio chapter-by-chapter and segment-by-segment.
- Speech and ambience will be rendered as separate stems.
- Long-form continuity is managed through persistent voice profiles and scene direction rules.

## 19. Default Production Modes
### Mode 1 — Clean Narration
- Narrator only
- No ambience
- Fastest generation

### Mode 2 — Multi-Voice Narrative
- Narrator + character voices
- No ambience by default
- Best balance of quality and speed

### Mode 3 — Light Cinematic
- Narrator + character voices
- Subtle ambience
- Sparse event SFX
- Best sample/demo mode

## 20. Quality Framework
### Objective Checks
- Missing segment detection
- Audio clipping detection
- Silence anomalies
- Pronunciation dictionary misses
- Duplicate line detection
- Extreme loudness mismatch

### Human Quality Rubric
Each chapter is rated on:
- voice consistency,
- emotional appropriateness,
- intelligibility,
- character separation,
- ambience restraint,
- pacing,
- immersion.

## 21. Metrics
### Product Metrics
- Time to first chapter draft
- Average manual edits per 1,000 words
- Regenerations per chapter
- Export completion rate
- Session-to-export conversion

### Quality Metrics
- User-rated immersion score
- Character distinguishability score
- Pronunciation correctness rate
- Chapter acceptance rate without major rework

### System Metrics
- Generation time per 1,000 words
- Failure rate per segment
- Memory usage
- Recovery success rate

## 22. Risks
1. **Speaker attribution errors**
   - Mitigation: confidence UI + manual override.
2. **Voice inconsistency over long books**
   - Mitigation: voice bible + seed/profile locking.
3. **Overproduced sound design**
   - Mitigation: conservative defaults + speech-only preview.
4. **Legal misuse on copyrighted books**
   - Mitigation: rights gate + clear policy + licensing workflow later.
5. **Slow local generation**
   - Mitigation: chunking, resumable jobs, preview mode.
6. **Pronunciation of invented terms/names**
   - Mitigation: lexicon editor + global overrides.

## 23. Constraints
- Must be practical on a single Apple Silicon device.
- Must avoid requiring studio-level audio expertise.
- Must keep full-book generation resumable.
- Must not rely on internet availability for core workflows.

## 24. Roadmap
### Phase 1
- Import + parser
- Cast builder
- Narrator + character generation
- Chapter export

### Phase 2
- Scene direction
- Pronunciation lexicon
- Segment patching
- Basic ambience/SFX

### Phase 3
- M4B package export
- Voice bible templates
- Project templates
- Better review queue

## 25. Launch Strategy (MVP)
### Initial Launch Type
Private alpha for:
- indie authors,
- audio hobbyists,
- internal publishing experiments.

### Positioning
“Turn your manuscript into a cinematic multi-voice audiobook draft on your Mac.”

### Pricing Hypothesis
- One-time desktop license, or
- paid beta, or
- freemium with export watermark limits.

## 26. Open Questions
- How much automatic speaker attribution is “good enough” for MVP?
- Should voice cloning be included at launch or gated?
- Should music be excluded entirely in MVP to avoid overproduction?
- What is the ideal maximum number of distinct characters before UX breaks down?
- Should the editor look like a DAW, a text editor, or a hybrid?

## 27. MVP Exit Criteria
The MVP is ready when:
- a full novella or novel can be imported,
- at least one chapter can be generated with narrator + character voices,
- problematic lines can be selectively regenerated,
- a user can export a chaptered audiobook draft,
- users consistently say it feels more immersive than generic TTS.

---

# PRD B — Final Product

## 1. Product Name
**AI Audiobook Studio Platform**

## 2. Product Summary
A full-stack, production-grade audiobook creation platform that converts licensed long-form text into high-quality audio experiences using AI direction, multi-character casting, speech synthesis, ambience/SFX design, editorial review, collaboration, rights management, and distribution workflows.

This product serves:
- indie authors,
- small publishers,
- audiobook studios,
- enterprise publishers,
- localization teams,
- accessibility programs,
- content licensing platforms.

## 3. Product Vision
Become the default operating system for next-generation audiobook production: faster than traditional narration pipelines, dramatically more expressive than standard TTS, and safer and more controllable than fully automated “generate everything” tools.

The final product should support three quality levels:
1. **AI draft**
2. **Producer-polished release**
3. **Publisher-grade commercial release**

## 4. Mission
Compress audiobook production time and cost while increasing creative control, localization speed, and experimentation quality.

## 5. Market Opportunity
Audiobook demand continues to rise, but professional production remains expensive, slow, and difficult to scale across backlists, translations, and niche titles. Existing tools either:
- focus on generic single-voice TTS,
- lack production controls,
- lack long-form continuity,
- or fail to address licensing and publishing workflows.

AI Audiobook Studio can occupy the space between:
- text-to-speech tools,
- DAWs,
- publisher workflow systems,
- and full-service audiobook studios.

## 6. Target Segments
### Segment A — Indie Authors
Need affordability, ease, and speed.

### Segment B — Small/Medium Publishers
Need backlist conversion, lower cost, faster release, and controlled workflows.

### Segment C — Studios / Agencies
Need producer workstations, collaboration, approvals, and fine control.

### Segment D — Enterprise Publishers / Rights Holders
Need rights management, auditability, brand consistency, localization, and catalog scale.

### Segment E — Accessibility / Education Programs
Need clear narration, role separation, and controllable delivery.

## 7. Product Pillars
1. **Narrative Intelligence**
   - Understands structure, speakers, tone, pacing.
2. **Voice Direction**
   - Consistent casting, voice design, performance control.
3. **Production Quality**
   - Stems, ambience, mastering, loudness, patching.
4. **Human Workflow**
   - Review, approvals, collaboration, versioning.
5. **Rights & Safety**
   - Licensing, provenance, allowed-use enforcement.
6. **Scale**
   - Catalog processing, localization, enterprise deployment.

## 8. Product Goals
### Business Goals
- Reduce audiobook production cost and turnaround time.
- Unlock long-tail catalog monetization.
- Enable rapid sample creation for sales/marketing.
- Create recurring revenue through SaaS + usage + enterprise plans.

### User Goals
- Produce immersive multi-voice audiobooks.
- Retain editorial control.
- Manage long-form projects reliably.
- Scale production to multiple titles and languages.

## 9. Non-Goals
- Replacing all human narrators in every premium production.
- Becoming a music production suite.
- Supporting unauthorized commercial adaptation of copyrighted books.
- Defaulting every title to a fully dramatized audio drama.

## 10. Product Modes
### 10.1 Solo Creator Mode
- Lightweight project setup
- Fast defaults
- Desktop + optional cloud acceleration

### 10.2 Publisher Mode
- Multi-title pipeline
- Templates
- Team permissions
- Rights registry
- Approval workflows

### 10.3 Studio Mode
- Advanced direction controls
- Stem export to DAWs
- Fine-grained mixing and timing tools
- External asset support

### 10.4 API / Platform Mode
- Programmatic ingestion
- Batch processing
- Integration with CMS/DAM/rights systems

## 11. End-to-End Workflow
1. Rights verification / project creation
2. Ingestion and normalization
3. Structural analysis
4. Character and speaker graph creation
5. Voice casting and approval
6. Pronunciation and lexicon setup
7. Scene direction plan creation
8. Audio generation pass
9. QA pass (automated)
10. Human review and patching
11. Mixing/mastering
12. Packaging and metadata
13. Distribution/export
14. Analytics and post-release feedback

## 12. Functional Areas

### 12.1 Rights & Licensing Module
- Rights declaration and evidence storage
- Content classification: public domain / owned / licensed / restricted
- Voice rights and cloning permission records
- Commercial-use gating
- Audit logs for generation and export
- Territory/language restrictions

### 12.2 Ingestion & Content Normalization
- EPUB, DOCX, PDF (with validation), TXT, Markdown, CMS import
- OCR quality warnings
- Chapter extraction
- Footnote/endnote handling
- Front/back matter rules
- Style normalization
- Dialogue cleanup

### 12.3 Narrative Intelligence Engine
- Chapter/scene segmentation
- Dialogue attribution
- POV detection
- Internal monologue detection
- Flashback / timeline shift detection
- Tension and pacing analysis
- Emotional beat detection
- Character relationship graph

### 12.4 Character Bible & Casting
- Character cards with description, age band, vocal tone, accent, emotional range
- Narrator profile management
- Voice search and recommendation
- Voice cloning / voice design workflows with consent records
- Character continuity across sequels/series
- Shared publisher voice libraries

### 12.5 Pronunciation & Language Layer
- Custom dictionary
- IPA/phonetic fields
- Series glossary
- Fantasy/Sci-fi term handling
- Regional pronunciation profiles
- Multi-language adaptations
- Accent-safe variants

### 12.6 Direction System
- Scene-level direction plans
- Line-level direction controls
- Delivery styles: intimate, detached, urgent, playful, weary, cold, heroic, etc.
- Pace, emphasis, pause, breath, whisper, shout simulation settings
- Character emotional arc continuity
- “Underplay” safeguard to prevent melodrama

### 12.7 Speech Generation Engine
- Multiple model backends: local, cloud, hybrid
- Draft mode vs release mode generation
- Voice consistency controls
- Streaming preview
- Patch generation
- Batch chapter rendering
- Multi-speaker orchestration

### 12.8 Ambience, Foley & Music Layer
- Suggested ambience packs
- Contextual event SFX suggestions
- Style guides per imprint/publisher
- Stem-based mixing
- Music bed support with rights-safe assets
- Intensity controls and anti-overproduction rules

### 12.9 Editorial Review Workspace
- Text/audio sync editor
- Segment comments
- approval states
- compare versions
- reviewer assignments
- issue queue
- patch history
- side-by-side transcript and waveform

### 12.10 Audio Post-Processing
- Loudness normalization
- Room tone continuity
- Breath/noise cleanup
- clipping checks
- de-essing or smoothing where needed
- mastering presets by distribution target

### 12.11 Packaging & Distribution
- M4B, MP3, WAV, stem export, DAW-friendly exports
- chapter metadata
- cover art and catalog metadata
- storefront-compliant package templates
- sample clip export for marketing
- distribution handoff APIs

### 12.12 Analytics & Feedback
- completion/listen-through telemetry (where allowed)
- skipped segment analysis
- chapter drop-off analysis
- sample conversion metrics
- QA defect categories
- regeneration heatmaps

## 13. Key Personas
### Persona 1 — Indie Author Aria
Wants to launch an audiobook without paying for a full voice cast. She prioritizes simplicity, affordability, and good emotional differentiation.

### Persona 2 — Publisher Ops Lead Dev
Needs to convert 500 backlist titles into commercially viable audiobooks while enforcing rights restrictions and consistent quality templates.

### Persona 3 — Audio Producer Maya
Needs a sophisticated editor and hates black-box AI output. Wants patchable segments, stems, approvals, and export to external tools.

### Persona 4 — Rights Manager Sofia
Needs audit trails, license scopes, territory restrictions, and proof that no unauthorized voice cloning or unlicensed content was used.

## 14. Detailed User Stories
### Rights
- As a publisher, I want to prove I control audiobook rights before allowing commercial export.
- As a rights manager, I want to track which voice models/voices were used on each title.

### Series Continuity
- As a producer, I want recurring characters in Book 2 to sound consistent with Book 1.
- As a publisher, I want series templates so tone and brand remain stable.

### Localization
- As a localization team, I want to adapt a title into multiple languages while preserving narrative structure and character identity.

### QA
- As an editor, I want the platform to flag suspicious pronunciations, abrupt pacing changes, repeated words, and tonal mismatches.

### Collaboration
- As a team lead, I want to assign chapters to reviewers and track approvals.

### Distribution
- As operations, I want ready-to-submit audio packages for storefronts and internal archives.

## 15. Experience Design Requirements
### Onboarding
- guided setup by project type
- rights validation checkpoint
- starter templates
- quality mode selection

### Main Workspace
- project navigator on left
- transcript/timeline center
- voice/direction inspector on right
- QA/issues tray below
- chapter/scene switching with low friction

### Collaboration UX
- reviewer mentions
- asset locking during edits
- compare current vs approved outputs
- comment threads anchored to exact timecodes and text spans

## 16. Advanced Functional Requirements

### 16.1 Rights Enforcement
- Commercial export blocked unless rights status is valid.
- Voice cloning blocked without explicit consent evidence.
- Restricted content can be sandboxed for evaluation only.
- Every export includes generation provenance metadata.

### 16.2 Catalog-Scale Processing
- Bulk project creation from title feeds.
- Shared voice and style templates.
- Queue-based rendering.
- Resume/retry infrastructure.
- Fleet orchestration for cloud/hybrid environments.

### 16.3 Multi-Title Knowledge Reuse
- Shared pronunciation dictionaries.
- imprint-level sound style templates.
- recurring series cast libraries.
- reusable ambience packs.

### 16.4 Quality Safeguards
- voice drift detection
- pronunciation anomaly detection
- dialogue attribution confidence scoring
- over-acting risk detection
- ambience masking score
- chapter loudness compliance checks

### 16.5 Human Escalation System
- uncertain segments routed to human review
- “must approve” rules for low-confidence areas
- audio producer override authority
- publish blocking issues

## 17. AI/ML Layer Requirements
### Inputs
- manuscript text
- metadata
- pronunciation dictionaries
- rights constraints
- voice library
- scene direction prompts

### Outputs
- segment-level audio
- alignment metadata
- confidence scores
- suggested issues
- voice usage logs
- production manifests

### Model Governance
- support multiple model providers
- track model version by render
- allow title-level model locking
- preserve reproducibility where possible

## 18. Enterprise Requirements
- SSO / SAML
- RBAC
- tenant isolation
- audit trails
- data retention policies
- private deployment options
- VPC / on-prem support where needed
- legal hold/export logs

## 19. Security & Privacy
- encrypt project data at rest and in transit
- isolate uploaded manuscripts
- secure voice samples and consent documents
- configurable retention for generated assets
- explicit training-data policy: customer data not reused unless opted in

## 20. API Requirements
- create project
- upload manuscript
- fetch structure
- manage voices
- submit generation jobs
- retrieve outputs
- review/approve segments
- export/package
- push events/webhooks

## 21. Data Entities
### Organization
- org_id
- plan
- policy settings

### User
- user_id
- role
- permissions

### Title / Work
- work_id
- isbn/internal_id
- rights status
- territory/language scopes

### Project
- project_id
- work_id
- pipeline config
- target language
- target quality mode

### Render Job
- job_id
- model versions
- runtime environment
- status
- cost metrics

### Review Item
- issue_id
- segment_id
- severity
- assignee
- disposition

### Export Package
- export_id
- format
- mastering preset
- compliance status

## 22. Output Quality Levels
### Draft
- fast generation
- moderate quality
- lower cost
- for internal review

### Producer Polish
- stronger consistency
- selective manual review
- better mastering
- sample-ready and often release-capable

### Publisher Release
- stricter QA
n- full rights checks
- advanced mastering
- mandatory approvals
- storefront packaging compliance

## 23. Metrics Framework
### Business Metrics
- titles produced per month
- time to release
- cost per finished hour
- expansion revenue from backlist conversion
- churn by segment

### Product Metrics
- project completion rate
- average review cycles per chapter
- patch frequency
- % exports accepted without external DAW roundtrip

### Quality Metrics
- MOS-like user listening scores
- distinctness of character voices
- pronunciation error rate
- rights compliance incident rate
- QA issues per finished hour

### Platform Metrics
- queue latency
- render failure rate
- storage cost per project
- GPU/accelerator utilization in cloud/hybrid mode

## 24. Go-To-Market
### Phase 1
Serve indie authors and creators with desktop + hosted optional acceleration.

### Phase 2
Offer team workflows to small publishers.

### Phase 3
Sell enterprise deployments to publishers with large backlists and localization needs.

### Packaging Options
- Creator plan
- Studio plan
- Publisher team plan
- Enterprise license
- API usage tier

## 25. Competitive Positioning
We are not just another TTS app.
We are not just another DAW.
We are not just an audiobook distributor.

We are the **production system for long-form narrative audio adaptation**.

Differentiators:
- narrative-aware generation,
- persistent character casting,
- editable long-form workflows,
- rights-aware publishing controls,
- local/hybrid deployment options,
- series and catalog continuity.

## 26. Risks and Mitigations
### Risk 1 — Quality plateau vs human narrators
Mitigation: target hybrid workflows, not pure replacement.

### Risk 2 — Legal/regulatory pushback
Mitigation: rights module, voice consent, commercial gates, auditability.

### Risk 3 — Overpromising “one-click cinematic audiobooks”
Mitigation: market as producer-grade workflow, not magic.

### Risk 4 — Voice cloning misuse
Mitigation: permission requirements, watermarking/provenance, restricted features.

### Risk 5 — Operational cost at scale
Mitigation: quality tiers, caching, hybrid local/cloud execution.

### Risk 6 — Editorial distrust of AI output
Mitigation: explainability, confidence scores, patch workflows, side-by-side review.

## 27. Release Roadmap
### Release 1
- MVP foundation
- solo creator workflows
- local-first generation

### Release 2
- cloud acceleration
- collaboration
- better QA
- stem exports

### Release 3
- rights module
- publisher templates
- shared voice libraries
- analytics dashboard

### Release 4
- localization workflows
- enterprise APIs
- catalog-scale orchestration
- advanced governance

## 28. Organizational Requirements
To ship the final product, the team will likely need:
- product manager,
- narrative UX designer,
- ML/audio engineer,
- full-stack engineer,
- audio tooling engineer,
- rights/compliance advisor,
- QA + listening ops.

## 29. Final Product Exit Criteria
The final product is successful when:
- publishers can process titles at scale,
- solo creators can still get value quickly,
- multi-voice outputs feel materially more immersive than generic TTS,
- rights/compliance workflows are trusted,
- teams can produce release-grade audiobooks with significantly lower cost/time than traditional workflows.

## 30. Strategic Thesis
The winning product will not be the one with the flashiest raw voice model. It will be the one that best combines:
- narrative intelligence,
- casting consistency,
- tasteful direction,
- human review,
- rights compliance,
- and repeatable production workflow.

That is the strategic goal of AI Audiobook Studio.



---

# Engineering Roadmap

This section translates the PRDs into an implementation plan with:
- recommended repository structure,
- service boundaries,
- API contracts,
- data/storage schema,
- phased milestones,
- delivery sequencing,
- operational decisions.

The roadmap is split into two lanes:
1. **Lane A — Local-First MVP**
2. **Lane B — Hybrid/Cloud Publisher Platform**

The product should be built so that Lane A is not throwaway work. The local-first MVP should become the “single-node runtime” of the broader system.

---

## 1. Engineering Strategy

### 1.1 Architectural Principles
1. **Segment-first pipeline**
   - Never treat the whole book as a single generation unit.
   - The stable unit is `segment`.
   - Segments belong to scenes; scenes belong to chapters; chapters belong to projects.

2. **Manifest-driven processing**
   - Every stage should read/write structured manifests.
   - Audio generation should be reproducible from manifests and versioned settings.

3. **Human patchability over monolithic rendering**
   - Users must be able to regenerate one line without rerendering the chapter.

4. **Runtime portability**
   - The same core services should run:
     - locally as embedded processes,
     - as Docker containers,
     - later in a cloud worker fleet.

5. **Storage separation**
   - transactional metadata in database,
   - large artifacts in filesystem / object storage,
   - derived caches isolated from source assets.

6. **Clear service seams**
   - parsing,
   - narrative analysis,
   - casting,
   - generation,
   - assembly,
   - review,
   - export.

7. **Model abstraction from product logic**
   - product code should not depend tightly on one TTS backend.
   - introduce adapters for Qwen / MLX / future backends.

### 1.2 Deployment Philosophy
#### MVP
- single-user,
- local desktop + local web UI,
- filesystem project store,
- embedded DB,
- background job runner in-process.

#### Scale-up
- multi-user web app,
- API service,
- queue workers,
- object storage,
- shared database,
- authentication and RBAC.

---

## 2. Recommended Tech Stack

### 2.1 Core Languages
- **Backend orchestration/API**: Python or TypeScript/Node for fast iteration.
- **ML/audio pipeline**: Python.
- **Desktop shell (optional)**: Tauri or Electron.
- **Web UI**: Next.js / React.
- **Audio editor UI**: React with waveform/timeline components.

### 2.2 Recommended Practical Choice
Use:
- **Python** for pipeline services, model orchestration, audio processing, batch jobs.
- **FastAPI** for backend APIs.
- **React/Next.js** for UI.
- **SQLite** for local MVP metadata.
- **Postgres** for scaled/cloud version.
- **Local filesystem** for MVP artifact storage.
- **S3-compatible object storage** for final platform.
- **Redis** only after moving to multi-node async queues.

### 2.3 Why this split
- TTS/audio tooling is much stronger in Python.
- FastAPI is fast to ship and easy to evolve.
- React is the safest option for transcript/timeline-heavy tooling.
- SQLite avoids unnecessary infrastructure in MVP.

---

## 3. Repository Structure

### 3.1 Monorepo Recommendation
Use a monorepo initially. This reduces integration pain while the domain is still changing quickly.

```text
ai-audiobook-studio/
├─ apps/
│  ├─ web/                          # Next.js app
│  ├─ desktop-shell/                # Tauri/Electron wrapper (optional)
│  └─ api/                          # FastAPI app entrypoint
│
├─ services/
│  ├─ ingestion-service/            # file import, normalization, chapter extraction
│  ├─ narrative-service/            # scenes, dialogue attribution, character registry
│  ├─ casting-service/              # voice profiles, character voice assignment
│  ├─ direction-service/            # scene style, delivery directives, pause rules
│  ├─ tts-service/                  # backend-agnostic speech generation
│  ├─ audio-assembly-service/       # concatenation, stems, timing, fades, ambience layering
│  ├─ qa-service/                   # pronunciation checks, drift detection, loudness checks
│  ├─ review-service/               # comments, issues, approvals, patch history
│  ├─ export-service/               # M4B/MP3/WAV packaging and metadata
│  └─ rights-service/               # rights/consent/policy checks (can be minimal in MVP)
│
├─ libs/
│  ├─ domain-models/                # Pydantic models / shared schemas
│  ├─ audio-utils/                  # ffmpeg wrappers, loudness, silence, waveform helpers
│  ├─ tts-adapters/                 # qwen, mlx, mock, future providers
│  ├─ storage/                      # local FS, S3, artifact index helpers
│  ├─ db/                           # ORM models, migrations, repositories
│  ├─ manifests/                    # pipeline manifest schema and serializers
│  ├─ auth/                         # later-stage auth helpers
│  ├─ ui-components/                # shared UI components
│  └─ observability/                # logging, metrics, tracing helpers
│
├─ scripts/
│  ├─ seed_sample_project.py
│  ├─ reindex_artifacts.py
│  ├─ benchmark_tts.py
│  ├─ backfill_waveforms.py
│  └─ export_debug_bundle.py
│
├─ infra/
│  ├─ docker/
│  ├─ compose/
│  ├─ k8s/                          # later stage
│  ├─ terraform/                    # later stage
│  └─ ci/
│
├─ docs/
│  ├─ architecture/
│  ├─ api/
│  ├─ runbooks/
│  ├─ ADRs/
│  └─ product/
│
├─ examples/
│  ├─ sample-manuscripts/
│  ├─ sample-voice-bibles/
│  └─ demo-projects/
│
├─ tests/
│  ├─ integration/
│  ├─ e2e/
│  ├─ fixtures/
│  └─ golden-audio/
│
├─ pyproject.toml
├─ package.json
├─ turbo.json / nx.json             # optional build orchestration
└─ README.md
```

### 3.2 Repo Evolution Strategy
#### Stage 1
Single monorepo, all services in-process.

#### Stage 2
Still monorepo, but services become separately runnable.

#### Stage 3
Only split repos if:
- teams grow,
- release cadences differ,
- infra becomes significantly complex.

---

## 4. Runtime Architecture

### 4.1 MVP Runtime (Single Node)
```text
[React UI]
    |
    v
[FastAPI App]
    |
    +--> Ingestion Module
    +--> Narrative Module
    +--> Casting Module
    +--> Direction Module
    +--> TTS Module
    +--> Audio Assembly Module
    +--> QA Module
    +--> Export Module
    |
    +--> SQLite DB
    +--> Local Artifact Store (/projects/...)
    +--> Local Model Runtime (Qwen/MLX/etc.)
```

### 4.2 Scaled Runtime (Hybrid/Cloud)
```text
[Web App]
    |
    v
[API Gateway / Backend API]
    |
    +--> Project Service
    +--> Rights Service
    +--> Review Service
    +--> Export Service
    |
    +--> Postgres
    +--> Object Storage
    +--> Redis / Queue
    |
    +--> Worker Pool:
           - Ingestion Worker
           - Narrative Worker
           - TTS Worker
           - Assembly Worker
           - QA Worker
           - Packaging Worker
```

### 4.3 Pipeline Execution Model
Every processing stage should produce:
- `input_manifest.json`
- `output_manifest.json`
- logs
- artifact references
- quality metadata

This keeps the pipeline debuggable and resumable.

---

## 5. Service Breakdown

### 5.1 Ingestion Service
**Responsibilities**
- import manuscript files,
- normalize text,
- detect chapters,
- clean formatting noise,
- store canonical source text.

**Inputs**
- EPUB/DOCX/TXT/Markdown/PDF later

**Outputs**
- canonical manuscript JSON,
- chapter records,
- raw structural hints.

**Key modules**
- file parsers,
- normalization pipeline,
- chapter boundary detector,
- validation warnings.

### 5.2 Narrative Service
**Responsibilities**
- scene segmentation,
- dialogue detection,
- speaker attribution,
- character extraction,
- internal monologue classification.

**Outputs**
- scene graph,
- character registry,
- segment list,
- confidence scores.

**Key modules**
- NER/entity resolution,
- dialogue attribution rules,
- segmenter,
- scene mood inference.

### 5.3 Casting Service
**Responsibilities**
- narrator profile,
- character-to-voice mapping,
- voice bible persistence,
- pronunciation rules.

**Outputs**
- voice profile assignments,
- project voice manifest,
- pronunciation dictionary overrides.

### 5.4 Direction Service
**Responsibilities**
- scene-level style defaults,
- line-level delivery directives,
- pause rules,
- intensity controls,
- anti-overproduction safeguards.

**Outputs**
- generation directives per segment.

### 5.5 TTS Service
**Responsibilities**
- generate audio for a segment,
- support multiple backends,
- store raw speech stems,
- expose generation diagnostics.

**Key interfaces**
- `synthesize_segment()`
- `preview_voice()`
- `validate_voice_profile()`

### 5.6 Audio Assembly Service
**Responsibilities**
- combine speech stems,
- insert pauses,
- layer ambience,
- manage fades,
- build chapter audio.

**Outputs**
- chapter speech stem,
- ambience stem,
- mixed chapter,
- alignment map.

### 5.7 QA Service
**Responsibilities**
- pronunciation anomaly checks,
- missing segment checks,
- clipping/loudness checks,
- voice drift heuristics,
- silence anomaly checks.

**Outputs**
- issue records,
- chapter quality report,
- blocking/non-blocking warnings.

### 5.8 Review Service
**Responsibilities**
- comments,
- patch requests,
- segment status transitions,
- approvals,
- issue assignment.

### 5.9 Export Service
**Responsibilities**
- render final package,
- embed metadata,
- generate chapter files,
- package M4B/ZIP bundles,
- create sample clips.

### 5.10 Rights Service
**MVP version**
- store rights declaration,
- require acknowledgment before export.

**Final version**
- store license documents,
- voice consent artifacts,
- policy engine for commercial restrictions.

---

## 6. Core Domain Model

### 6.1 Entity Hierarchy
```text
Organization (later)
  └─ User (later)
      └─ Project
           ├─ SourceDocument
           ├─ Chapter
           │    ├─ Scene
           │    │    ├─ Segment
           │    │    └─ SceneDirective
           │    ├─ ChapterRender
           │    └─ QualityReport
           ├─ Character
           ├─ VoiceProfile
           ├─ PronunciationEntry
           ├─ Issue
           ├─ Comment
           ├─ ExportPackage
           └─ RightsDeclaration
```

### 6.2 Segment as the Primary Unit
A `Segment` should be the atomic editable/generatable object.

Segment types:
- narration
- dialogue
- monologue
- silence
- ambience-cue
- sfx-cue

Why this matters:
- patchability,
- versioning,
- QA granularity,
- render caching.

---

## 7. Database Schema

### 7.1 MVP Database Recommendation
Use **SQLite** with SQLAlchemy and Alembic migrations.

### 7.2 Cloud Database Recommendation
Move to **Postgres** with mostly the same schema.

### 7.3 Schema Overview

#### projects
```sql
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT,
  description TEXT,
  rights_status TEXT NOT NULL DEFAULT 'declared',
  rights_notes TEXT,
  source_format TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  settings_json TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

#### source_documents
```sql
CREATE TABLE source_documents (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  original_path TEXT,
  normalized_text_path TEXT,
  checksum TEXT,
  word_count INTEGER,
  parser_version TEXT,
  created_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### chapters
```sql
CREATE TABLE chapters (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  chapter_number INTEGER,
  title TEXT,
  order_index INTEGER NOT NULL,
  source_text_path TEXT,
  word_count INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### scenes
```sql
CREATE TABLE scenes (
  id TEXT PRIMARY KEY,
  chapter_id TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  title TEXT,
  mood_tags_json TEXT,
  style_preset TEXT,
  ambience_profile TEXT,
  start_offset INTEGER,
  end_offset INTEGER,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(chapter_id) REFERENCES chapters(id)
);
```

#### characters
```sql
CREATE TABLE characters (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  aliases_json TEXT,
  description TEXT,
  role_type TEXT,
  notes TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### voice_profiles
```sql
CREATE TABLE voice_profiles (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  backend TEXT NOT NULL,
  base_voice_id TEXT,
  style_prompt TEXT,
  settings_json TEXT,
  sample_audio_path TEXT,
  is_narrator_default INTEGER NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### character_voice_assignments
```sql
CREATE TABLE character_voice_assignments (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  character_id TEXT NOT NULL,
  voice_profile_id TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(character_id) REFERENCES characters(id),
  FOREIGN KEY(voice_profile_id) REFERENCES voice_profiles(id)
);
```

#### pronunciation_entries
```sql
CREATE TABLE pronunciation_entries (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  term TEXT NOT NULL,
  phonetic TEXT,
  replacement_text TEXT,
  notes TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### segments
```sql
CREATE TABLE segments (
  id TEXT PRIMARY KEY,
  scene_id TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  segment_type TEXT NOT NULL,
  speaker_character_id TEXT,
  text_content TEXT NOT NULL,
  normalized_text TEXT,
  attribution_confidence REAL,
  direction_json TEXT,
  duration_ms INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  current_render_id TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(scene_id) REFERENCES scenes(id),
  FOREIGN KEY(speaker_character_id) REFERENCES characters(id)
);
```

#### segment_renders
```sql
CREATE TABLE segment_renders (
  id TEXT PRIMARY KEY,
  segment_id TEXT NOT NULL,
  voice_profile_id TEXT,
  backend TEXT NOT NULL,
  backend_model_version TEXT,
  render_params_json TEXT,
  speech_audio_path TEXT,
  alignment_json_path TEXT,
  waveform_json_path TEXT,
  duration_ms INTEGER,
  qa_summary_json TEXT,
  created_at DATETIME NOT NULL,
  FOREIGN KEY(segment_id) REFERENCES segments(id),
  FOREIGN KEY(voice_profile_id) REFERENCES voice_profiles(id)
);
```

#### chapter_renders
```sql
CREATE TABLE chapter_renders (
  id TEXT PRIMARY KEY,
  chapter_id TEXT NOT NULL,
  render_mode TEXT NOT NULL,
  speech_stem_path TEXT,
  ambience_stem_path TEXT,
  mixed_audio_path TEXT,
  manifest_path TEXT,
  duration_ms INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(chapter_id) REFERENCES chapters(id)
);
```

#### issues
```sql
CREATE TABLE issues (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  chapter_id TEXT,
  scene_id TEXT,
  segment_id TEXT,
  severity TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  metadata_json TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### comments
```sql
CREATE TABLE comments (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  segment_id TEXT,
  chapter_id TEXT,
  body TEXT NOT NULL,
  created_by TEXT,
  created_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### exports
```sql
CREATE TABLE exports (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  format TEXT NOT NULL,
  scope TEXT NOT NULL,
  metadata_json TEXT,
  output_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### jobs
```sql
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  job_type TEXT NOT NULL,
  target_id TEXT,
  payload_json TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  error_message TEXT,
  progress_json TEXT,
  created_at DATETIME NOT NULL,
  started_at DATETIME,
  finished_at DATETIME,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

#### rights_declarations
```sql
CREATE TABLE rights_declarations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  declaration_type TEXT NOT NULL,
  status TEXT NOT NULL,
  evidence_path TEXT,
  notes TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

### 7.4 Tables Added Later for Multi-User Cloud
- organizations
- users
- memberships
- roles
- audit_logs
- api_keys
- billing_accounts
- asset_permissions
- review_assignments

---

## 8. Artifact Storage Layout

### 8.1 Local Filesystem Layout
```text
/projects/
  <project_id>/
    source/
      original.epub
      normalized.txt
      canonical_manuscript.json
    chapters/
      <chapter_id>/
        source.txt
        scenes.json
        chapter_manifest.json
        segments/
          <segment_id>/
            render_v1.wav
            render_v1.json
            render_v2.wav
            waveform.json
        stems/
          speech.wav
          ambience.wav
        mixes/
          mixed_v1.wav
          preview.mp3
    voices/
      <voice_profile_id>/
        preview.wav
        config.json
    exports/
      audiobook_v1.m4b
      chapter_01.mp3
    logs/
      pipeline.log
      qa_report.json
```

### 8.2 Why not BLOB audio in DB
Do not store audio binaries in the relational DB.
Store only paths/URIs + hashes + metadata.

---

## 9. API Design

### 9.1 API Style
Use REST for MVP. Add async jobs for long-running operations. Keep webhook/event patterns for later.

### 9.2 API Namespacing
```text
/api/v1/projects
/api/v1/chapters
/api/v1/scenes
/api/v1/segments
/api/v1/voices
/api/v1/jobs
/api/v1/issues
/api/v1/exports
/api/v1/rights
```

### 9.3 Core Endpoints

#### Projects
```http
POST   /api/v1/projects
GET    /api/v1/projects
GET    /api/v1/projects/{projectId}
PATCH  /api/v1/projects/{projectId}
DELETE /api/v1/projects/{projectId}
```

**Create project payload**
```json
{
  "title": "Project Hail Mary Demo",
  "author": "Example Author",
  "rightsStatus": "owned",
  "settings": {
    "renderMode": "multi_voice",
    "qualityMode": "draft"
  }
}
```

#### Source Import
```http
POST   /api/v1/projects/{projectId}/source/import
GET    /api/v1/projects/{projectId}/source
POST   /api/v1/projects/{projectId}/source/reparse
```

#### Chapters / Scenes / Segments
```http
GET    /api/v1/projects/{projectId}/chapters
GET    /api/v1/chapters/{chapterId}
GET    /api/v1/chapters/{chapterId}/scenes
GET    /api/v1/scenes/{sceneId}/segments
PATCH  /api/v1/segments/{segmentId}
```

**Segment patch payload**
```json
{
  "textContent": "Rocky said the line more softly.",
  "direction": {
    "delivery": "gentle",
    "pace": "slow",
    "pauseBeforeMs": 250
  },
  "speakerCharacterId": "char_rocky"
}
```

#### Characters and Voices
```http
GET    /api/v1/projects/{projectId}/characters
POST   /api/v1/projects/{projectId}/characters
PATCH  /api/v1/characters/{characterId}

GET    /api/v1/projects/{projectId}/voices
POST   /api/v1/projects/{projectId}/voices
PATCH  /api/v1/voices/{voiceId}
POST   /api/v1/voices/{voiceId}/preview
POST   /api/v1/characters/{characterId}/assign-voice
```

**Voice preview payload**
```json
{
  "text": "This is a preview of the selected narrator voice.",
  "stylePrompt": "warm, calm, intelligent"
}
```

#### Pronunciation Dictionary
```http
GET    /api/v1/projects/{projectId}/pronunciations
POST   /api/v1/projects/{projectId}/pronunciations
PATCH  /api/v1/pronunciations/{entryId}
DELETE /api/v1/pronunciations/{entryId}
```

#### Rendering / Jobs
```http
POST   /api/v1/projects/{projectId}/generate/chapters
POST   /api/v1/chapters/{chapterId}/generate
POST   /api/v1/segments/{segmentId}/generate
GET    /api/v1/jobs/{jobId}
POST   /api/v1/jobs/{jobId}/cancel
```

**Generate chapter payload**
```json
{
  "renderMode": "light_cinematic",
  "qualityMode": "draft",
  "includeAmbience": true,
  "regenerateOnlyFailed": false
}
```

#### Review / Issues
```http
GET    /api/v1/projects/{projectId}/issues
POST   /api/v1/segments/{segmentId}/comments
PATCH  /api/v1/issues/{issueId}
POST   /api/v1/segments/{segmentId}/mark-reviewed
```

#### Exports
```http
POST   /api/v1/projects/{projectId}/exports
GET    /api/v1/projects/{projectId}/exports
GET    /api/v1/exports/{exportId}
```

**Create export payload**
```json
{
  "format": "m4b",
  "scope": "full_project",
  "metadata": {
    "title": "My Audiobook",
    "author": "Me"
  }
}
```

#### Rights
```http
GET    /api/v1/projects/{projectId}/rights
POST   /api/v1/projects/{projectId}/rights/declaration
POST   /api/v1/projects/{projectId}/rights/evidence
```

### 9.4 Async Job Response Pattern
Every long task should return:
```json
{
  "jobId": "job_123",
  "status": "queued",
  "pollUrl": "/api/v1/jobs/job_123"
}
```

### 9.5 Internal Service Contracts
Internally, prefer typed Python interfaces/events over HTTP between modules during MVP. Move to message queues later.

---

## 10. Background Job Model

### 10.1 MVP
Use an in-process background runner.

Job types:
- import_source
- parse_narrative
- assign_characters
- preview_voice
- generate_segment
- generate_chapter
- assemble_chapter
- run_qa
- export_project

### 10.2 Scale-Up
Move to queue-based workers.

Recommended flow:
- API writes job row
- dispatcher claims queued jobs
- worker executes
- worker writes status updates
- UI polls or subscribes later

---

## 11. UI Structure and Frontend Modules

### 11.1 Frontend App Structure
```text
apps/web/src/
├─ app/
│  ├─ projects/
│  ├─ editor/
│  ├─ voices/
│  ├─ exports/
│  └─ settings/
├─ components/
│  ├─ project/
│  ├─ chapter/
│  ├─ timeline/
│  ├─ waveform/
│  ├─ voice/
│  ├─ review/
│  └─ export/
├─ hooks/
├─ lib/
├─ state/
└─ types/
```

### 11.2 Primary Screens to Ship First
1. Project list / dashboard
2. Source import and parse review
3. Character + voice mapping screen
4. Chapter review screen
5. Segment regeneration drawer
6. Export dialog

### 11.3 UI State Strategy
- TanStack Query for server state
- Zustand or Redux Toolkit for editor state
- waveform/timeline state isolated from project metadata state

---

## 12. Audio Pipeline Details

### 12.1 Processing Pipeline
```text
source text
 -> normalize
 -> chapter split
 -> scene split
 -> segment extraction
 -> character/speaker assignment
 -> voice assignment
 -> direction pass
 -> per-segment TTS
 -> speech stem assembly
 -> ambience layering
 -> chapter QA
 -> export/package
```

### 12.2 Segment Generation Contract
Inputs:
- normalized text
- voice profile
- direction settings
- pronunciation dictionary
- backend adapter

Outputs:
- WAV/PCM audio
- timing/alignment metadata
- diagnostics

### 12.3 Cache Strategy
Cache render results by key:
```text
hash(segment_text + voice_profile + direction + backend_version + lexicon_version)
```

This saves enormous time when patching/retrying.

---

## 13. Model Adapter Layer

### 13.1 Goal
Avoid scattering Qwen-specific logic across the codebase.

### 13.2 Adapter Interface
```python
class TTSAdapter(Protocol):
    def validate_voice_profile(self, profile: VoiceProfile) -> ValidationResult: ...
    def preview(self, text: str, profile: VoiceProfile) -> AudioArtifact: ...
    def synthesize_segment(self, request: SegmentRenderRequest) -> SegmentRenderResult: ...
```

### 13.3 Adapters
- `qwen_adapter.py`
- `mlx_adapter.py`
- `mock_adapter.py`
- `cloud_provider_adapter.py` later

### 13.4 Why this matters
- easy swapping of runtimes,
- easier benchmarking,
- easier fallback logic.

---

## 14. QA and Testing Strategy

### 14.1 Testing Layers
#### Unit Tests
- parser rules,
- segment splitting,
- voice assignment logic,
- render key hashing,
- export metadata generation.

#### Integration Tests
- import manuscript → chapters created,
- character assignment → segments linked,
- segment render → artifacts stored,
- export job → files created.

#### End-to-End Tests
- create project,
- import sample manuscript,
- assign voices,
- generate chapter,
- patch one segment,
- export audiobook sample.

### 14.2 Golden Tests
Keep “golden audio” only for structural validation, not exact waveform equality.
Compare:
- duration bounds,
- loudness bounds,
- file existence,
- metadata presence,
- alignment structure.

### 14.3 Human QA Harness
Create a lightweight listening checklist for each build:
- does voice assignment persist?
- is one segment patchable?
- is export structurally valid?
- is ambience too loud by default?

---

## 15. Observability

### 15.1 Logging
Use structured logging with fields:
- project_id
- chapter_id
- scene_id
- segment_id
- job_id
- service
- backend
- duration_ms
- status

### 15.2 Metrics
Track:
- job duration by type
- segment generation success rate
- average regeneration count
- export failure rate
- storage growth
- cache hit rate

### 15.3 Debug Bundles
A "download debug bundle" feature for a chapter should include:
- chapter manifest,
- segment list,
- issue report,
- logs,
- render settings,
- artifact index.

---

## 16. Security and Rights Controls

### 16.1 MVP
- explicit rights confirmation before export,
- local-only by default,
- no silent cloud upload.

### 16.2 Later Stages
- signed rights evidence uploads,
- voice consent records,
- immutable audit log for export decisions,
- policy engine for commercial-use blocking.

---

## 17. Phased Delivery Plan

## Phase 0 — Foundations (2–3 weeks)
**Goal**: establish skeleton, shared models, local runtime, and build workflow.

### Deliverables
- monorepo initialized,
- FastAPI app bootstrapped,
- Next.js app bootstrapped,
- shared domain schemas,
- SQLite + migrations,
- local project artifact directory layout,
- job runner scaffold,
- seed sample manuscript flow.

### Exit Criteria
- user can create a project,
- project persists locally,
- sample manuscript can be imported into storage.

---

## Phase 1 — Ingestion & Narrative Structure (3–4 weeks)
**Goal**: convert manuscript into chapters, scenes, and segments.

### Deliverables
- file import for TXT/Markdown/DOCX/EPUB,
- normalized manuscript generation,
- chapter extraction,
- scene segmentation,
- dialogue block detection,
- character extraction v1,
- chapter/scene/segment viewer.

### APIs
- create project,
- import source,
- fetch chapters/scenes/segments,
- patch segment text.

### Exit Criteria
- a manuscript becomes an editable structured project.

---

## Phase 2 — Casting, Voice Bible & Previews (2–3 weeks)
**Goal**: map characters and narrator to stable voice profiles.

### Deliverables
- character list UI,
- voice profile CRUD,
- narrator default profile,
- character-to-voice assignment,
- pronunciation dictionary CRUD,
- voice preview endpoint,
- persistent voice bible per project.

### Exit Criteria
- user can assign voices and hear previews for narrator and characters.

---

## Phase 3 — Segment TTS & Chapter Assembly (4–5 weeks)
**Goal**: generate usable speech audio and assemble a chapter.

### Deliverables
- TTS adapter abstraction,
- first working local backend adapter,
- per-segment generation,
- segment render cache,
- chapter assembly service,
- pause insertion rules,
- speech-only chapter output,
- waveform/timeline view.

### Exit Criteria
- one chapter can be generated end-to-end with narrator + character voices.

---

## Phase 4 — Review, Patch, and QA (3–4 weeks)
**Goal**: make the output actually editable and debuggable.

### Deliverables
- segment regenerate action,
- render version history,
- issues table,
- clipping/loudness checks,
- attribution warnings,
- mark-reviewed workflow,
- comments on segments,
- chapter quality report.

### Exit Criteria
- user can selectively fix bad lines without rerendering the entire chapter.

---

## Phase 5 — Light Cinematic Layer & Export (3–4 weeks)
**Goal**: add restrained ambience and final packaging.

### Deliverables
- ambience profile suggestions,
- ambience stem generation/import,
- speech + ambience mix,
- export MP3/WAV,
- M4B packaging,
- metadata UI,
- sample clip export.

### Exit Criteria
- user can export a polished sample and a full chaptered draft.

---

## Phase 6 — Private Alpha Hardening (2–3 weeks)
**Goal**: stabilize MVP for real testers.

### Deliverables
- import reliability fixes,
- better error recovery,
- resumable failed jobs,
- performance profiling,
- cache improvements,
- debug bundle export,
- onboarding polish.

### Exit Criteria
- 5–10 external alpha users can successfully complete projects.

---

## Phase 7 — Hybrid/Cloud Transition (4–6 weeks)
**Goal**: evolve architecture without rewriting core logic.

### Deliverables
- Postgres support,
- object storage adapter,
- queue worker service,
- auth/RBAC foundation,
- multi-user project ownership,
- API hardening,
- deployment manifests.

### Exit Criteria
- same project pipeline runs in hosted mode with async workers.

---

## Phase 8 — Publisher Features (6–8 weeks)
**Goal**: support teams, rights, and review workflows.

### Deliverables
- organizations/users/roles,
- rights evidence workflows,
- review assignments,
- shared voice libraries,
- audit logs,
- export compliance checks,
- series glossary and pronunciation libraries.

### Exit Criteria
- a small publisher team can manage multiple titles with approvals.

---

## Phase 9 — Catalog Scale, Localization, API Platform (8–12 weeks)
**Goal**: support large backlists and integrations.

### Deliverables
- batch title ingestion,
- API keys,
- webhooks,
- title templates,
- localization workflows,
- cloud acceleration policies,
- analytics dashboards,
- fleet orchestration improvements.

### Exit Criteria
- enterprise customers can automate high-volume title pipelines.

---

## 18. Milestone Summary Table

| Milestone | Outcome |
|---|---|
| M0 | repo + runtime foundations |
| M1 | manuscript becomes structured project |
| M2 | stable voice bible + previews |
| M3 | chapter generation works |
| M4 | patch/review loop works |
| M5 | export polished draft |
| M6 | alpha-stable product |
| M7 | hosted multi-user pipeline |
| M8 | publisher workflows |
| M9 | catalog-scale platform |

---

## 19. Suggested Team by Phase

### Solo Founder / Tiny Team (M0–M5)
- 1 full-stack/product engineer
- 1 ML/audio engineer
- part-time design support or strong design system usage

### Small Team (M6–M8)
- 1 PM/founder
- 2 backend/platform engineers
- 1 frontend engineer
- 1 ML/audio engineer
- 1 QA/listening ops person

### Growth Team (M8+)
- rights/compliance specialist
- DevOps/platform engineer
- customer success / implementation support

---

## 20. Priority Order — What to Build First

If resources are limited, build in this strict order:
1. project + import + structure
2. character registry + voice assignment
3. segment generation
4. chapter assembly
5. segment patching
6. export
7. ambience
8. hosted collaboration
9. rights automation
10. enterprise scale features

Reason: **patchable chapter generation** is the core wedge. Everything else is secondary.

---

## 21. MVP Definition of Done
The MVP is engineering-complete when:
- a user can create a project locally,
- import a manuscript,
- review chapter/scene/segment structure,
- assign narrator and character voices,
- preview voices,
- generate a chapter,
- selectively regenerate bad segments,
- export chaptered audio,
- preserve project state across sessions,
- recover from common job failures without corrupting the project.

---

## 22. Final Product Readiness Definition
The platform is final-product ready when it additionally supports:
- multi-user collaboration,
- cloud workers and object storage,
- rights evidence and policy controls,
- review/approval workflows,
- series continuity tools,
- batch processing,
- localization,
- enterprise-grade auditability.

---

## 23. Immediate Next Build Artifacts
The next docs to create after this roadmap should be:
1. **ARCHITECTURE.md** — system overview and runtime diagrams
2. **DOMAIN_MODEL.md** — entities, relationships, lifecycle rules
3. **API_SPEC.yaml** — OpenAPI contract for MVP endpoints
4. **DB_SCHEMA.md** — migrations + table explanations
5. **PIPELINE_MANIFEST_SPEC.md** — manifest schemas for each processing stage
6. **VOICE_BIBLE_SPEC.md** — narrator/character profile structure
7. **QA_RULEBOOK.md** — automated and human review criteria
8. **MVP_EXECUTION_PLAN.md** — sprint-by-sprint breakdown

These should become the engineering operating docs for implementation.

