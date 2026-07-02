# Graph Report - .  (2026-07-02)

## Corpus Check
- 166 files · ~161,376 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1295 nodes · 3488 edges · 91 communities (79 shown, 12 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 507 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Domain Models|Domain Models]]
- [[_COMMUNITY_Ingestion Pipeline|Ingestion Pipeline]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Domain Models|Domain Models]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Speaker Attribution|Speaker Attribution]]
- [[_COMMUNITY_Voice Setup|Voice Setup]]
- [[_COMMUNITY_Database Models|Database Models]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Domain Models|Domain Models]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Chapter Assembly|Chapter Assembly]]
- [[_COMMUNITY_Character Bible|Character Bible]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Ingestion Pipeline|Ingestion Pipeline]]
- [[_COMMUNITY_Character Bible|Character Bible]]
- [[_COMMUNITY_Speaker Attribution|Speaker Attribution]]
- [[_COMMUNITY_Frontend App|Frontend App]]
- [[_COMMUNITY_Ingestion Pipeline|Ingestion Pipeline]]
- [[_COMMUNITY_Voice Setup|Voice Setup]]
- [[_COMMUNITY_Frontend App|Frontend App]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Domain Models|Domain Models]]
- [[_COMMUNITY_Voice Setup|Voice Setup]]
- [[_COMMUNITY_Direction Studio|Direction Studio]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Ingestion Pipeline|Ingestion Pipeline]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Domain Models|Domain Models]]
- [[_COMMUNITY_Domain Models|Domain Models]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Voice Setup|Voice Setup]]
- [[_COMMUNITY_Speaker Attribution|Speaker Attribution]]
- [[_COMMUNITY_Review Patching|Review Patching]]
- [[_COMMUNITY_Test Suite|Test Suite]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Frontend App|Frontend App]]
- [[_COMMUNITY_Export Packaging|Export Packaging]]
- [[_COMMUNITY_Review Patching|Review Patching]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Logging|Logging]]
- [[_COMMUNITY_Direction Studio|Direction Studio]]
- [[_COMMUNITY_Structure Parser|Structure Parser]]
- [[_COMMUNITY_Sound Design|Sound Design]]
- [[_COMMUNITY_TTS Rendering|TTS Rendering]]
- [[_COMMUNITY_UI Assets|UI Assets]]
- [[_COMMUNITY_Voice Setup|Voice Setup]]
- [[_COMMUNITY_Review Patching|Review Patching]]
- [[_COMMUNITY_Chapter Assembly|Chapter Assembly]]
- [[_COMMUNITY_Model Center|Model Center]]
- [[_COMMUNITY_Speaker Attribution|Speaker Attribution]]
- [[_COMMUNITY_Frontend App|Frontend App]]
- [[_COMMUNITY_Export Packaging|Export Packaging]]
- [[_COMMUNITY_Domain Models|Domain Models]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Frontend App|Frontend App]]
- [[_COMMUNITY_Implementation Plans|Implementation Plans]]
- [[_COMMUNITY_Code|Code]]
- [[_COMMUNITY_Architecture|Architecture]]
- [[_COMMUNITY_Character Bible|Character Bible]]
- [[_COMMUNITY_Code|Code]]

## God Nodes (most connected - your core abstractions)
1. `ApiModel` - 96 edges
2. `request()` - 78 edges
3. `AppContainer` - 67 edges
4. `SegmentRecord` - 51 edges
5. `ChapterAssembler` - 43 edges
6. `Database` - 43 edges
7. `Base` - 42 edges
8. `CastingRepository` - 42 edges
9. `ChapterRecord` - 41 edges
10. `SceneRecord` - 41 edges

## Surprising Connections (you probably didn't know these)
- `Segment Atomic Unit` --semantically_similar_to--> `Segment First Architecture`  [INFERRED] [semantically similar]
  README.md → docs/architecture.md
- `AssemblyInput` --uses--> `AmbienceAssetRecord`  [INFERRED]
  apps/api/src/echodraft_api/assembly.py → libs/db/src/echodraft_db/models.py
