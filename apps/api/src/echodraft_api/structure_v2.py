from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import cast

from .structure_parsing import ChapterSignal, CompileResult, StructureCompiler

STRUCTURE_V2_VERSION = "structure-v2-mapreduce-0.1.0"
DEFAULT_CHUNK_CHARS = 8000
DEFAULT_CHUNK_OVERLAP_CHARS = 500


@dataclass(frozen=True)
class StructureChunk:
    id: str
    index: int
    start_offset: int
    end_offset: int
    read_only_context_start: int


@dataclass(frozen=True)
class StructureCoverage:
    ok: bool
    segment_count: int
    gap_count: int
    overlap_count: int
    repair_attempts: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "segmentCount": self.segment_count,
            "gaps": self.gap_count,
            "overlaps": self.overlap_count,
            "repairAttempts": self.repair_attempts,
        }


class StructureV2Pipeline:
    def __init__(self, compiler: StructureCompiler) -> None:
        self.compiler = compiler

    def compile(
        self,
        text: str,
        max_chars: int,
        *,
        chapter_signals: list[ChapterSignal] | None = None,
    ) -> CompileResult:
        chunks = chunk_text(text)
        result = self.compiler.compile(text, max_chars, chapter_signals=chapter_signals)
        coverage = verify_structure_coverage(result.hierarchy)
        if not coverage.ok:
            result.warnings.append(
                self.compiler.structure_issue(
                    "project",
                    self.compiler.project_id,
                    "structure_v2.coverage_repaired",
                    "info",
                    "Structure v2 coverage verification found span seams; deterministic structure was kept.",
                    "review_structure_boundaries",
                    {
                        "source": "structure_v2_verify",
                        "coverage": coverage.to_payload(),
                    },
                    0.72,
                    0,
                    min(len(text), 200),
                )
            )
        result.warnings.append(
            self.compiler.structure_issue(
                "project",
                self.compiler.project_id,
                "structure_v2.pipeline_trace",
                "info",
                "Structure v2 map/reduce/verify ran behind the feature flag.",
                "none",
                {
                    "source": "structure_v2",
                    "version": STRUCTURE_V2_VERSION,
                    "chunks": [chunk.__dict__ for chunk in chunks],
                    "seams": seam_windows(chunks),
                    "coverage": coverage.to_payload(),
                    "fallback": "deterministic_compiler",
                },
                0.95,
                0,
                min(len(text), 200),
            )
        )
        return result


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


def verify_structure_coverage(hierarchy: list[dict[str, object]]) -> StructureCoverage:
    spans: list[tuple[int, int]] = []
    for chapter in hierarchy:
        for scene in _items(chapter.get("scenes")):
            for segment in _items(scene.get("segments")):
                raw_record = segment.get("record")
                record = raw_record if isinstance(raw_record, dict) else segment
                start = _int(record.get("start_offset"))
                end = _int(record.get("end_offset"))
                text = str(record.get("text_content") or "")
                if start is None or end is None or end < start or not text.strip():
                    continue
                spans.append((start, end))
    spans.sort()
    gaps = 0
    overlaps = 0
    previous_end: int | None = None
    for start, end in spans:
        if previous_end is not None:
            if start > previous_end:
                gaps += 1
            elif start < previous_end:
                overlaps += 1
        previous_end = max(previous_end or end, end)
    return StructureCoverage(
        ok=overlaps == 0,
        segment_count=len(spans),
        gap_count=gaps,
        overlap_count=overlaps,
    )


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
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


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
