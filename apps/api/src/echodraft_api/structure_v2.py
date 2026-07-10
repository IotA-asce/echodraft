from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from echodraft_domain import LlmExtractionRequest, LlmExtractionResult

from .local_llm import LocalLlmService
from .structure_parsing import (
    ChapterSignal,
    CompileResult,
    StructureCompiler,
    _chapter_status_for_heading,
    _trim_span,
    safe_json,
    stable_id,
)

if TYPE_CHECKING:
    from .container import AppContainer

STRUCTURE_V2_VERSION = "structure-v2-mapreduce-1.0.0"
DEFAULT_CHUNK_CHARS = 8000
DEFAULT_CHUNK_OVERLAP_CHARS = 500
# MAP runs the small/fast model per chunk; REDUCE would use a larger model in
# production. Both default to the installed small model so no new model pull is
# required and the flag-gated path stays local-first.
STRUCTURE_V2_MAP_MODEL = "qwen3:4b"
STRUCTURE_V2_REDUCE_MODEL = "qwen3:4b"
MAX_REPAIR_ATTEMPTS = 2
# Two boundary offsets are treated as the same decision when they fall within
# this many characters of each other (paragraph-scale jitter across chunk seams).
BOUNDARY_MATCH_CHARS = 32

STRUCTURE_BOUNDARY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "boundaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "offset": {"type": "integer"},
                    "title": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["kind", "offset", "confidence"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["boundaries", "warnings"],
}


@dataclass(frozen=True)
class StructureChunk:
    id: str
    index: int
    start_offset: int
    end_offset: int
    read_only_context_start: int


@dataclass(frozen=True)
class ProposedBoundary:
    kind: str
    offset: int
    title: str
    confidence: float
    evidence: str
    chunk_index: int
    source: str


@dataclass(frozen=True)
class StructureCoverage:
    ok: bool
    segment_count: int
    gap_count: int
    overlap_count: int
    repair_attempts: int = 0
    gaps: tuple[tuple[int, int], ...] = field(default_factory=tuple)
    overlaps: tuple[tuple[int, int], ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "segmentCount": self.segment_count,
            "gaps": self.gap_count,
            "overlaps": self.overlap_count,
            "repairAttempts": self.repair_attempts,
            "gapSpans": [[start, end] for start, end in self.gaps],
            "overlapSpans": [[start, end] for start, end in self.overlaps],
        }


