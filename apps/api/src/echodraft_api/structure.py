import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from echodraft_db.models import (
    ChapterRecord,
    CharacterRecord,
    IssueRecord,
    SceneRecord,
    SegmentRecord,
    SegmentRevisionRecord,
    StructureParserWarningRecord,
)
from echodraft_domain import (
    Chapter,
    LlmExtractionRequest,
    Scene,
    Segment,
    SegmentRevision,
    StructureQuality,
)
from sqlalchemy import select

from .container import AppContainer
from .local_llm import LocalLlmService
from .structure_parsing import (
    ALLOWED_PRODUCTION_TYPES,
    SegmentDraft,
    StructureCompiler,
    TextAtom,
    compatible_segment_type,
    ignored_speaker,
)

STRUCTURE_PARSER_VERSION = "structure-parser-0.4.0"
DEFAULT_REFINEMENT_MODEL = "qwen3:4b"
DEFAULT_REFINEMENT_MODEL_KEY = "qwen3_4b_ollama"
LLM_REFINEMENT_BATCH_CHARS = 3200

ATOM_SEGMENT_REFINEMENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "atomIds": {"type": "array", "items": {"type": "string"}},
                    "segmentType": {"type": "string"},
                    "speakerHint": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": [
                    "atomIds",
                    "segmentType",
                    "speakerHint",
                    "confidence",
                    "evidence",
                ],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["segments", "warnings"],
}