- `AssemblyInput` --uses--> `AmbienceCueRecord`  [INFERRED]
  apps/api/src/echodraft_api/assembly.py → libs/db/src/echodraft_db/models.py
- `AssemblyInput` --uses--> `ChapterRenderRecord`  [INFERRED]
  apps/api/src/echodraft_api/assembly.py → libs/db/src/echodraft_db/models.py
- `AssemblyInput` --uses--> `SceneRecord`  [INFERRED]
  apps/api/src/echodraft_api/assembly.py → libs/db/src/echodraft_db/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Segment First Patchable Workflow** — readme_segment_atomic_unit, docs_architecture_segment_first_architecture, docs_domain_model_segment, docs_domain_model_segment_render, docs_pipeline_manifest_spec_invalidation_rules [EXTRACTED 1.00]
- **Local AI Toolchain** — apps_api_src_echodraft_api_local_ai_model_catalog_poppler, apps_api_src_echodraft_api_local_ai_model_catalog_tesseract, apps_api_src_echodraft_api_local_ai_model_catalog_ollama, apps_api_src_echodraft_api_local_ai_model_catalog_kokoro_82m_onnx, docs_model_center_model_center [EXTRACTED 1.00]
- **MVP Pipeline Sequence** — implement_00_foundations_local_first_monorepo, implement_01_ingestion_source_document, implement_02_structure_extraction_chapter_scene_segment, implement_03_character_casting_voice_bible, implement_04_voice_direction_direction_profile, implement_05_segment_generation_segment_render, implement_06_chapter_assembly_chapter_render, implement_07_review_patching_selective_patch_flow, implement_09_export_export_package [EXTRACTED 1.00]

## Communities (91 total, 12 thin omitted)

### Community 0 - "Domain Models"
Cohesion: 0.06
Nodes (97): BaseModel, AmbienceAsset, AmbienceAssetCreate, AmbienceCue, AmbienceCueCreate, AmbienceProfile, AmbienceProfileCreate, ApiModel (+89 more)

### Community 1 - "Ingestion Pipeline"
Cohesion: 0.07
Nodes (36): CleaningChange, CleaningIssueDraft, CleaningPipeline, CleaningResult, IngestionError, IngestionService, PdfArtifactPaths, PdfPageExtraction (+28 more)

### Community 2 - "Structure Parser"
Cohesion: 0.06
Nodes (33): LocalLlmService, OllamaGenerateResult, OllamaProvider, SchemaValidationError, validate_json_schema(), _aliases(), CharacterIndex, _confidence() (+25 more)

### Community 3 - "Domain Models"
Cohesion: 0.09
Nodes (17): CatalogEntry, _is_winget_already_installed_message(), LocalAiService, LocalAiInstallation, LocalAiInstallJob, Path, find_ollama_model(), normalize_ollama_model_name() (+9 more)

### Community 4 - "Structure Parser"
Cohesion: 0.05
Nodes (30): assetUrl(), Chapter, Comment, Issue, listExports(), listRenderQueue(), LocalAiInstallJob, Project (+22 more)

### Community 5 - "Speaker Attribution"
Cohesion: 0.09
Nodes (15): ABC, Managed local Kokoro ONNX setup., KokoroTtsAdapter, ManagedKokoroOnnxAdapter, MockTtsAdapter, _piper_speaker_id(), PiperTtsAdapter, Path (+7 more)

### Community 6 - "Voice Setup"
Cohesion: 0.09
Nodes (18): managed_python_path(), ManagedKokoroPaths, ManagedKokoroSetupService, Path, install_payload(), patch_successful_install(), MonkeyPatch, Path (+10 more)

### Community 7 - "Database Models"
Cohesion: 0.11
Nodes (13): DeclarativeBase, AmbienceRepository, Database, Session, Apply safe, idempotent repairs for pre-migration local SQLite DBs.          Ea, AmbienceAssetRecord, AmbienceCueRecord, AmbienceProfileRecord (+5 more)