class StructureV2Pipeline:
    """LLM-first structure extraction: MAP per chunk, REDUCE over seams, then a
    deterministic coverage VERIFY with a bounded repair loop that fails closed to
    the deterministic v1 structure. See docs/architecture/extraction-pipeline-v2.md
    (S2. Structure v2)."""

    def __init__(
        self,
        compiler: StructureCompiler,
        *,
        container: AppContainer | None = None,
        job_id: str | None = None,
        llm_ready: bool = False,
    ) -> None:
        self.compiler = compiler
        self.container = container
        self.job_id = job_id
        self.llm_ready = llm_ready
        self.llm: LocalLlmService | None = (
            LocalLlmService(container) if container is not None else None
        )

    def compile(
        self,
        text: str,
        max_chars: int,
        *,
        chapter_signals: list[ChapterSignal] | None = None,
    ) -> CompileResult:
        chunks = chunk_text(text)
        seams = seam_windows(chunks)
        # v1 output is used both as MAP evidence and as the fail-closed fallback.
        v1_result = self.compiler.compile(text, max_chars, chapter_signals=chapter_signals)

        if not self.llm_ready or self.llm is None:
            return self._deterministic_result(v1_result, chunks, seams, text, "llm_not_ready")

        det_boundaries = _deterministic_boundaries(v1_result.hierarchy)
        map_results, map_diagnostics = self._map(chunks, text, det_boundaries)
        resolved, seam_decisions = self._reduce_seams(
            chunks, seams, map_results, det_boundaries, text
        )
        chapter_offsets, scene_offsets, boundary_titles = _aggregate_boundaries(
            map_results, seams, resolved, text
        )

        warnings: list[dict[str, object]] = []
        hierarchy = self._build_hierarchy(
            text, max_chars, chapter_offsets, scene_offsets, boundary_titles, warnings
        )
        hierarchy, coverage, repair_attempts, outcome = self._verify_and_repair(
            hierarchy=hierarchy,
            text=text,
            max_chars=max_chars,
            chapter_offsets=chapter_offsets,
            scene_offsets=scene_offsets,
            boundary_titles=boundary_titles,
            det_boundaries=det_boundaries,
            v1_result=v1_result,
            warnings=warnings,
        )
        warnings.append(
            self._pipeline_trace(
                text,
                chunks,
                seams,
                coverage,
                fallback=outcome,
                map_diagnostics=map_diagnostics,
                seam_decisions=seam_decisions,
                repair_attempts=repair_attempts,
            )
        )
        quality = self.compiler.quality(
            hierarchy, warnings, llm_used=True, accepted=0, rejected=0
        )
        return CompileResult(hierarchy=hierarchy, warnings=warnings, quality=quality)

    # -- deterministic (flag-on but LLM unavailable) --------------------------

    def _deterministic_result(
        self,
        v1_result: CompileResult,
        chunks: list[StructureChunk],
        seams: list[dict[str, int]],
        text: str,
        reason: str,
    ) -> CompileResult:
        warnings = list(v1_result.warnings)
        coverage = verify_structure_coverage(v1_result.hierarchy, text)
        warnings.append(
            self._pipeline_trace(
                text,
                chunks,
                seams,
                coverage,
                fallback="deterministic_compiler",
                map_diagnostics=[],
                seam_decisions=[],
                repair_attempts=0,
                reason=reason,
            )
        )
        return CompileResult(
            hierarchy=v1_result.hierarchy, warnings=warnings, quality=v1_result.quality
        )

    # -- MAP ------------------------------------------------------------------

    def _map(
        self,
        chunks: list[StructureChunk],
        text: str,
        det_boundaries: list[ProposedBoundary],
    ) -> tuple[dict[int, list[ProposedBoundary]], list[dict[str, object]]]:
        assert self.llm is not None
        project_id = self.compiler.project_id
        max_workers = min(
            len(chunks),
            self.container.orchestrator_pools.llm.max_workers if self.container else 1,
        )

        def map_chunk(
            chunk: StructureChunk,
        ) -> tuple[StructureChunk, LlmExtractionResult | ValueError]:
            request = LlmExtractionRequest(
                model=STRUCTURE_V2_MAP_MODEL,
                task="structure_map",
                schema=STRUCTURE_BOUNDARY_SCHEMA,
                prompt=self._map_prompt(chunk, text, det_boundaries),
            )
            try:
                assert self.llm is not None
                return chunk, self.llm.extract(project_id, request, self.job_id)
            except ValueError as error:
                return chunk, error

        outcomes: list[tuple[StructureChunk, LlmExtractionResult | ValueError]] = []
        with ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="echodraft-structure-map",
        ) as executor:
            futures = [executor.submit(map_chunk, chunk) for chunk in chunks]
            for future in futures:
                outcomes.append(future.result())

        map_results: dict[int, list[ProposedBoundary]] = {}
        diagnostics: list[dict[str, object]] = []
        for chunk, outcome in sorted(outcomes, key=lambda item: item[0].index):
            if self.job_id and self.container:
                self.container.jobs_repository.set_progress(
                    self.job_id,
                    {
                        "phase": "structure_v2_map",
                        "current": chunk.index,
                        "total": len(chunks),
                        "message": "Proposing chapter and scene boundaries per chunk.",
                    },
                )
            if isinstance(outcome, ValueError):
                # Fail closed for this chunk: keep the deterministic candidates.
                fallback = [
                    ProposedBoundary(
                        b.kind, b.offset, b.title, b.confidence, b.evidence, chunk.index, "det_fallback"
                    )
                    for b in det_boundaries
                    if chunk.start_offset <= b.offset < chunk.end_offset
                ]
                map_results[chunk.index] = fallback
                diagnostics.append(
                    {
                        "chunk": chunk.index,
                        "status": "llm_failed",
                        "error": str(outcome)[:300],
                        "boundaries": len(fallback),
                        "source": "det_fallback",
                    }
                )
                continue
            boundaries = self._parse_chunk_boundaries(chunk, outcome, text)
            map_results[chunk.index] = boundaries
            diagnostics.append(
                {
                    "chunk": chunk.index,
                    "status": "ok",
                    "llmRunId": outcome.run.id,
                    "boundaries": len(boundaries),
                    "source": "llm_map",
                }
            )
        return map_results, diagnostics

    def _parse_chunk_boundaries(
        self, chunk: StructureChunk, result: LlmExtractionResult, text: str
    ) -> list[ProposedBoundary]:
        raw = result.result.get("boundaries")
        if not isinstance(raw, list):
            return []
        chunk_len = chunk.end_offset - chunk.start_offset
        boundaries: list[ProposedBoundary] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip().lower()
            if kind not in {"chapter", "scene"}:
                continue
            rel = _int(item.get("offset"))
            if rel is None:
                continue
            rel = max(0, min(rel, chunk_len))
            absolute = chunk.start_offset + rel
            boundaries.append(
                ProposedBoundary(
                    kind=kind,
                    offset=absolute,
                    title=str(item.get("title") or "").strip(),
                    confidence=_clamp(item.get("confidence")),
                    evidence=str(item.get("evidence") or "")[:280],
                    chunk_index=chunk.index,
                    source="llm_map",
                )
            )
        return boundaries

    def _map_prompt(
        self, chunk: StructureChunk, text: str, det_boundaries: list[ProposedBoundary]
    ) -> str:
        chunk_text = text[chunk.start_offset : chunk.end_offset]
        prev_context = text[chunk.read_only_context_start : chunk.start_offset][-300:]
        det_lines = (
            "\n".join(
                f"- {b.kind} candidate at offset {b.offset - chunk.start_offset} "
                f"(deterministic confidence {b.confidence:.2f})"
                for b in det_boundaries
                if chunk.start_offset <= b.offset < chunk.end_offset
            )
            or "- (no deterministic candidates in this chunk)"
        )
        return (
            "You are detecting chapter and scene boundaries in one chunk of an "
            "audiobook manuscript.\n"
            "Offsets are relative to THIS chunk; offset 0 is the first character of "
            "the chunk text below.\n\n"
            "Return JSON only: a list of boundaries. Each boundary has kind "
            "('chapter' or 'scene'), offset (integer character position where the "
            "chapter/scene STARTS), a short title, a confidence in [0,1], and a short "
            "evidence string.\n\n"
            "Rules:\n"
            "- Return offsets and labels only. Never return manuscript text.\n"
            "- A boundary offset should fall on a paragraph start.\n"
            "- Use the deterministic candidates below as evidence; confirm them or "
            "override with a reason. They are hints, not decisions.\n"
            "- If the chunk continues the previous chunk's scene, do not emit a "
            "boundary at offset 0.\n\n"
            f"Deterministic candidates (chunk-relative offsets):\n{det_lines}\n\n"
            f"Previous chunk tail (read-only context):\n{prev_context}\n\n"
            f"Chunk text (offset 0 = first character):\n{chunk_text}"
        )

    # -- REDUCE ---------------------------------------------------------------

    def _reduce_seams(
        self,
        chunks: list[StructureChunk],
        seams: list[dict[str, int]],
        map_results: dict[int, list[ProposedBoundary]],
        det_boundaries: list[ProposedBoundary],
        text: str,
    ) -> tuple[list[ProposedBoundary], list[dict[str, object]]]:
        resolved: list[ProposedBoundary] = []
        decisions: list[dict[str, object]] = []
        for seam in seams:
            window_start = seam["startOffset"]
            window_end = seam["endOffset"]
            left = seam["leftChunk"]
            right = seam["rightChunk"]
            left_claims = _in_window(map_results.get(left, []), window_start, window_end)
            right_claims = _in_window(map_results.get(right, []), window_start, window_end)
            if window_end <= window_start:
                continue
            if _claims_agree(left_claims, right_claims):
                merged = _dedupe_boundaries(left_claims + right_claims)
                resolved.extend(merged)
                if merged:
                    decisions.append(
                        {
                            "seam": [left, right],
                            "window": [window_start, window_end],
                            "method": "agree",
                            "boundaries": len(merged),
                        }
                    )
                continue
            reconciled, method = self._reconcile_seam(
                window_start, window_end, left_claims, right_claims, det_boundaries, text
            )
            resolved.extend(reconciled)
            decisions.append(
                {
                    "seam": [left, right],
                    "window": [window_start, window_end],
                    "method": method,
                    "leftClaims": len(left_claims),
                    "rightClaims": len(right_claims),
                    "boundaries": len(reconciled),
                }
            )
        return resolved, decisions

    def _reconcile_seam(
        self,
        window_start: int,
        window_end: int,
        left_claims: list[ProposedBoundary],
        right_claims: list[ProposedBoundary],
        det_boundaries: list[ProposedBoundary],
        text: str,
    ) -> tuple[list[ProposedBoundary], str]:
        det_in_window = _in_window(det_boundaries, window_start, window_end)
        if self.llm is None:
            return _dedupe_boundaries(det_in_window), "det_tiebreak"
        request = LlmExtractionRequest(
            model=STRUCTURE_V2_REDUCE_MODEL,
            task="structure_seam_reduce",
            schema=STRUCTURE_BOUNDARY_SCHEMA,
            prompt=self._seam_prompt(
                window_start, window_end, left_claims, right_claims, det_in_window, text
            ),
        )
        try:
            result = self.llm.extract(self.compiler.project_id, request, self.job_id)
        except ValueError:
            # Deterministic tie-break: prefer the v1 candidate in the window.
            return _dedupe_boundaries(det_in_window), "det_tiebreak"
        reconciled = self._parse_seam_boundaries(result, window_start, window_end)
        return _dedupe_boundaries(reconciled), "llm"

    def _parse_seam_boundaries(
        self, result: LlmExtractionResult, window_start: int, window_end: int
    ) -> list[ProposedBoundary]:
        raw = result.result.get("boundaries")
        if not isinstance(raw, list):
            return []
        boundaries: list[ProposedBoundary] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip().lower()
            if kind not in {"chapter", "scene"}:
                continue
            offset = _int(item.get("offset"))
            if offset is None or not (window_start <= offset <= window_end):
                continue
            boundaries.append(
                ProposedBoundary(
                    kind=kind,
                    offset=offset,
                    title=str(item.get("title") or "").strip(),
                    confidence=_clamp(item.get("confidence")),
                    evidence=str(item.get("evidence") or "")[:280],
                    chunk_index=-1,
                    source="llm_reduce",
                )
            )
        return boundaries

    def _seam_prompt(
        self,
        window_start: int,
        window_end: int,
        left_claims: list[ProposedBoundary],
        right_claims: list[ProposedBoundary],
        det_in_window: list[ProposedBoundary],
        text: str,
    ) -> str:
        seam_text = text[window_start:window_end]

        def render(label: str, claims: list[ProposedBoundary]) -> str:
            if not claims:
                return f"{label}: (none)"
            return f"{label}:\n" + "\n".join(
                f"  - {b.kind} at absolute offset {b.offset} (confidence {b.confidence:.2f})"
                for b in claims
            )

        return (
            "Two adjacent manuscript chunks disagree about boundaries inside their "
            "overlapping seam window. Reconcile them into one authoritative set.\n"
            "Offsets below are ABSOLUTE source character positions.\n\n"
            "Return JSON only: the final list of boundaries for this window. Each has "
            "kind ('chapter' or 'scene'), offset (absolute integer), title, confidence, "
            "and evidence. Return offsets and labels only, never manuscript text.\n"
            "Merge duplicates and drop spurious boundaries; a single logical boundary "
            "must appear once.\n\n"
            f"Seam window: absolute offsets [{window_start}, {window_end}].\n"
            f"{render('Left chunk claims', left_claims)}\n"
            f"{render('Right chunk claims', right_claims)}\n"
            f"{render('Deterministic candidates', det_in_window)}\n\n"
            f"Seam text:\n{seam_text}"
        )

    # -- build ----------------------------------------------------------------

    def _build_hierarchy(
        self,
        text: str,
        max_chars: int,
        chapter_offsets: list[int],
        scene_offsets: list[int],
        boundary_titles: dict[int, str],
        warnings: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        offsets = sorted({0, *[o for o in chapter_offsets if 0 < o < len(text)]})
        hierarchy: list[dict[str, object]] = []
        for chapter_index, chapter_start in enumerate(offsets):
            chapter_end = offsets[chapter_index + 1] if chapter_index + 1 < len(offsets) else len(text)
            chapter_text = text[chapter_start:chapter_end]
            if not chapter_text.strip():
                continue
            title = boundary_titles.get(chapter_start) or f"Chapter {len(hierarchy) + 1}"
            status, matter_type = _chapter_status_for_heading(title)
            chapter_id = stable_id("chap", self.compiler.source_id, chapter_start, chapter_end, title)
            scene_starts = sorted(
                {chapter_start, *[o for o in scene_offsets if chapter_start < o < chapter_end]}
            )
            scenes: list[dict[str, object]] = []
            for scene_index, scene_start in enumerate(scene_starts):
                scene_end = (
                    scene_starts[scene_index + 1]
                    if scene_index + 1 < len(scene_starts)
                    else chapter_end
                )
                scene = self._build_scene(
                    chapter_id, len(scenes), scene_start, scene_end, text, max_chars, warnings
                )
                if scene is not None:
                    scenes.append(scene)
            if not scenes:
                continue
            evidence: dict[str, object] = {
                "reason": "structure_v2_llm_boundary",
                "parserVersion": self.compiler.parser_version,
                "source": "structure_v2_map_reduce",
                **({"matterType": matter_type} if matter_type else {}),
            }
            hierarchy.append(
                {
                    "record": {
                        "id": chapter_id,
                        "project_id": self.compiler.project_id,
                        "order_index": len(hierarchy),
                        "title": title,
                        "start_offset": chapter_start,
                        "end_offset": chapter_end,
                        "confidence": 0.9,
                        "status": status,
                        "parser_evidence_json": safe_json(evidence),
                    },
                    "scenes": scenes,
                }
            )
        return hierarchy

    def _build_scene(
        self,
        chapter_id: str,
        order_index: int,
        scene_start: int,
        scene_end: int,
        text: str,
        max_chars: int,
        warnings: list[dict[str, object]],
    ) -> dict[str, object] | None:
        raw = text[scene_start:scene_end]
        trimmed_start, trimmed_end, trimmed_text = _trim_span(raw, scene_start, scene_end)
        if not trimmed_text:
            return None
        scene_id = stable_id(
            "scene", self.compiler.source_id, trimmed_start, trimmed_end, trimmed_text[:160]
        )
        # LLM decides the boundary; segmentation inside the scene stays deterministic.
        atoms = self.compiler.atoms_for_scene(trimmed_text, trimmed_start, warnings, scene_id)
        segments = self.compiler.segments_from_atoms(scene_id, atoms, max_chars, warnings)
        evidence: dict[str, object] = {
            "reason": "structure_v2_llm_scene",
            "parserVersion": self.compiler.parser_version,
            "source": "structure_v2_map_reduce",
        }
        return {
            "record": {
                "id": scene_id,
                "chapter_id": chapter_id,
                "order_index": order_index,
                "start_offset": trimmed_start,
                "end_offset": trimmed_end,
                "confidence": 0.88,
                "status": "structured",
                "parser_evidence_json": safe_json(evidence),
            },
            "segments": segments,
            "_atoms": atoms,
            "_scene_text": trimmed_text,
            "_base": trimmed_start,
        }

    # -- verify + repair ------------------------------------------------------

    def _verify_and_repair(
        self,
        *,
        hierarchy: list[dict[str, object]],
        text: str,
        max_chars: int,
        chapter_offsets: list[int],
        scene_offsets: list[int],
        boundary_titles: dict[int, str],
        det_boundaries: list[ProposedBoundary],
        v1_result: CompileResult,
        warnings: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], StructureCoverage, int, str]:
        coverage = verify_structure_coverage(hierarchy, text)
        attempts = 0
        while not coverage.ok and attempts < MAX_REPAIR_ATTEMPTS:
            attempts += 1
            regions = list(coverage.gaps) + list(coverage.overlaps)
            repaired = self._repair_regions(text, regions, det_boundaries)
            for boundary in repaired:
                if boundary.kind == "chapter":
                    chapter_offsets.append(boundary.offset)
                else:
                    scene_offsets.append(boundary.offset)
                if boundary.title:
                    boundary_titles.setdefault(boundary.offset, boundary.title)
            repaired_warnings: list[dict[str, object]] = []
            hierarchy = self._build_hierarchy(
                text, max_chars, chapter_offsets, scene_offsets, boundary_titles, repaired_warnings
            )
            warnings[:] = repaired_warnings
            coverage = verify_structure_coverage(hierarchy, text)

        coverage = StructureCoverage(
            ok=coverage.ok,
            segment_count=coverage.segment_count,
            gap_count=coverage.gap_count,
            overlap_count=coverage.overlap_count,
            repair_attempts=attempts,
            gaps=coverage.gaps,
            overlaps=coverage.overlaps,
        )
        if coverage.ok:
            return hierarchy, coverage, attempts, "none" if attempts == 0 else "repaired"

        # Fail closed: ship the deterministic v1 structure so no source text is
        # ever left uncovered, and fold the affected spans into one review task.
        self._record_coverage_fallback(coverage, warnings)
        warnings[:] = list(v1_result.warnings) + warnings
        fallback_coverage = verify_structure_coverage(v1_result.hierarchy, text)
        fallback_coverage = StructureCoverage(
            ok=fallback_coverage.ok,
            segment_count=fallback_coverage.segment_count,
            gap_count=fallback_coverage.gap_count,
            overlap_count=fallback_coverage.overlap_count,
            repair_attempts=attempts,
            gaps=fallback_coverage.gaps,
            overlaps=fallback_coverage.overlaps,
        )
        return v1_result.hierarchy, fallback_coverage, attempts, "deterministic_v1_region"

    def _repair_regions(
        self,
        text: str,
        regions: list[tuple[int, int]],
        det_boundaries: list[ProposedBoundary],
    ) -> list[ProposedBoundary]:
        if self.llm is None or not regions:
            return []
        repaired: list[ProposedBoundary] = []
        for region_start, region_end in regions:
            request = LlmExtractionRequest(
                model=STRUCTURE_V2_REDUCE_MODEL,
                task="structure_repair",
                schema=STRUCTURE_BOUNDARY_SCHEMA,
                prompt=self._repair_prompt(region_start, region_end, text),
            )
            try:
                result = self.llm.extract(self.compiler.project_id, request, self.job_id)
            except ValueError:
                continue
            repaired.extend(
                self._parse_seam_boundaries(result, region_start, max(region_end, region_start))
            )
        return repaired

    def _repair_prompt(self, region_start: int, region_end: int, text: str) -> str:
        region_text = text[region_start:region_end]
        return (
            "The coverage verifier found a region that is not covered by exactly one "
            "segment (a gap or overlap). Re-propose chapter/scene boundaries for this "
            "region using ABSOLUTE offsets so every character is covered once.\n\n"
            "Return JSON only: boundaries with kind ('chapter'/'scene'), offset "
            "(absolute integer), title, confidence, evidence. Never return manuscript "
            "text.\n\n"
            f"Region: absolute offsets [{region_start}, {region_end}].\n\n"
            f"Region text:\n{region_text}"
        )

    def _record_coverage_fallback(
        self, coverage: StructureCoverage, warnings: list[dict[str, object]]
    ) -> None:
        regions = list(coverage.gaps) + list(coverage.overlaps)
        first_start = regions[0][0] if regions else 0
        first_end = regions[0][1] if regions else 0
        warnings.append(
            self.compiler.structure_issue(
                "project",
                self.compiler.project_id,
                "structure_v2.coverage_fallback",
                "warning",
                "Structure v2 coverage could not be verified after repair; the "
                "deterministic structure was shipped for the affected spans.",
                "review_structure_boundaries",
                {
                    "source": "structure_v2_verify",
                    "coverage": coverage.to_payload(),
                },
                0.6,
                first_start,
                first_end,
            )
        )
        if self.container is None:
            return
        members: list[dict[str, object]] = [
            {"ref": f"coverage:{start}:{end}", "span": [start, end]}
            for start, end in regions
        ]
        if not members:
            return
        self.container.review.fold_review_task(
            project_id=self.compiler.project_id,
            cause_key="structure_v2_coverage",
            category="structure",
            scope_type="project",
            scope_id=self.compiler.project_id,
            title=f"{len(members)} structure spans need coverage review",
            members=members,
            evidence={"version": STRUCTURE_V2_VERSION, "coverage": coverage.to_payload()},
        )

    # -- manifest -------------------------------------------------------------

    def _pipeline_trace(
        self,
        text: str,
        chunks: list[StructureChunk],
        seams: list[dict[str, int]],
        coverage: StructureCoverage,
        *,
        fallback: str,
        map_diagnostics: list[dict[str, object]],
        seam_decisions: list[dict[str, object]],
        repair_attempts: int,
        reason: str | None = None,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "source": "structure_v2",
            "version": STRUCTURE_V2_VERSION,
            "chunks": [chunk.__dict__ for chunk in chunks],
            "seams": seams,
            "coverage": coverage.to_payload(),
            "map": map_diagnostics,
            "seamDecisions": seam_decisions,
            "repairAttempts": repair_attempts,
            "fallback": fallback,
        }
        if reason:
            evidence["reason"] = reason
        return self.compiler.structure_issue(
            "project",
            self.compiler.project_id,
            "structure_v2.pipeline_trace",
            "info",
            "Structure v2 map/reduce/verify ran behind the feature flag.",
            "none",
            evidence,
            0.95,
            0,
            min(len(text), 200),
        )