class StructureService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def extract(self, project_id: str, max_chars: int, job_id: str | None = None) -> None:
        source = self.container.sources.latest(project_id)
        project = self.container.projects.get(project_id)
        if not source or not source.canonical_path or not project:
            raise ValueError("A successfully imported canonical source is required.")
        text = Path(source.canonical_path).read_text(encoding="utf-8")
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id,
                {
                    "phase": "block_map",
                    "message": "Compiling manuscript blocks and production atoms locally.",
                },
            )
        compiler = StructureCompiler(project_id, source.id, STRUCTURE_PARSER_VERSION)
        compiled = compiler.compile(text, max_chars)
        hierarchy = compiled.hierarchy
        warnings = compiled.warnings
        llm_used, accepted, rejected = self._refine_hierarchy(
            project_id, source.id, compiler, hierarchy, warnings, job_id
        )
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id, {"phase": "saving_structure", "message": "Saving production planner draft."}
            )
        self.container.structure.replace(project_id, hierarchy, warnings)
        self._run_cast_and_speaker_draft(project_id, source.id, job_id)
        quality = self.quality(
            project_id,
            hierarchy=hierarchy,
            warnings=warnings,
            llm_used=llm_used,
            llm_accepted=accepted,
            llm_rejected=rejected,
        )
        self._write_manifest(project_id, source.id, max_chars, hierarchy, warnings, quality)

    def quality(
        self,
        project_id: str,
        *,
        hierarchy: list[dict[str, object]] | None = None,
        warnings: list[dict[str, object]] | None = None,
        llm_used: bool | None = None,
        llm_accepted: int | None = None,
        llm_rejected: int | None = None,
    ) -> StructureQuality:
        manifest_quality = self._manifest_quality(project_id)
        if hierarchy is None:
            live = self._live_quality(project_id)
            if manifest_quality:
                live.update(
                    {
                        "llmRefinementUsed": manifest_quality.get("llmRefinementUsed", False),
                        "llmAcceptedBatchCount": manifest_quality.get("llmAcceptedBatchCount", 0),
                        "llmRejectedBatchCount": manifest_quality.get("llmRejectedBatchCount", 0),
                    }
                )
            return StructureQuality.model_validate(live)

        compiler = StructureCompiler(project_id, self._latest_source_id(project_id), STRUCTURE_PARSER_VERSION)
        payload = compiler.quality(
            hierarchy,
            warnings or [],
            llm_used=bool(llm_used),
            accepted=llm_accepted or 0,
            rejected=llm_rejected or 0,
        )
        live_cast = self._live_cast_quality(project_id)
        payload.update(live_cast)
        return StructureQuality.model_validate(payload)

    def _refine_hierarchy(
        self,
        project_id: str,
        source_id: str,
        compiler: StructureCompiler,
        hierarchy: list[dict[str, object]],
        warnings: list[dict[str, object]],
        job_id: str | None,
    ) -> tuple[bool, int, int]:
        ready, message = self._local_llm_ready()
        if not ready:
            warnings.append(
                compiler.structure_issue(
                    "project",
                    project_id,
                    "llm.not_available",
                    "info",
                    "Local LLM atom grouping was not run; deterministic production segments were kept.",
                    "install_or_verify_local_llm",
                    {
                        "source": "optional_atom_llm_grouping",
                        "model": DEFAULT_REFINEMENT_MODEL,
                        "reason": message or "Local Ollama model is not ready.",
                    },
                    0.8,
                    0,
                    0,
                )
            )
            return False, 0, 0

        llm = LocalLlmService(self.container)
        accepted = 0
        rejected = 0
        for chapter in hierarchy:
            scenes = cast(list[dict[str, object]], chapter.get("scenes", []))
            for scene in scenes:
                raw_atoms = scene.get("_atoms")
                atoms = [
                    atom for atom in raw_atoms if isinstance(atom, TextAtom)
                ] if isinstance(raw_atoms, list) else []
                if not atoms:
                    continue
                scene_id = str(cast(dict[str, object], scene["record"])["id"])
                refined_records: list[dict[str, object]] = []
                batch_rejected = False
                batches = _atom_batches(atoms)
                for batch_index, batch in enumerate(batches, 1):
                    if job_id:
                        self.container.jobs_repository.set_progress(
                            job_id,
                            {
                                "phase": "optional_atom_llm_grouping",
                                "current": batch_index,
                                "total": len(batches),
                                "message": "Grouping source-preserving atoms with local Ollama.",
                            },
                        )
                    try:
                        result = llm.extract(
                            project_id,
                            LlmExtractionRequest(
                                model=DEFAULT_REFINEMENT_MODEL,
                                task="atom_segment_refinement",
                                schema=ATOM_SEGMENT_REFINEMENT_SCHEMA,
                                prompt=self._atom_refinement_prompt(atoms, batch),
                            ),
                            job_id,
                        )
                    except ValueError as error:
                        warnings.append(
                            compiler.structure_issue(
                                "scene",
                                scene_id,
                                "llm.validation_failed",
                                "warning",
                                "Local LLM atom grouping failed; deterministic segments were kept.",
                                "review_deterministic_segments",
                                {
                                    "source": "optional_atom_llm_grouping",
                                    "error": str(error)[:500],
                                    "atomIds": [atom.id for atom in batch],
                                },
                                0.55,
                                batch[0].start_offset,
                                batch[-1].end_offset,
                            )
                        )
                        rejected += 1
                        batch_rejected = True
                        break
                    raw_segments = result.result.get("segments")
                    if not isinstance(raw_segments, list):
                        warnings.append(
                            compiler.structure_issue(
                                "scene",
                                scene_id,
                                "llm.validation_failed",
                                "warning",
                                "Local LLM atom grouping returned no segment list; deterministic segments were kept.",
                                "review_deterministic_segments",
                                {
                                    "source": "optional_atom_llm_grouping",
                                    "llmRunId": result.run.id,
                                },
                                0.55,
                                batch[0].start_offset,
                                batch[-1].end_offset,
                            )
                        )
                        rejected += 1
                        batch_rejected = True
                        break
                    refined = self._validated_atom_refinement(
                        compiler,
                        scene_id,
                        batch,
                        cast(list[dict[str, object]], raw_segments),
                        result.run.id,
                        warnings,
                    )
                    if refined is None:
                        rejected += 1
                        batch_rejected = True
                        break
                    accepted += 1
                    refined_records.extend(refined)
                if batch_rejected:
                    continue
                for index, segment in enumerate(refined_records):
                    segment["order_index"] = index
                scene["segments"] = refined_records
        return True, accepted, rejected

    def _validated_atom_refinement(
        self,
        compiler: StructureCompiler,
        scene_id: str,
        atoms: list[TextAtom],
        llm_segments: list[dict[str, object]],
        run_id: str,
        warnings: list[dict[str, object]],
    ) -> list[dict[str, object]] | None:
        atom_by_id = {atom.id: atom for atom in atoms}
        expected_order = [atom.id for atom in atoms]
        flattened: list[str] = []
        groups: list[tuple[list[TextAtom], str, str | None, float, str]] = []
        scene_text = " ".join(atom.text for atom in atoms)
        for payload in llm_segments:
            atom_ids = payload.get("atomIds")
            if not isinstance(atom_ids, list) or not atom_ids:
                self._reject_atom_refinement(compiler, scene_id, atoms, run_id, warnings, "missing atomIds")
                return None
            ids = [str(atom_id) for atom_id in atom_ids]
            if any(atom_id not in atom_by_id for atom_id in ids):
                self._reject_atom_refinement(compiler, scene_id, atoms, run_id, warnings, "invented atom id")
                return None
            group_positions = [expected_order.index(atom_id) for atom_id in ids]
            if group_positions != list(range(group_positions[0], group_positions[0] + len(ids))):
                self._reject_atom_refinement(
                    compiler, scene_id, atoms, run_id, warnings, "non-adjacent atom grouping"
                )
                return None
            production_type = str(payload.get("segmentType") or "narration")
            if production_type not in ALLOWED_PRODUCTION_TYPES:
                self._reject_atom_refinement(
                    compiler, scene_id, atoms, run_id, warnings, "unsupported segment type"
                )
                return None
            speaker_hint = str(payload.get("speakerHint") or "").strip() or None
            if speaker_hint and (
                ignored_speaker(speaker_hint)
                or (
                    speaker_hint.casefold() not in scene_text.casefold()
                    and not any(speaker_hint == atom.speaker_hint for atom in atoms)
                )
            ):
                self._reject_atom_refinement(compiler, scene_id, atoms, run_id, warnings, "unsafe speaker hint")
                return None
            confidence = _clamp_float(payload.get("confidence"), 0.0, 1.0)
            evidence = str(payload.get("evidence") or "")
            groups.append(([atom_by_id[atom_id] for atom_id in ids], production_type, speaker_hint, confidence, evidence))
            flattened.extend(ids)

        if flattened != expected_order or len(flattened) != len(set(flattened)):
            self._reject_atom_refinement(compiler, scene_id, atoms, run_id, warnings, "atom coverage mismatch")
            return None

        records: list[dict[str, object]] = []
        for index, (group, production_type, speaker_hint, confidence, llm_evidence) in enumerate(groups):
            speaker = speaker_hint
            speaker_confidence = confidence if speaker_hint else 0.0
            if not speaker and any(atom.kind == "quote" for atom in group):
                quote_index = atoms.index(next(atom for atom in group if atom.kind == "quote"))
                speaker, speaker_confidence, _evidence = compiler.resolve_atom_speaker(atoms, quote_index)
            segment_type = compatible_segment_type(production_type)
            status = (
                "ready"
                if segment_type != "dialogue" or (speaker and speaker_confidence >= 0.8)
                else "needs_review"
            )
            text = " ".join(atom.text for atom in group).strip()
            draft = SegmentDraft(
                atom_ids=[atom.id for atom in group],
                segment_type=segment_type,
                production_type=production_type,
                text=text,
                start_offset=group[0].start_offset,
                end_offset=group[-1].end_offset,
                speaker_hint=speaker,
                speaker_confidence=speaker_confidence,
                confidence=confidence,
                status=status,
                evidence={
                    "sources": [
                        "block_map",
                        "quote_aware_atomization",
                        "deterministic_segment_builder",
                        "optional_atom_llm_grouping",
                    ],
                    "llmRunId": run_id,
                    "llmEvidence": llm_evidence,
                    "llmConfidence": confidence,
                    "atomKinds": [atom.kind for atom in group],
                    "atomSpeakerHints": [
                        {
                            "name": atom.speaker_hint,
                            "confidence": atom.speaker_confidence,
                            "kind": atom.kind,
                        }
                        for atom in group
                        if atom.speaker_hint
                    ],
                },
            )
            records.append(compiler.segment_record(scene_id, index, compiler.review_segment_draft(draft, warnings)))
        return records

    def _reject_atom_refinement(
        self,
        compiler: StructureCompiler,
        scene_id: str,
        atoms: list[TextAtom],
        run_id: str,
        warnings: list[dict[str, object]],
        reason: str,
    ) -> None:
        warnings.append(
            compiler.structure_issue(
                "scene",
                scene_id,
                "llm.validation_failed",
                "warning",
                "Local LLM atom grouping failed validation; deterministic segments were kept.",
                "review_deterministic_segments",
                {
                    "source": "optional_atom_llm_grouping",
                    "llmRunId": run_id,
                    "reason": reason,
                    "atomIds": [atom.id for atom in atoms],
                },
                0.55,
                atoms[0].start_offset,
                atoms[-1].end_offset,
            )
        )
        return None

    def _atom_refinement_prompt(self, scene_atoms: list[TextAtom], batch: list[TextAtom]) -> str:
        first_index = scene_atoms.index(batch[0])
        last_index = scene_atoms.index(batch[-1])
        previous_text = scene_atoms[first_index - 1].text[-240:] if first_index else ""
        next_text = scene_atoms[last_index + 1].text[:240] if last_index + 1 < len(scene_atoms) else ""
        atom_lines = "\n".join(
            (
                f"ATOM {atom.id} kind={atom.kind} speaker={atom.speaker_hint or ''} "
                f"confidence={atom.confidence:.2f} text={json.dumps(atom.text)}"
            )
            for atom in batch
        )
        return (
            "You are refining an audiobook production structure.\n\n"
            "You will receive source-preserving text atoms from one scene. Each atom has an ID, "
            "kind guess, optional speaker hint, and exact text. Return JSON only.\n\n"
            "Rules:\n"
            "- Do not return manuscript text.\n"
            "- Do not invent atom IDs.\n"
            "- Do not drop atoms.\n"
            "- Do not duplicate atoms.\n"
            "- Preserve atom order exactly.\n"
            "- Group adjacent atoms into renderable audiobook segments.\n"
            "- A dialogue segment should contain one speaker only.\n"
            "- Use speakerHint only when explicitly observed or strongly implied nearby.\n"
            "- If uncertain, leave speakerHint empty and lower confidence.\n\n"
            f"Previous context:\n{previous_text}\n\n"
            f"Next context:\n{next_text}\n\n"
            f"Atoms:\n{atom_lines}"
        )

    def _run_cast_and_speaker_draft(
        self, project_id: str, source_id: str, job_id: str | None
    ) -> None:
        ready, _message = self._local_llm_ready()
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id,
                {"phase": "cast_discovery", "message": "Discovering cast from production segments."},
            )
        from .cast_discovery import CastDiscoveryService
        from .speaker_attribution import SpeakerAttributionService

        CastDiscoveryService(self.container).discover(
            project_id, source_id=source_id, use_local_llm=ready, job_id=job_id
        )
        if job_id:
            self.container.jobs_repository.set_progress(
                job_id,
                {"phase": "speaker_attribution", "message": "Linking speakers to cast records."},
            )
        try:
            SpeakerAttributionService(self.container).generate(
                project_id, use_local_llm=ready, model=DEFAULT_REFINEMENT_MODEL, job_id=job_id
            )
        except ValueError as error:
            self.container.review.create_issue(
                project_id=project_id,
                category="cast_discovery",
                severity="warning",
                title="LLM speaker attribution needs review",
                description="Local LLM speaker attribution failed after deterministic rows were created.",
                metadata={
                    "sourceDocumentId": source_id,
                    "model": DEFAULT_REFINEMENT_MODEL,
                    "error": str(error)[:500],
                },
                dedupe_key=f"cast-speaker-llm:{project_id}:{source_id}",
            )

    def _write_manifest(
        self,
        project_id: str,
        source_id: str,
        max_chars: int,
        hierarchy: list[dict[str, object]],
        warnings: list[dict[str, object]],
        quality: StructureQuality,
    ) -> None:
        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")
        manifest = {
            "manifestType": "structure_manifest",
            "schemaVersion": "0.2.0",
            "projectId": project_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "status": "completed",
            "diagnostics": [
                {
                    "severity": warning["severity"],
                    "scopeType": warning["scope_type"],
                    "scopeId": warning["scope_id"],
                    "message": warning["message"],
                    "evidence": _evidence(str(warning["evidence_json"])),
                    "confidence": warning["confidence"],
                }
                for warning in warnings
            ],
            "payload": {
                "sourceDocumentId": source_id,
                "maxSegmentChars": max_chars,
                "parserVersion": STRUCTURE_PARSER_VERSION,
                "pipeline": [
                    "block_map",
                    "chapter_candidate_scoring",
                    "scene_candidate_scoring",
                    "quote_aware_atomization",
                    "deterministic_segment_builder",
                    "optional_atom_llm_grouping",
                    "cast_discovery",
                    "speaker_attribution",
                ],
                "quality": quality.model_dump(by_alias=True),
                "chapters": _manifest_hierarchy(hierarchy),
            },
        }
        root = Path(project.artifact_path) / "manifests"
        version = root / f"structure_manifest.{uuid4().hex[:12]}.json"
        version.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (root / "structure_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _local_llm_ready(self) -> tuple[bool, str | None]:
        installation = self.container.local_ai.installation(DEFAULT_REFINEMENT_MODEL_KEY)
        if installation and installation.status == "installed":
            return True, "Local Ollama model is marked installed in Model Center."
        return False, "Ollama model qwen3:4b is not marked installed in Model Center."

    def _latest_source_id(self, project_id: str) -> str:
        source = self.container.sources.latest(project_id)
        return source.id if source else project_id

    def _manifest_quality(self, project_id: str) -> dict[str, object]:
        project = self.container.projects.get(project_id)
        if not project:
            return {}
        path = Path(project.artifact_path) / "manifests" / "structure_manifest.json"
        if not path.exists():
            return {}
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        payload = manifest.get("payload") if isinstance(manifest, dict) else None
        quality = payload.get("quality") if isinstance(payload, dict) else None
        return cast(dict[str, object], quality) if isinstance(quality, dict) else {}

    def _live_quality(self, project_id: str) -> dict[str, object]:
        with self.container.structure.database.session() as session:
            chapters = list(
                session.scalars(select(ChapterRecord).where(ChapterRecord.project_id == project_id))
            )
            chapter_ids = [chapter.id for chapter in chapters]
            scenes = list(
                session.scalars(select(SceneRecord).where(SceneRecord.chapter_id.in_(chapter_ids)))
            ) if chapter_ids else []
            scene_ids = [scene.id for scene in scenes]
            segments = list(
                session.scalars(select(SegmentRecord).where(SegmentRecord.scene_id.in_(scene_ids)))
            ) if scene_ids else []
            warnings = list(
                session.scalars(
                    select(StructureParserWarningRecord).where(
                        StructureParserWarningRecord.project_id == project_id,
                        StructureParserWarningRecord.resolved.is_(False),
                    )
                )
            )
            characters = list(
                session.scalars(
                    select(CharacterRecord).where(
                        CharacterRecord.project_id == project_id,
                        CharacterRecord.merged_into_character_id.is_(None),
                    )
                )
            )
            issues = list(
                session.scalars(
                    select(IssueRecord).where(
                        IssueRecord.project_id == project_id,
                        IssueRecord.status == "open",
                    )
                )
            )
        dialogue = [segment for segment in segments if segment.segment_type == "dialogue"]
        unresolved = [
            segment
            for segment in dialogue
            if not segment.speaker_candidate or segment.speaker_confidence < 0.8
        ]
        warning_codes = [_warning_record_code(warning) for warning in warnings]
        issue_codes = [_issue_record_code(issue) for issue in issues]
        total_chars = sum(len(segment.text_content) for segment in segments)
        attributed_dialogue = len(dialogue) - len(unresolved)
        return {
            "chapterCount": len(chapters),
            "sceneCount": len(scenes),
            "segmentCount": len(segments),
            "dialogueSegmentCount": len(dialogue),
            "dialogueAttributionCoverage": round((attributed_dialogue / len(dialogue)) * 100, 1) if dialogue else 100.0,
            "unresolvedDialogueCount": len(unresolved),
            "averageSegmentChars": round(total_chars / len(segments), 1) if segments else 0,
            "longSegmentCount": sum(1 for segment in segments if len(segment.text_content) > 900),
            "mixedSegmentWarningCount": warning_codes.count("segment.mixed_dialogue_and_narration"),
            "castCandidateCount": len(characters),
            "possibleDuplicateCastCount": issue_codes.count("cast.possible_duplicate"),
            "lowConfidenceCastCandidateCount": issue_codes.count("cast.low_confidence_candidate")
            or sum(1 for character in characters if character.confidence < 0.72),
            "possibleSceneBreakCount": warning_codes.count("scene.possible_break_detected"),
            "offsetValidationFailureCount": warning_codes.count("segment.offset_validation_failed"),
            "quoteUnclosedCount": warning_codes.count("segment.quote_unclosed"),
            "warningsNeedingReviewCount": sum(
                1 for warning in warnings if warning.severity in {"warning", "blocking", "error"}
            ),
            "llmRefinementUsed": False,
            "llmAcceptedBatchCount": 0,
            "llmRejectedBatchCount": 0,
        }

    def _live_cast_quality(self, project_id: str) -> dict[str, object]:
        with self.container.structure.database.session() as session:
            characters = list(
                session.scalars(
                    select(CharacterRecord).where(
                        CharacterRecord.project_id == project_id,
                        CharacterRecord.merged_into_character_id.is_(None),
                    )
                )
            )
            issues = list(
                session.scalars(
                    select(IssueRecord).where(
                        IssueRecord.project_id == project_id,
                        IssueRecord.status == "open",
                    )
                )
            )
        issue_codes = [_issue_record_code(issue) for issue in issues]
        return {
            "castCandidateCount": len(characters),
            "possibleDuplicateCastCount": issue_codes.count("cast.possible_duplicate"),
            "lowConfidenceCastCandidateCount": issue_codes.count("cast.low_confidence_candidate")
            or sum(1 for character in characters if character.confidence < 0.72),
        }


def _atom_batches(atoms: list[TextAtom]) -> list[list[TextAtom]]:
    batches: list[list[TextAtom]] = []
    current: list[TextAtom] = []
    current_chars = 0
    for atom in atoms:
        length = len(atom.text)
        if current and current_chars + length > LLM_REFINEMENT_BATCH_CHARS:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(atom)
        current_chars += length
    if current:
        batches.append(current)
    return batches


def _manifest_hierarchy(hierarchy: list[dict[str, object]]) -> list[dict[str, object]]:
    chapters: list[dict[str, object]] = []
    for chapter in hierarchy:
        chapter_record = cast(dict[str, object], chapter["record"])
        scenes: list[dict[str, object]] = []
        for scene in cast(list[dict[str, object]], chapter.get("scenes", [])):
            scene_record = cast(dict[str, object], scene["record"])
            scenes.append(
                {
                    "record": scene_record,
                    "segments": cast(list[dict[str, object]], scene.get("segments", [])),
                }
            )
        chapters.append({"record": chapter_record, "scenes": scenes})
    return chapters


def _warning_record_code(warning: StructureParserWarningRecord) -> str:
    evidence = _evidence(warning.evidence_json)
    return str(evidence.get("code") or "")


def _issue_record_code(issue: IssueRecord) -> str:
    evidence = _evidence(issue.metadata_json)
    return str(evidence.get("code") or "")


def _clamp_float(value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, (int, float, str)):
        try:
            numeric = float(value)
        except ValueError:
            numeric = minimum
    else:
        numeric = minimum
    return min(max(numeric, minimum), maximum)


def _evidence(payload: str | None) -> dict[str, object]:
    try:
        loaded = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], loaded if isinstance(loaded, dict) else {})