### Community 8 - "Structure Parser"
Cohesion: 0.14
Nodes (20): AssemblyInput, AppSettings, AppContainer, build_container(), apply_pronunciations(), Any, create_app(), Chapter-at-a-time orchestration over immutable segment renders. (+12 more)

### Community 9 - "Domain Models"
Cohesion: 0.15
Nodes (14): ExportPlan, ExportService, _int_value(), _json_dict(), _json_dict_from_value(), PlannedChapter, Any, Path (+6 more)

### Community 10 - "Structure Parser"
Cohesion: 0.05
Nodes (37): compareSegmentRenders(), deleteVoice(), getJob(), getKokoroSetup(), getLatestReadiness(), getLocalAiInstallJob(), getProductionSettings(), getSegmentDirection() (+29 more)

### Community 11 - "Structure Parser"
Cohesion: 0.06
Nodes (36): addComment(), assembleChapter(), createCharacter(), createExport(), createProject(), createPronunciation(), createSoundCue(), createVoice() (+28 more)

### Community 12 - "Structure Parser"
Cohesion: 0.06
Nodes (33): ChapterRender, Character, CleaningRun, Direction, ExportBlocker, ExportPackage, getProductionStatus(), getSegmentOverride() (+25 more)

### Community 13 - "Chapter Assembly"
Cohesion: 0.15
Nodes (6): ChapterAssembler, ChapterRender, Path, Session, Build immutable chapter stems from the current successful segment renders., SoundCueInput

### Community 14 - "Character Bible"
Cohesion: 0.19
Nodes (12): CastDiscoveryService, _character_names(), CharacterCandidate, CharacterIndex, _clamp_float(), _clean_strings(), _ignored_name(), _name_key() (+4 more)

### Community 15 - "Structure Parser"
Cohesion: 0.16
Nodes (12): MergeDecision, _json_dict(), ChapterBoundary, ChapterRecord, SceneRecord, SegmentRecord, SegmentRevisionRecord, StructureLockRecord (+4 more)

### Community 16 - "Ingestion Pipeline"
Cohesion: 0.07
Nodes (28): Poppler PDF Tools, Tesseract OCR, Manifest Driven Pipeline, Manuscript Intake UI, Review and Patch UI, Editable story map UI, Clean Text Review, Direction Studio (+20 more)

### Community 17 - "Character Bible"
Cohesion: 0.14
Nodes (8): CharacterRecord, CharacterVoiceAssignmentRecord, PronunciationEntryRecord, VoiceProfileRecord, CastingRepository, _clean_strings(), _list_from_json(), Any

### Community 18 - "Speaker Attribution"
Cohesion: 0.25
Nodes (6): CheckDraft, Any, Session, ReadinessService, ReadinessCheck, ReadinessReport

### Community 19 - "Frontend App"
Cohesion: 0.09
Nodes (22): dependencies, next, react, react-dom, devDependencies, eslint, eslint-config-next, @playwright/test (+14 more)

### Community 20 - "Ingestion Pipeline"
Cohesion: 0.27
Nodes (19): docx_bytes(), epub_bytes(), import_bytes(), pdf_bytes(), project_id(), MonkeyPatch, Path, test_cleaning_issues_flag_suspicious_tokens_and_can_be_resolved() (+11 more)

### Community 21 - "Voice Setup"
Cohesion: 0.12
Nodes (15): captureAssets(), chapters, __dirname, exports, frameDir, installRoutes(), issues, openChapter() (+7 more)

### Community 22 - "Frontend App"
Cohesion: 0.11
Nodes (17): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+9 more)

### Community 23 - "Code"
Cohesion: 0.26
Nodes (7): ProjectProductionSettingsRecord, ProjectRecord, RightsDeclarationRecord, SegmentProductionOverrideRecord, ProductionSettingsRepository, _project(), ProjectRepository