def chunk_text(
    text: str,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[StructureChunk]:
    if not text:
        return [
            StructureChunk(
                id="chunk_0001",
                index=1,
                start_offset=0,
                end_offset=0,
                read_only_context_start=0,
            )
        ]
    chunks: list[StructureChunk] = []
    start = 0
    while start < len(text):
        target_end = min(len(text), start + chunk_chars)
        end = _paragraph_boundary(text, start, target_end)
        if end <= start:
            end = target_end
        chunks.append(
            StructureChunk(
                id=f"chunk_{len(chunks) + 1:04d}",
                index=len(chunks) + 1,
                start_offset=start,
                end_offset=end,
                read_only_context_start=max(0, start - overlap_chars),
            )
        )
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def seam_windows(chunks: list[StructureChunk]) -> list[dict[str, int]]:
    seams: list[dict[str, int]] = []
    for left, right in zip(chunks, chunks[1:]):
        seams.append(
            {
                "leftChunk": left.index,
                "rightChunk": right.index,
                "startOffset": right.read_only_context_start,
                "endOffset": min(left.end_offset, right.end_offset),
            }
        )
    return seams


def verify_structure_coverage(
    hierarchy: list[dict[str, object]], text: str | None = None
) -> StructureCoverage:
    """Coverage invariant (design S2 VERIFY): the readable segment spans must
    partition ``[0, len(text))`` — no gaps, no overlaps, monotonic. Whitespace-only
    gaps are tolerated. ``ok`` requires zero overlaps AND zero non-whitespace gaps
    AND (when ``text`` is supplied) coverage through the end of the canonical text."""
    canonical_len = len(text) if text is not None else None
    spans: list[tuple[int, int]] = []
    for chapter in hierarchy:
        for scene in _items(chapter.get("scenes")):
            for segment in _items(scene.get("segments")):
                raw_record = segment.get("record")
                record = raw_record if isinstance(raw_record, dict) else segment
                start = _int(record.get("start_offset"))
                end = _int(record.get("end_offset"))
                content = str(record.get("text_content") or "")
                if start is None or end is None or end < start or not content.strip():
                    continue
                spans.append((start, end))
    spans.sort()
    raw_gaps: list[tuple[int, int]] = []
    overlaps: list[tuple[int, int]] = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            raw_gaps.append((cursor, start))
        elif start < cursor:
            overlaps.append((start, min(cursor, end)))
        cursor = max(cursor, end)
    if canonical_len is not None and cursor < canonical_len:
        raw_gaps.append((cursor, canonical_len))
    gaps: list[tuple[int, int]] = []
    for gap_start, gap_end in raw_gaps:
        if text is not None and not text[gap_start:gap_end].strip():
            continue
        gaps.append((gap_start, gap_end))
    return StructureCoverage(
        ok=not gaps and not overlaps,
        segment_count=len(spans),
        gap_count=len(gaps),
        overlap_count=len(overlaps),
        gaps=tuple(gaps),
        overlaps=tuple(overlaps),
    )


def _deterministic_boundaries(hierarchy: list[dict[str, object]]) -> list[ProposedBoundary]:
    boundaries: list[ProposedBoundary] = []
    for chapter in hierarchy:
        record = chapter.get("record")
        if isinstance(record, dict):
            start = _int(record.get("start_offset"))
            if start is not None:
                boundaries.append(
                    ProposedBoundary(
                        "chapter",
                        start,
                        str(record.get("title") or ""),
                        _clamp(record.get("confidence")),
                        "v1_chapter",
                        -1,
                        "det",
                    )
                )
        for scene in _items(chapter.get("scenes")):
            scene_record = scene.get("record")
            if not isinstance(scene_record, dict):
                continue
            start = _int(scene_record.get("start_offset"))
            if start is not None:
                boundaries.append(
                    ProposedBoundary(
                        "scene",
                        start,
                        "",
                        _clamp(scene_record.get("confidence")),
                        "v1_scene",
                        -1,
                        "det",
                    )
                )
    return boundaries


def _aggregate_boundaries(
    map_results: dict[int, list[ProposedBoundary]],
    seams: list[dict[str, int]],
    resolved: list[ProposedBoundary],
    text: str,
) -> tuple[list[int], list[int], dict[int, str]]:
    windows = [(seam["startOffset"], seam["endOffset"]) for seam in seams]
    aggregated: list[ProposedBoundary] = []
    for boundaries in map_results.values():
        for boundary in boundaries:
            if _in_any_window(boundary.offset, windows):
                continue
            aggregated.append(boundary)
    aggregated.extend(resolved)
    chapters = _dedupe_boundaries([b for b in aggregated if b.kind == "chapter"])
    scenes = _dedupe_boundaries([b for b in aggregated if b.kind == "scene"])
    titles: dict[int, str] = {}
    for boundary in chapters:
        if boundary.title:
            titles[boundary.offset] = boundary.title
    chapter_offsets = [b.offset for b in chapters if 0 <= b.offset < len(text)]
    scene_offsets = [b.offset for b in scenes if 0 <= b.offset < len(text)]
    return chapter_offsets, scene_offsets, titles


def _dedupe_boundaries(boundaries: list[ProposedBoundary]) -> list[ProposedBoundary]:
    ordered = sorted(boundaries, key=lambda b: (b.offset, -b.confidence))
    kept: list[ProposedBoundary] = []
    for boundary in ordered:
        if any(
            existing.kind == boundary.kind
            and abs(existing.offset - boundary.offset) <= BOUNDARY_MATCH_CHARS
            for existing in kept
        ):
            continue
        kept.append(boundary)
    return kept


def _claims_agree(left: list[ProposedBoundary], right: list[ProposedBoundary]) -> bool:
    def matched(source: list[ProposedBoundary], other: list[ProposedBoundary]) -> bool:
        for boundary in source:
            if not any(
                candidate.kind == boundary.kind
                and abs(candidate.offset - boundary.offset) <= BOUNDARY_MATCH_CHARS
                for candidate in other
            ):
                return False
        return True

    return matched(left, right) and matched(right, left)


def _in_window(
    boundaries: list[ProposedBoundary], window_start: int, window_end: int
) -> list[ProposedBoundary]:
    return [b for b in boundaries if window_start <= b.offset <= window_end]


def _in_any_window(offset: int, windows: list[tuple[int, int]]) -> bool:
    return any(start <= offset <= end for start, end in windows)


def _paragraph_boundary(text: str, start: int, target_end: int) -> int:
    if target_end >= len(text):
        return len(text)
    window = text[start:target_end]
    matches = list(re.finditer(r"\n\s*\n", window))
    if matches:
        return start + matches[-1].end()
    return target_end


def _items(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _clamp(value: object, minimum: float = 0.0, maximum: float = 1.0) -> float:
    if isinstance(value, bool):
        return minimum
    if isinstance(value, (int, float)):
        return min(max(float(value), minimum), maximum)
    if isinstance(value, str):
        try:
            return min(max(float(value), minimum), maximum)
        except ValueError:
            return minimum
    return minimum


def structure_v2_manifest_payload(warnings: list[dict[str, object]]) -> dict[str, object] | None:
    for warning in warnings:
        try:
            evidence = json.loads(str(warning.get("evidence_json") or "{}"))
        except json.JSONDecodeError:
            return None
        if evidence.get("code") != "structure_v2.pipeline_trace":
            continue
        return cast(dict[str, object], evidence)
    return None