def chapter_model(record: ChapterRecord) -> Chapter:
    return Chapter.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "orderIndex": record.order_index,
            "title": record.title,
            "confidence": record.confidence,
            "startOffset": record.start_offset,
            "endOffset": record.end_offset,
            "status": record.status,
            "parserEvidence": _evidence(record.parser_evidence_json),
            "userLocked": record.user_locked,
            "lockReason": record.lock_reason,
        }
    )


def scene_model(record: SceneRecord) -> Scene:
    return Scene.model_validate(
        {
            "id": record.id,
            "chapterId": record.chapter_id,
            "orderIndex": record.order_index,
            "confidence": record.confidence,
            "startOffset": record.start_offset,
            "endOffset": record.end_offset,
            "status": record.status,
            "parserEvidence": _evidence(record.parser_evidence_json),
            "userLocked": record.user_locked,
            "lockReason": record.lock_reason,
        }
    )


def segment_model(record: SegmentRecord) -> Segment:
    return Segment.model_validate(
        {
            "id": record.id,
            "sceneId": record.scene_id,
            "orderIndex": record.order_index,
            "textContent": record.text_content,
            "normalizedText": record.normalized_text,
            "segmentType": record.segment_type,
            "speakerCandidate": record.speaker_candidate,
            "speakerConfidence": record.speaker_confidence,
            "startOffset": record.start_offset,
            "endOffset": record.end_offset,
            "revision": record.revision,
            "status": record.status,
            "parserEvidence": _evidence(record.parser_evidence_json),
            "userLocked": record.user_locked,
            "lockReason": record.lock_reason,
        }
    )


def revision_model(record: SegmentRevisionRecord) -> SegmentRevision:
    return SegmentRevision.model_validate(
        {
            "id": record.id,
            "segmentId": record.segment_id,
            "revision": record.revision,
            "textContent": record.text_content,
            "createdAt": record.created_at,
        }
    )