### Community 24 - "Code"
Cohesion: 0.28
Nodes (7): _install_job(), _installation(), LocalAiRepository, LocalAiInstallation, LocalAiInstallJob, ModelInstallationRecord, ModelInstallJobRecord

### Community 25 - "Domain Models"
Cohesion: 0.30
Nodes (3): DirectionService, SegmentDirection, DirectionProfile

### Community 26 - "Voice Setup"
Cohesion: 0.31
Nodes (5): Session, SegmentRenderer, SegmentRenderRecord, SegmentRender, SegmentRenderComparison

### Community 28 - "Structure Parser"
Cohesion: 0.47
Nodes (10): extract(), project_with_source(), test_cast_discovery_uses_aliases_without_creating_duplicates(), test_heading_scene_and_sentence_safe_segments(), test_invalid_llm_structure_refinement_falls_back_with_warning(), test_llm_structure_refinement_creates_cast_and_speaker_rows(), test_segment_split_merge_and_lock_survives_reextract(), test_structure_parser_v2_front_matter_dialogue_and_warnings() (+2 more)

### Community 29 - "Ingestion Pipeline"
Cohesion: 0.18
Nodes (11): Local-first monorepo foundation, SourceDocument implementation, Chapter Scene Segment hierarchy implementation, voice_bible.json implementation, DirectionProfile implementation, SegmentRender implementation, ChapterRender implementation, Selective patch flow implementation (+3 more)

### Community 30 - "Code"
Cohesion: 0.33
Nodes (3): InProcessJobRunner, Exception, Job

### Community 31 - "Domain Models"
Cohesion: 0.53
Nodes (3): TtsSettingsStore, TtsSettingsUpdate, TtsSettings

### Community 32 - "Domain Models"
Cohesion: 0.47
Nodes (4): _llm_run(), LlmRunRepository, LlmRunRecord, LlmRun

### Community 33 - "Code"
Cohesion: 0.31
Nodes (4): JobRecord, _job(), JobRepository, In-process jobs cannot safely resume after restart; fail them with guidance.

### Community 34 - "Code"
Cohesion: 0.31
Nodes (4): RenderQueueItemRecord, _render_queue_item(), RenderQueueRepository, RenderQueueItem

### Community 35 - "Voice Setup"
Cohesion: 0.40
Nodes (4): SegmentDirectionRecord, SegmentDirection, _segment_direction(), SegmentDirectionRepository

### Community 36 - "Speaker Attribution"
Cohesion: 0.47
Nodes (4): SpeakerAttributionRecord, SpeakerAttribution, _speaker_attribution(), SpeakerAttributionRepository

### Community 37 - "Review Patching"
Cohesion: 0.22
Nodes (4): Comment, Issue, PatchAttempt, SegmentReviewInspector

### Community 38 - "Test Suite"
Cohesion: 0.28
Nodes (4): create_payload(), Path, test_project_creation_persists_and_creates_artifact_layout(), test_startup_repairs_legacy_sqlite_production_columns()

### Community 39 - "Code"
Cohesion: 0.42
Nodes (3): SourceDocumentRecord, SourceDocumentRepository, SourceDocument

### Community 40 - "Frontend App"
Cohesion: 0.22
Nodes (8): name, private, scripts, web:dev, web:lint, web:test:smoke, web:typecheck, workspaces

### Community 41 - "Export Packaging"
Cohesion: 0.57
Nodes (7): project_with_chapter(), test_artifact_route_rejects_escape_and_segment_override(), test_export_estimate_marks_mixed_gate_and_m4b_as_planned(), test_export_refuses_open_blocking_issues(), test_production_settings_produce_download_and_export(), test_segment_render_cache_and_forced_lineage_are_append_only(), wait_for_job()

### Community 42 - "Review Patching"
Cohesion: 0.54
Nodes (7): prepared_segment(), render_payload(), test_issue_comment_and_selective_patch_preserve_render_history(), test_qa_issues_are_durable_and_deduplicated_per_render(), test_segment_review_inspector_layers_patch_history_and_waveform(), test_segment_revision_stales_only_the_edited_render(), wait_for_job()

### Community 44 - "Logging"
Cohesion: 0.47
Nodes (4): configure_logging(), JsonFormatter, Logger, LogRecord

### Community 45 - "Direction Studio"
Cohesion: 0.80
Nodes (4): direction(), project_with_segment(), test_segment_direction_changes_render_fingerprint(), wait_for_job()

### Community 46 - "Structure Parser"
Cohesion: 0.70
Nodes (4): structured_project(), test_readiness_report_persists_checks_and_issue_resolution(), test_readiness_reports_cast_voice_coverage_and_narrator_fallback(), wait_for_job()

### Community 47 - "Sound Design"
Cohesion: 0.70
Nodes (4): project_with_produced_chapter(), test_sound_design_import_assign_and_mix(), wait_for_job(), wav_bytes()

### Community 48 - "TTS Rendering"
Cohesion: 0.70
Nodes (3): project_with_segment(), test_render_queue_pronunciations_and_compare(), wait_for_job()

### Community 49 - "UI Assets"
Cohesion: 0.40
Nodes (5): Segment First Architecture, Echodraft production dashboard, Echodraft, Local First Architecture, Segment Atomic Unit

### Community 50 - "Voice Setup"
Cohesion: 0.50
Nodes (4): Kokoro 82M ONNX, Local voice system setup UI, Segment render queue items, Local TTS provider contract

### Community 52 - "Chapter Assembly"
Cohesion: 0.83
Nodes (3): test_chapter_assembly_pins_ordered_renders_and_emits_stem(), test_chapter_assembly_rejects_missing_segment_render(), wait_for_job()

### Community 53 - "Model Center"
Cohesion: 0.67
Nodes (3): Ollama Runtime, Local LLM Service, Model Center

### Community 56 - "Export Packaging"
Cohesion: 0.67
Nodes (3): Export Manifest, Export approval rules, Deterministic readiness reports

### Community 80 - "Domain Models"
Cohesion: 1.00
Nodes (3): echodraft-api, echodraft-db, echodraft-domain-models

## Knowledge Gaps
- **93 isolated node(s):** `ParserWarning`, `CleaningRun`, `KokoroSetupStep`, `LocalAiInstallation`, `SegmentOverride` (+88 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AppContainer` connect `Structure Parser` to `Ingestion Pipeline`, `Structure Parser`, `Domain Models`, `Speaker Attribution`, `Domain Models`, `Code`, `Chapter Assembly`, `Character Bible`, `Structure Parser`, `Speaker Attribution`, `Domain Models`, `Voice Setup`, `Direction Studio`, `Code`, `Domain Models`?**
  _High betweenness centrality (0.103) - this node is a cross-community bridge._
- **Why does `build_container()` connect `Structure Parser` to `Domain Models`, `Code`, `Code`, `Voice Setup`, `Speaker Attribution`, `Ingestion Pipeline`, `Database Models`, `Code`, `Code`, `Structure Parser`, `Character Bible`, `Code`, `Code`, `Code`, `Domain Models`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Why does `ApiModel` connect `Domain Models` to `Domain Models`, `Domain Models`, `Domain Models`, `Domain Models`, `Domain Models`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Are the 36 inferred relationships involving `AppContainer` (e.g. with `AssemblyInput` and `ChapterAssembler`) actually correct?**
  _`AppContainer` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `SegmentRecord` (e.g. with `AssemblyInput` and `ChapterAssembler`) actually correct?**
  _`SegmentRecord` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `ChapterAssembler` (e.g. with `AppContainer` and `ReviewService`) actually correct?**
  _`ChapterAssembler` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `FastAPI composition root for echodraft.`, `Build immutable chapter stems from the current successful segment renders.`, `Managed local Kokoro ONNX setup.` to the rest of the system?**
  _105 weakly-connected nodes found - possible documentation gaps or missing edges._