from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime


HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Dr|Prof|Professor|Captain|Capt|Sir|Lady|Lord)\.?"
NAME_TOKEN = r"[A-Z][A-Za-z]+(?:[-'][A-Z]?[A-Za-z]+)?"
PROPER_NAME = rf"(?:{HONORIFIC}\s+)?{NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,3}}"
ROLE_NAME = (
    r"(?:the\s+)?(?:old man|old woman|boy|girl|man|woman|doctor|captain|mother|"
    r"father|mom|dad)"
)
SPEAKER_PATTERN = rf"(?:{PROPER_NAME}|{ROLE_NAME})"
SPEECH_VERBS = (
    "said",
    "asked",
    "replied",
    "whispered",
    "shouted",
    "murmured",
    "called",
    "answered",
    "cried",
    "yelled",
    "continued",
    "added",
    "told",
    "insisted",
    "said softly",
)
SPEECH_VERB_PATTERN = "|".join(re.escape(verb) for verb in SPEECH_VERBS)
EXPLICIT_CHAPTER_RE = re.compile(
    r"^(?:chapter\s+(?:\d+|[ivxlcdm]+|[a-z]+)|prologue|epilogue|afterword|"
    r"acknowledg(?:e)?ments|part\s+(?:\d+|[ivxlcdm]+|[a-z]+)|book\s+"
    r"(?:\d+|[ivxlcdm]+|[a-z]+))\b",
    re.IGNORECASE,
)
SEPARATOR_RE = re.compile(r"^\s*(?:\*[\s*]{2,}|-{3,}|-[\s-]{2,}|—[\s—]{2,})\s*$")
SCENE_LINE_RE = re.compile(r"^\s*(?:scene\s+\d+\b.*|#{4,}\s+.+)\s*$", re.IGNORECASE)
TIME_SHIFT_RE = re.compile(
    r"^(?:later|that night|the next morning|the next day|at dawn|by dusk|"
    r"meanwhile|after midnight|before sunrise|at\s+\d{1,2}(?::\d{2})?\s*(?:a\.m\.|p\.m\.)?)\b",
    re.IGNORECASE,
)
TAG_BEFORE_RE = re.compile(
    rf"^\s*(?P<speaker>{SPEAKER_PATTERN})\s+(?:{SPEECH_VERB_PATTERN})\b(?:,|\.)?\s*$",
    re.IGNORECASE,
)
TAG_AFTER_RE = re.compile(
    rf"^\s*(?:(?P<speaker_before>{SPEAKER_PATTERN})\s+(?:{SPEECH_VERB_PATTERN})|"
    rf"(?:{SPEECH_VERB_PATTERN})\s+(?P<speaker_after>{SPEAKER_PATTERN}))\b[^.!?]*[.!?,]?\s*$",
    re.IGNORECASE,
)
COLON_SPEAKER_RE = re.compile(rf"^\s*(?P<speaker>{SPEAKER_PATTERN}):\s+", re.IGNORECASE)
SENTENCE_RE = re.compile(r".+?(?:[.!?]+(?:[\"'”’])?|$)(?:\s+|$)", re.DOTALL)
ABBREVIATION_TAIL_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof|Professor|Capt|St)\.$")
IGNORED_SPEAKER_CANDIDATES = {
    "he",
    "she",
    "they",
    "we",
    "you",
    "i",
    "it",
    "narrator",
    "someone",
    "everyone",
    "no one",
    "this",
    "that",
    "there",
    "what",
    "when",
    "where",
    "why",
    "how",
}
ROLE_SPEAKER_KEYS = {
    "the old man",
    "old man",
    "the old woman",
    "old woman",
    "boy",
    "girl",
    "man",
    "woman",
    "doctor",
    "captain",
    "the captain",
    "mother",
    "father",
    "mom",
    "dad",
}
ALLOWED_PRODUCTION_TYPES = {
    "narration",
    "dialogue",
    "dialogue_with_tag",
    "action_beat",
    "performance_beat",
    "heading",
}
# Chapter signals extracted from container structure (DOCX heading styles, EPUB
# spine/TOC) rather than from in-text keyword headings. Only these source kinds
# mark a chapter as container-derived.
CONTAINER_SIGNAL_KINDS = ("docx_heading", "epub_toc", "epub_spine")


@dataclass(frozen=True)
class ChapterSignal:
    """A chapter boundary hint recovered from a container's structural metadata.

    Resolution is by anchor text, never by raw offsets: cleaning/normalization
    shifts character positions, so signals are matched against parsed blocks by
    case-insensitive, whitespace-collapsed text equality.
    """

    title: str
    source_kind: str
    level: int
    anchor_text: str
    confidence: float

    def to_payload(self) -> dict[str, object]:
        return {
            "title": self.title,
            "sourceKind": self.source_kind,
            "level": self.level,
            "anchorText": self.anchor_text,
            "confidence": self.confidence,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ChapterSignal":
        level = payload.get("level")
        confidence = payload.get("confidence")
        return cls(
            title=str(payload.get("title") or ""),
            source_kind=str(payload.get("sourceKind") or ""),
            level=int(level) if isinstance(level, (int, float, str)) else 0,
            anchor_text=str(payload.get("anchorText") or ""),
            confidence=float(confidence) if isinstance(confidence, (int, float, str)) else 0.0,
        )


def normalize_anchor(value: str) -> str:
    """Collapse whitespace and casefold so anchor text compares stably."""
    return re.sub(r"\s+", " ", value).strip().casefold()


@dataclass(frozen=True)
class TextBlock:
    id: str
    kind: str
    text: str
    start_offset: int
    end_offset: int
    line_start: int
    line_end: int
    confidence: float
    evidence: dict[str, object]


@dataclass(frozen=True)
class ChapterCandidate:
    start: int
    content_start: int
    end: int | None
    title: str
    confidence: float
    status: str
    evidence: dict[str, object]


@dataclass(frozen=True)
class SceneCandidate:
    start: int
    end: int
    title: str | None
    confidence: float
    status: str
    evidence: dict[str, object]


@dataclass(frozen=True)
class TextAtom:
    id: str
    kind: str
    text: str
    start_offset: int
    end_offset: int
    speaker_hint: str | None
    speaker_confidence: float
    confidence: float
    evidence: dict[str, object]


@dataclass(frozen=True)
class QuoteScan:
    spans: list[tuple[int, int]]
    unclosed_start: int | None = None
    unclosed_char: str | None = None


@dataclass(frozen=True)
class AtomOffsetValidation:
    valid: bool
    errors: list[str]
    uncovered_ranges: list[tuple[int, int]]
    overlapping_ranges: list[tuple[int, int]]


@dataclass(frozen=True)
class SegmentDraft:
    atom_ids: list[str]
    segment_type: str
    production_type: str
    text: str
    start_offset: int
    end_offset: int
    speaker_hint: str | None
    speaker_confidence: float
    confidence: float
    status: str
    evidence: dict[str, object]


@dataclass(frozen=True)
class CompileResult:
    hierarchy: list[dict[str, object]]
    warnings: list[dict[str, object]]
    quality: dict[str, object]


def stable_id(prefix: str, source_id: str, start: int, end: int, text: str) -> str:
    digest = hashlib.sha1(f"{source_id}:{start}:{end}:{text}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def ignored_speaker(value: str | None) -> bool:
    if not value:
        return True
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    if normalized.startswith(("the ", "a ", "an ")) and normalized not in ROLE_SPEAKER_KEYS:
        return True
    return normalized in IGNORED_SPEAKER_CANDIDATES


def compatible_segment_type(production_type: str) -> str:
    if production_type == "performance_beat":
        return "performance_beat"
    if production_type in {"dialogue", "dialogue_with_tag"}:
        return "dialogue"
    return "narration"


def safe_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True)


def validate_atom_offsets(
    scene_text: str, base: int, atoms: list[TextAtom]
) -> AtomOffsetValidation:
    scene_start = base
    scene_end = base + len(scene_text)
    previous_end = scene_start
    errors: list[str] = []
    covered_ranges: list[tuple[int, int]] = []
    overlapping_ranges: list[tuple[int, int]] = []

    def add_error(code: str) -> None:
        if code not in errors:
            errors.append(code)

    for atom in atoms:
        if atom.start_offset < scene_start or atom.end_offset > scene_end:
            add_error("out_of_bounds")
        if atom.start_offset > atom.end_offset:
            add_error("invalid_span")
        if atom.start_offset < previous_end:
            add_error("non_monotonic_order")
        if atom.start_offset < previous_end and atom.end_offset > atom.start_offset:
            overlap_end = min(atom.end_offset, previous_end)
            if overlap_end > atom.start_offset:
                overlapping_ranges.append((atom.start_offset, overlap_end))
                add_error("overlapping_atoms")
        if scene_start <= atom.start_offset <= atom.end_offset <= scene_end:
            source_slice = scene_text[atom.start_offset - base : atom.end_offset - base]
            if source_slice.strip() != atom.text.strip():
                add_error("source_slice_mismatch")
            if atom.end_offset > atom.start_offset:
                covered_ranges.append((atom.start_offset, atom.end_offset))
        previous_end = max(previous_end, atom.end_offset)

    uncovered_ranges = _uncovered_non_whitespace_ranges(scene_text, base, covered_ranges)
    if uncovered_ranges:
        add_error("uncovered_source_text")
    return AtomOffsetValidation(
        valid=not errors,
        errors=errors,
        uncovered_ranges=uncovered_ranges,
        overlapping_ranges=overlapping_ranges,
    )


def atom_offsets_valid(scene_text: str, base: int, atoms: list[TextAtom]) -> bool:
    return validate_atom_offsets(scene_text, base, atoms).valid


def _uncovered_non_whitespace_ranges(
    scene_text: str, base: int, ranges: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    scene_start = base
    scene_end = base + len(scene_text)
    cursor = scene_start
    uncovered: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if start > cursor:
            gap = scene_text[cursor - base : start - base]
            if gap.strip():
                uncovered.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < scene_end:
        gap = scene_text[cursor - base : scene_end - base]
        if gap.strip():
            uncovered.append((cursor, scene_end))
    return uncovered


class StructureCompiler:
    def __init__(self, project_id: str, source_id: str, parser_version: str) -> None:
        self.project_id = project_id
        self.source_id = source_id
        self.parser_version = parser_version

    def compile(
        self,
        text: str,
        max_chars: int,
        chapter_signals: list[ChapterSignal] | None = None,
    ) -> CompileResult:
        warnings: list[dict[str, object]] = []
        blocks = self.block_map(text)
        chapters = self.chapter_candidates(blocks, text, chapter_signals, warnings)
        if not chapters:
            chapter_id = stable_id("chap", self.source_id, 0, len(text), text[:180])
            chapters = [
                ChapterCandidate(
                    start=0,
                    content_start=0,
                    end=len(text),
                    title="Unresolved chapter",
                    confidence=0.35,
                    status="unresolved",
                    evidence={
                        "reason": "no_confirmed_heading",
                        "parserVersion": self.parser_version,
                    },
                )
            ]
            warnings.append(
                self.structure_issue(
                    "chapter",
                    chapter_id,
                    "chapter.no_confirmed_heading",
                    "warning",
                    "No reliable chapter heading was found.",
                    "confirm_chapter_heading",
                    {"startOffset": 0, "endOffset": min(len(text), 200), "textPreview": text[:160]},
                    0.35,
                    0,
                    min(len(text), 200),
                )
            )
        elif chapters[0].start > 0 and text[: chapters[0].start].strip():
            chapters.insert(
                0,
                ChapterCandidate(
                    start=0,
                    content_start=0,
                    end=chapters[0].start,
                    title="Front matter",
                    confidence=0.74,
                    status="front_matter",
                    evidence={
                        "reason": "text_before_first_confirmed_heading",
                        "parserVersion": self.parser_version,
                    },
                ),
            )

        hierarchy: list[dict[str, object]] = []
        for chapter_index, chapter in enumerate(chapters):
            end = chapters[chapter_index + 1].start if chapter_index + 1 < len(chapters) else len(text)
            if chapter.end is not None:
                end = chapter.end
            chapter_id = stable_id("chap", self.source_id, chapter.start, end, chapter.title)
            chapter_text = text[chapter.content_start:end]
            chapter_blocks = [
                block
                for block in blocks
                if block.start_offset >= chapter.content_start and block.end_offset <= end
            ]
            scenes = self.scenes(
                chapter_id,
                chapter_text,
                chapter_blocks,
                chapter.content_start,
                max_chars,
                warnings,
            )
            hierarchy.append(
                {
                    "record": {
                        "id": chapter_id,
                        "project_id": self.project_id,
                        "order_index": chapter_index,
                        "title": chapter.title,
                        "start_offset": chapter.start,
                        "end_offset": end,
                        "confidence": chapter.confidence,
                        "status": chapter.status,
                        "parser_evidence_json": safe_json(chapter.evidence),
                    },
                    "scenes": scenes,
                }
            )

        quality = self.quality(hierarchy, warnings, llm_used=False, accepted=0, rejected=0)
        return CompileResult(hierarchy=hierarchy, warnings=warnings, quality=quality)

    def block_map(self, text: str) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        offset = 0
        for line_index, raw_line in enumerate(text.splitlines(keepends=True), 1):
            line_text = raw_line[:-1] if raw_line.endswith("\n") else raw_line
            block_text = line_text.strip()
            start = offset
            end = offset + len(line_text)
            kind, confidence, evidence = self._classify_block(block_text, blocks)
            blocks.append(
                TextBlock(
                    id=stable_id("block", self.source_id, start, end, block_text),
                    kind=kind,
                    text=block_text,
                    start_offset=start,
                    end_offset=end,
                    line_start=line_index,
                    line_end=line_index,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
            offset += len(raw_line)
        if not text.endswith("\n") and not blocks:
            blocks.append(
                TextBlock(
                    id=stable_id("block", self.source_id, 0, 0, ""),
                    kind="blank",
                    text="",
                    start_offset=0,
                    end_offset=0,
                    line_start=1,
                    line_end=1,
                    confidence=1.0,
                    evidence={"reason": "empty_document"},
                )
            )
        return blocks

    def chapter_candidates(
        self,
        blocks: list[TextBlock],
        text: str,
        chapter_signals: list[ChapterSignal] | None = None,
        warnings: list[dict[str, object]] | None = None,
    ) -> list[ChapterCandidate]:
        candidates_by_start: dict[int, ChapterCandidate] = {}
        for index, block in enumerate(blocks):
            if block.kind != "heading":
                continue
            markdown_level = block.evidence.get("markdownLevel")
            explicit = bool(EXPLICIT_CHAPTER_RE.match(_strip_markdown_heading(block.text)))
            if not explicit:
                continue
            title = _chapter_title_from_heading(_strip_markdown_heading(block.text))
            content_start = block.end_offset
            evidence = {
                **block.evidence,
                "parserVersion": self.parser_version,
                "reason": "explicit_chapter_heading",
                "sourceBlockId": block.id,
            }
            next_block = _next_nonblank(blocks, index + 1)
            if next_block and _is_title_line(next_block.text) and not EXPLICIT_CHAPTER_RE.match(next_block.text):
                title = f"{title} - {next_block.text}"
                content_start = next_block.end_offset
                evidence["subtitleBlockId"] = next_block.id
                evidence["subtitle"] = next_block.text
            confidence = 0.96 if markdown_level in {1, 2} else 0.9
            candidates_by_start[block.start_offset] = ChapterCandidate(
                start=block.start_offset,
                content_start=content_start,
                end=None,
                title=title,
                confidence=confidence,
                status="structured",
                evidence=evidence,
            )

        if chapter_signals:
            self._promote_signal_chapters(blocks, candidates_by_start, chapter_signals, warnings)

        return sorted(candidates_by_start.values(), key=lambda item: item.start)

    def _promote_signal_chapters(
        self,
        blocks: list[TextBlock],
        candidates_by_start: dict[int, ChapterCandidate],
        chapter_signals: list[ChapterSignal],
        warnings: list[dict[str, object]] | None,
    ) -> None:
        """Promote container signals to chapter boundaries by anchor-text match.

        Signals with ``level <= 1`` become chapters; a matched block bypasses
        ``EXPLICIT_CHAPTER_RE``. When a block is promoted by both the regex and a
        signal it keeps the container reason. Level-2 signals are scene-break
        hints only and never open a chapter in this task. Signals that match no
        block raise a ``container_signal_unmatched`` warning rather than crashing.
        """
        blocks_by_anchor: dict[str, list[TextBlock]] = {}
        for block in blocks:
            anchor = normalize_anchor(block.text)
            if anchor:
                blocks_by_anchor.setdefault(anchor, []).append(block)
        used_block_ids: set[str] = set()
        for signal in chapter_signals:
            if signal.level > 1:
                continue
            anchor = normalize_anchor(signal.anchor_text)
            match = next(
                (
                    block
                    for block in blocks_by_anchor.get(anchor, [])
                    if block.id not in used_block_ids
                ),
                None,
            )
            if match is None:
                if warnings is not None:
                    warnings.append(
                        self.structure_issue(
                            "chapter",
                            stable_id(
                                "chap",
                                self.source_id,
                                0,
                                0,
                                f"{signal.source_kind}:{signal.anchor_text}",
                            ),
                            "container_signal_unmatched",
                            "warning",
                            "A container chapter signal did not match any parsed text block.",
                            "confirm_chapter_heading",
                            {
                                "signalTitle": signal.title,
                                "sourceKind": signal.source_kind,
                                "anchorText": signal.anchor_text,
                                "level": signal.level,
                            },
                            signal.confidence,
                            0,
                            0,
                        )
                    )
                continue
            used_block_ids.add(match.id)
            existing = candidates_by_start.get(match.start_offset)
            confidence = max(signal.confidence, existing.confidence) if existing else signal.confidence
            candidates_by_start[match.start_offset] = ChapterCandidate(
                start=match.start_offset,
                content_start=match.end_offset,
                end=None,
                title=signal.title or match.text,
                confidence=confidence,
                status="structured",
                evidence={
                    "parserVersion": self.parser_version,
                    "reason": signal.source_kind,
                    "sourceBlockId": match.id,
                    "sourceKind": signal.source_kind,
                    "containerSignal": True,
                    "signalConfidence": signal.confidence,
                    "signalLevel": signal.level,
                },
            )

    def scenes(
        self,
        chapter_id: str,
        chapter_text: str,
        chapter_blocks: list[TextBlock],
        chapter_base_offset: int,
        max_chars: int,
        warnings: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        candidates = self.scene_candidates(chapter_text, chapter_blocks, chapter_base_offset)
        if not candidates:
            scene_id = stable_id(
                "scene",
                self.source_id,
                chapter_base_offset,
                chapter_base_offset + len(chapter_text),
                chapter_text[:160],
            )
            evidence = {
                "reason": "no_explicit_breaks",
                "parserVersion": self.parser_version,
                "startOffset": chapter_base_offset,
                "endOffset": chapter_base_offset + len(chapter_text),
            }
            candidates = [
                SceneCandidate(
                    start=chapter_base_offset,
                    end=chapter_base_offset + len(chapter_text),
                    title=None,
                    confidence=0.48,
                    status="unresolved",
                    evidence=evidence,
                )
            ]
            if chapter_text.strip():
                warnings.append(
                    self.structure_issue(
                        "scene",
                        scene_id,
                        "scene.no_explicit_breaks",
                        "info",
                        "No explicit scene breaks were found; a single scene was inferred.",
                        "confirm_scene_breaks",
                        evidence,
                        0.48,
                        chapter_base_offset,
                        chapter_base_offset + min(len(chapter_text), 160),
                    )
                )

        scenes: list[dict[str, object]] = []
        for order_index, candidate in enumerate(candidates):
            scene_text = chapter_text[
                max(0, candidate.start - chapter_base_offset) : max(0, candidate.end - chapter_base_offset)
            ]
            trimmed_start, trimmed_end, trimmed_text = _trim_span(
                scene_text, candidate.start, candidate.end
            )
            if not trimmed_text:
                continue
            scene_id = stable_id("scene", self.source_id, trimmed_start, trimmed_end, trimmed_text[:160])
            if candidate.status in {"inferred", "possible"}:
                warnings.append(
                    self.structure_issue(
                        "scene",
                        scene_id,
                        "scene.possible_break_detected",
                        "warning",
                        "Possible inferred scene break needs review.",
                        "confirm_scene_break",
                        {**candidate.evidence, "textPreview": trimmed_text[:160]},
                        candidate.confidence,
                        trimmed_start,
                        min(trimmed_end, trimmed_start + 160),
                    )
                )
            atoms = self.atoms_for_scene(trimmed_text, trimmed_start, warnings, scene_id)
            offset_validation = validate_atom_offsets(trimmed_text, trimmed_start, atoms)
            if not offset_validation.valid:
                warnings.append(
                    self.structure_issue(
                        "scene",
                        scene_id,
                        "segment.offset_validation_failed",
                        "warning",
                        "One or more atom offsets did not match the source text.",
                        "inspect_segment",
                        {
                            "textPreview": trimmed_text[:160],
                            "errors": offset_validation.errors,
                            "uncoveredRanges": [
                                [start, end]
                                for start, end in offset_validation.uncovered_ranges
                            ],
                            "overlappingRanges": [
                                [start, end]
                                for start, end in offset_validation.overlapping_ranges
                            ],
                        },
                        0.72,
                        trimmed_start,
                        trimmed_end,
                    )
                )
            segments = self.segments_from_atoms(scene_id, atoms, max_chars, warnings)
            scenes.append(
                {
                    "record": {
                        "id": scene_id,
                        "chapter_id": chapter_id,
                        "order_index": order_index,
                        "start_offset": trimmed_start,
                        "end_offset": trimmed_end,
                        "confidence": candidate.confidence,
                        "status": candidate.status,
                        "parser_evidence_json": safe_json(
                            {
                                **candidate.evidence,
                                "parserVersion": self.parser_version,
                                "title": candidate.title,
                            }
                        ),
                    },
                    "segments": segments,
                    "_atoms": atoms,
                    "_scene_text": trimmed_text,
                    "_base": trimmed_start,
                }
            )
        return scenes

    def scene_candidates(
        self, chapter_text: str, chapter_blocks: list[TextBlock], chapter_base_offset: int
    ) -> list[SceneCandidate]:
        breaks: list[tuple[int, int, str | None, float, str, dict[str, object]]] = []
        body_since_break = 0
        for block in chapter_blocks:
            if block.kind in {"paragraph", "dialogue_line", "script_dialogue"}:
                body_since_break += len(block.text)
            if block.kind == "separator" or SCENE_LINE_RE.match(block.text):
                breaks.append(
                    (
                        block.start_offset,
                        block.end_offset,
                        block.text if block.kind != "separator" else None,
                        0.92,
                        "structured",
                        {
                            "reason": "explicit_separator"
                            if block.kind == "separator"
                            else "explicit_scene_heading",
                            "separatorText": block.text,
                            "startOffset": block.start_offset,
                            "confidence": 0.92,
                        },
                    )
                )
                body_since_break = 0
            elif body_since_break >= 18 and _is_time_shift(block.text):
                breaks.append(
                    (
                        block.start_offset,
                        block.start_offset,
                        block.text[:80],
                        0.62,
                        "possible",
                        {
                            "reason": "possible_time_shift",
                            "matchedText": block.text[:80],
                            "startOffset": block.start_offset,
                            "confidence": 0.62,
                            "reviewAction": "confirm_scene_break",
                        },
                    )
                )
                body_since_break = len(block.text)
            elif body_since_break >= 120 and block.kind == "possible_heading":
                breaks.append(
                    (
                        block.start_offset,
                        block.end_offset,
                        block.text,
                        0.58,
                        "possible",
                        {
                            "reason": "possible_section_heading",
                            "matchedText": block.text,
                            "startOffset": block.start_offset,
                            "confidence": 0.58,
                            "reviewAction": "confirm_scene_break",
                        },
                    )
                )
                body_since_break = 0

        if not breaks:
            return []
        candidates: list[SceneCandidate] = []
        current_start = chapter_base_offset
        current_title: str | None = None
        current_confidence = max(breaks[0][3] - 0.05, 0.5)
        current_status = "structured"
        current_evidence = breaks[0][5]
        for break_start, break_end, title, confidence, status, evidence in breaks:
            if break_start > current_start:
                candidates.append(
                    SceneCandidate(
                        start=current_start,
                        end=break_start,
                        title=current_title,
                        confidence=current_confidence,
                        status=current_status if current_status == "possible" else "structured",
                        evidence=current_evidence,
                    )
                )
            if status == "possible":
                current_start = break_start
                current_title = title
                current_confidence = confidence
                current_status = "possible"
                current_evidence = evidence
            else:
                current_start = break_end if break_end > break_start else break_start
                current_title = title
                current_confidence = confidence
                current_status = status
                current_evidence = evidence
            if title and status == "possible":
                current_start = break_start
        chapter_end = chapter_base_offset + len(chapter_text)
        if current_start < chapter_end:
            candidates.append(
                SceneCandidate(
                    start=current_start,
                    end=chapter_end,
                    title=current_title,
                    confidence=current_confidence,
                    status=current_status,
                    evidence=current_evidence,
                )
            )
        return candidates

    def atoms_for_scene(
        self,
        scene_text: str,
        base: int,
        warnings: list[dict[str, object]] | None = None,
        scene_id: str | None = None,
    ) -> list[TextAtom]:
        atoms: list[TextAtom] = []
        for paragraph_index, (start, end, paragraph) in enumerate(_paragraph_spans(scene_text)):
            absolute_start = base + start
            absolute_end = base + end
            stripped_start, stripped_end, stripped_text = _trim_span(
                paragraph, absolute_start, absolute_end
            )
            if not stripped_text:
                continue
            if _is_performance_beat(stripped_text):
                atoms.append(
                    self._atom(
                        "performance_beat",
                        stripped_text,
                        stripped_start,
                        stripped_end,
                        None,
                        0.0,
                        0.94,
                        {"reason": "bracketed_performance_beat"},
                    )
                )
                continue
            colon = COLON_SPEAKER_RE.match(stripped_text)
            if colon:
                speaker = _clean_speaker(colon.group("speaker"))
                atoms.extend(
                    self._atoms_for_colon_speaker(
                        stripped_text,
                        stripped_start,
                        stripped_end,
                        speaker,
                        colon.end(),
                    )
                )
                continue
            paragraph_atoms = self._atoms_for_paragraph(
                stripped_text,
                stripped_start,
                warnings,
                scene_id,
            )
            if paragraph_index > 0 and paragraph_atoms:
                first_atom = paragraph_atoms[0]
                paragraph_atoms[0] = replace(
                    first_atom,
                    evidence={**first_atom.evidence, "paragraphBreakBefore": True},
                )
            atoms.extend(paragraph_atoms)
        return atoms

    def segments_from_atoms(
        self,
        scene_id: str,
        atoms: list[TextAtom],
        max_chars: int,
        warnings: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        drafts = self.segment_drafts_from_atoms(atoms, max_chars, warnings)
        drafts = [self.review_segment_draft(draft, warnings) for draft in drafts]
        return [
            self.segment_record(scene_id, index, draft)
            for index, draft in enumerate(drafts)
        ]

    def segment_drafts_from_atoms(
        self, atoms: list[TextAtom], max_chars: int, warnings: list[dict[str, object]]
    ) -> list[SegmentDraft]:
        drafts: list[SegmentDraft] = []
        used: set[str] = set()
        narration_group: list[TextAtom] = []

        def flush_narration() -> None:
            nonlocal narration_group
            if narration_group:
                drafts.extend(self._split_narration_group(narration_group, max_chars))
                narration_group = []

        for index, atom in enumerate(atoms):
            if atom.id in used:
                continue
            if atom.kind == "performance_beat":
                flush_narration()
                drafts.append(self._draft([atom], "performance_beat", "performance_beat", None, 0.0, 0.92))
                used.add(atom.id)
                continue
            if atom.kind == "quote":
                flush_narration()
                group: list[TextAtom] = []
                previous = atoms[index - 1] if index > 0 else None
                next_atom = atoms[index + 1] if index + 1 < len(atoms) else None
                if previous and previous.kind == "dialogue_tag" and previous.id not in used:
                    group.append(previous)
                    used.add(previous.id)
                group.append(atom)
                used.add(atom.id)
                if next_atom and next_atom.kind == "dialogue_tag" and next_atom.id not in used:
                    group.append(next_atom)
                    used.add(next_atom.id)
                speaker, confidence, evidence = self.resolve_atom_speaker(atoms, index)
                production_type = "dialogue_with_tag" if len(group) > 1 else "dialogue"
                status = "ready" if speaker and confidence >= 0.8 else "needs_review"
                draft = self._draft(group, "dialogue", production_type, speaker, confidence, confidence)
                draft = SegmentDraft(
                    atom_ids=draft.atom_ids,
                    segment_type=draft.segment_type,
                    production_type=draft.production_type,
                    text=draft.text,
                    start_offset=draft.start_offset,
                    end_offset=draft.end_offset,
                    speaker_hint=draft.speaker_hint,
                    speaker_confidence=draft.speaker_confidence,
                    confidence=draft.confidence,
                    status=status,
                    evidence={**draft.evidence, **evidence},
                )
                drafts.append(draft)
                if not speaker:
                    warnings.append(
                        self.structure_issue(
                            "segment",
                            stable_id("seg", self.source_id, atom.start_offset, atom.end_offset, atom.text),
                            "segment.dialogue_no_speaker",
                            "warning",
                            "Dialogue segment has no speaker attribution.",
                            "assign_speaker",
                            {
                                "textPreview": atom.text[:160],
                                "speakerRule": "unresolved_quote",
                                "startOffset": atom.start_offset,
                                "endOffset": atom.end_offset,
                            },
                            0.45,
                            atom.start_offset,
                            atom.end_offset,
                        )
                    )
                elif confidence < 0.8:
                    warnings.append(
                        self.structure_issue(
                            "segment",
                            stable_id("seg", self.source_id, atom.start_offset, atom.end_offset, atom.text),
                            "segment.low_confidence_speaker",
                            "warning",
                            "Dialogue speaker was inferred with low confidence.",
                            "confirm_speaker",
                            {
                                "textPreview": atom.text[:160],
                                "speakerCandidate": speaker,
                                "startOffset": atom.start_offset,
                                "endOffset": atom.end_offset,
                            },
                            confidence,
                            atom.start_offset,
                            atom.end_offset,
                        )
                    )
                continue
            if atom.kind == "dialogue_tag":
                flush_narration()
                drafts.append(self._draft([atom], "narration", "action_beat", None, 0.0, 0.62))
                used.add(atom.id)
                continue
            if atom.evidence.get("paragraphBreakBefore"):
                flush_narration()
            narration_group.append(atom)
            used.add(atom.id)
            if sum(len(item.text) for item in narration_group) >= max_chars:
                flush_narration()
        flush_narration()
        return self._mark_ambiguous_exchange(drafts, warnings)

    def review_segment_draft(
        self, draft: SegmentDraft, warnings: list[dict[str, object]]
    ) -> SegmentDraft:
        warning_codes = _clean_string_list(draft.evidence.get("warningCodes"))
        review_action = str(draft.evidence.get("reviewAction") or "")
        atom_kinds = _clean_string_list(draft.evidence.get("atomKinds"))
        high_confidence_speakers = {
            _speaker_key(name): name
            for name, confidence in _speaker_hint_pairs(draft.evidence.get("atomSpeakerHints"))
            if confidence >= 0.8 and _speaker_key(name)
        }
        if draft.speaker_hint and draft.speaker_confidence >= 0.8:
            high_confidence_speakers[_speaker_key(draft.speaker_hint)] = draft.speaker_hint

        if len(high_confidence_speakers) > 1:
            warning_codes.append("segment.multiple_speakers")
            review_action = "assign_speakers"
            warnings.append(
                self.structure_issue(
                    "segment",
                    stable_id("seg", self.source_id, draft.start_offset, draft.end_offset, draft.text),
                    "segment.multiple_speakers",
                    "warning",
                    "Segment contains multiple high-confidence speaker hints.",
                    "assign_speakers",
                    {
                        "textPreview": draft.text[:160],
                        "speakerCandidates": list(high_confidence_speakers.values()),
                    },
                    0.7,
                    draft.start_offset,
                    draft.end_offset,
                )
            )

        has_quote = "quote" in atom_kinds
        has_substantial_narration = "narration" in atom_kinds
        if has_quote and has_substantial_narration and draft.production_type != "dialogue_with_tag":
            warning_codes.append("segment.mixed_dialogue_and_narration")
            review_action = "split_segment"
            warnings.append(
                self.structure_issue(
                    "segment",
                    stable_id("seg", self.source_id, draft.start_offset, draft.end_offset, draft.text),
                    "segment.mixed_dialogue_and_narration",
                    "warning",
                    "Segment contains both dialogue and substantial narration.",
                    "split_segment",
                    {"textPreview": draft.text[:160], "atomKinds": atom_kinds},
                    0.68,
                    draft.start_offset,
                    draft.end_offset,
                )
            )

        if not warning_codes:
            return draft
        return replace(
            draft,
            status="needs_review",
            evidence={
                **draft.evidence,
                "warningCodes": sorted(set(warning_codes)),
                "reviewAction": review_action or "review_segment",
            },
        )

    def _mark_ambiguous_exchange(
        self, drafts: list[SegmentDraft], warnings: list[dict[str, object]]
    ) -> list[SegmentDraft]:
        index = 0
        marked: set[int] = set()
        while index < len(drafts):
            if not _is_unresolved_dialogue_draft(drafts[index]):
                index += 1
                continue
            start = index
            while index < len(drafts) and _is_unresolved_dialogue_draft(drafts[index]):
                index += 1
            if index - start < 4:
                continue
            window = drafts[start:index]
            preview = " ".join(draft.text for draft in window)[:160]
            warnings.append(
                self.structure_issue(
                    "segment",
                    stable_id("seg", self.source_id, window[0].start_offset, window[-1].end_offset, preview),
                    "speaker.ambiguous_two_person_exchange",
                    "warning",
                    "Alternating unattributed dialogue needs speaker review.",
                    "assign_speakers",
                    {"textPreview": preview, "segmentCount": len(window)},
                    0.62,
                    window[0].start_offset,
                    window[-1].end_offset,
                )
            )
            marked.update(range(start, index))
        if not marked:
            return drafts
        updated = list(drafts)
        for item in marked:
            codes = _clean_string_list(updated[item].evidence.get("warningCodes"))
            codes.append("speaker.ambiguous_two_person_exchange")
            updated[item] = replace(
                updated[item],
                status="needs_review",
                evidence={
                    **updated[item].evidence,
                    "warningCodes": sorted(set(codes)),
                    "reviewAction": "assign_speakers",
                },
            )
        return updated

    def segment_record(self, scene_id: str, order_index: int, draft: SegmentDraft) -> dict[str, object]:
        evidence = {
            **draft.evidence,
            "parserVersion": self.parser_version,
            "sources": draft.evidence.get("sources", ["block_map", "quote_aware_atomization"]),
            "segmentTypeRule": draft.segment_type,
            "productionType": draft.production_type,
            "atomIds": draft.atom_ids,
            "sourceSpanId": stable_id(
                "span", self.source_id, draft.start_offset, draft.end_offset, draft.text
            ),
        }
        return {
            "id": stable_id("seg", self.source_id, draft.start_offset, draft.end_offset, draft.text),
            "scene_id": scene_id,
            "order_index": order_index,
            "text_content": draft.text,
            "normalized_text": draft.text,
            "segment_type": draft.segment_type,
            "speaker_candidate": draft.speaker_hint,
            "speaker_confidence": draft.speaker_confidence,
            "start_offset": draft.start_offset,
            "end_offset": draft.end_offset,
            "revision": 1,
            "status": draft.status,
            "parser_evidence_json": safe_json(evidence),
        }

    def structure_issue(
        self,
        scope_type: str,
        scope_id: str,
        code: str,
        severity: str,
        message: str,
        review_action: str,
        evidence: dict[str, object],
        confidence: float,
        start_offset: int,
        end_offset: int,
    ) -> dict[str, object]:
        payload = {
            **evidence,
            "code": code,
            "reviewAction": review_action,
            "startOffset": start_offset,
            "endOffset": end_offset,
            "confidence": confidence,
        }
        return {
            "id": stable_id("structwarn", self.source_id, start_offset, end_offset, f"{code}:{scope_id}"),
            "project_id": self.project_id,
            "source_document_id": self.source_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "severity": severity,
            "message": message,
            "evidence_json": safe_json(payload),
            "confidence": confidence,
            "resolved": False,
            "created_at": datetime.now(UTC),
        }

    def quality(
        self,
        hierarchy: list[dict[str, object]],
        warnings: list[dict[str, object]],
        *,
        llm_used: bool,
        accepted: int,
        rejected: int,
    ) -> dict[str, object]:
        chapters = hierarchy
        scenes = [
            scene
            for chapter in chapters
            for scene in _as_list(cast_dict(chapter).get("scenes"))
            if isinstance(scene, dict)
        ]
        segments = [
            segment
            for scene in scenes
            for segment in _as_list(scene.get("segments"))
            if isinstance(segment, dict)
        ]
        dialogue = [segment for segment in segments if segment.get("segment_type") == "dialogue"]
        unresolved = [
            segment
            for segment in dialogue
            if not segment.get("speaker_candidate") or float(segment.get("speaker_confidence") or 0) < 0.8
        ]
        long_segments = [segment for segment in segments if len(str(segment.get("text_content") or "")) > 900]
        total_chars = sum(len(str(segment.get("text_content") or "")) for segment in segments)
        warning_codes = [_warning_code(warning) for warning in warnings]
        low_cast = sum(1 for segment in dialogue if float(segment.get("speaker_confidence") or 0) < 0.72)
        attributed_dialogue = len(dialogue) - len(unresolved)
        container_chapters = sum(
            1 for chapter in chapters if _chapter_from_container_signal(chapter)
        )
        return {
            "chapterCount": len(chapters),
            "chaptersFromContainerSignals": container_chapters,
            "sceneCount": len(scenes),
            "segmentCount": len(segments),
            "dialogueSegmentCount": len(dialogue),
            "dialogueAttributionCoverage": round((attributed_dialogue / len(dialogue)) * 100, 1) if dialogue else 100.0,
            "unresolvedDialogueCount": len(unresolved),
            "averageSegmentChars": round(total_chars / len(segments), 1) if segments else 0,
            "longSegmentCount": len(long_segments),
            "mixedSegmentWarningCount": warning_codes.count("segment.mixed_dialogue_and_narration"),
            "castCandidateCount": len(
                {
                    str(segment.get("speaker_candidate"))
                    for segment in dialogue
                    if segment.get("speaker_candidate")
                }
            ),
            "possibleDuplicateCastCount": 0,
            "lowConfidenceCastCandidateCount": low_cast,
            "possibleSceneBreakCount": warning_codes.count("scene.possible_break_detected"),
            "offsetValidationFailureCount": warning_codes.count("segment.offset_validation_failed"),
            "quoteUnclosedCount": warning_codes.count("segment.quote_unclosed"),
            "warningsNeedingReviewCount": sum(
                1
                for warning in warnings
                if str(warning.get("severity")) in {"warning", "blocking", "error"}
            ),
            "llmRefinementUsed": llm_used,
            "llmAcceptedBatchCount": accepted,
            "llmRejectedBatchCount": rejected,
        }

    def _classify_block(
        self, text: str, previous_blocks: list[TextBlock]
    ) -> tuple[str, float, dict[str, object]]:
        if not text:
            return "blank", 1.0, {"reason": "blank_line"}
        if SEPARATOR_RE.match(text):
            return "separator", 0.96, {"reason": "explicit_separator", "separatorText": text}
        if _is_performance_beat(text):
            return "stage_direction", 0.9, {"reason": "bracketed_stage_direction"}
        markdown = re.match(r"^(#{1,6})\s+(.+)$", text)
        if markdown:
            level = len(markdown.group(1))
            if level <= 2 or EXPLICIT_CHAPTER_RE.match(markdown.group(2).strip()):
                return "heading", 0.92, {"reason": "markdown_heading", "markdownLevel": level}
            return "possible_heading", 0.62, {"reason": "markdown_section_heading", "markdownLevel": level}
        if EXPLICIT_CHAPTER_RE.match(text):
            return "heading", 0.9, {"reason": "explicit_chapter_heading"}
        if SCENE_LINE_RE.match(text):
            return "separator", 0.88, {"reason": "scene_marker", "separatorText": text}
        if COLON_SPEAKER_RE.match(text):
            return "script_dialogue", 0.9, {"reason": "colon_speaker"}
        if _is_title_line(text) and previous_blocks and previous_blocks[-1].kind == "blank":
            return "possible_heading", 0.58, {"reason": "short_heading_like_line"}
        return "paragraph", 0.84, {"reason": "body_paragraph"}

    def _atoms_for_paragraph(
        self,
        paragraph: str,
        base: int,
        warnings: list[dict[str, object]] | None = None,
        scene_id: str | None = None,
    ) -> list[TextAtom]:
        scan = _scan_quotes(paragraph)
        if scan.unclosed_start is not None:
            warning_start = base + scan.unclosed_start
            warning_end = base + len(paragraph)
            if warnings is not None:
                warnings.append(
                    self.structure_issue(
                        "segment",
                        stable_id("seg", self.source_id, warning_start, warning_end, paragraph[scan.unclosed_start :]),
                        "segment.quote_unclosed",
                        "warning",
                        "Quoted text has an opening quote without a closing quote.",
                        "inspect_segment",
                        {
                            "textPreview": paragraph[scan.unclosed_start : scan.unclosed_start + 160],
                            "quoteChar": scan.unclosed_char or "",
                            "sceneId": scene_id or "",
                        },
                        0.74,
                        warning_start,
                        warning_end,
                    )
                )
            return self._sentence_atoms(paragraph, base, "narration")
        spans = scan.spans
        if not spans:
            return self._sentence_atoms(paragraph, base, "narration")
        atoms: list[TextAtom] = []
        cursor = 0
        for quote_start, quote_end in spans:
            if quote_start > cursor:
                atoms.extend(self._text_atoms_between_quotes(paragraph[cursor:quote_start], base + cursor))
            quote_text = paragraph[quote_start:quote_end]
            atoms.append(
                self._atom(
                    "quote",
                    quote_text,
                    base + quote_start,
                    base + quote_end,
                    None,
                    0.0,
                    0.78,
                    {"reason": "quoted_text"},
                )
            )
            cursor = quote_end
        if cursor < len(paragraph):
            atoms.extend(self._text_atoms_between_quotes(paragraph[cursor:], base + cursor))
        return atoms

    def _text_atoms_between_quotes(self, text: str, base: int) -> list[TextAtom]:
        stripped_start, stripped_end, stripped_text = _trim_span(text, base, base + len(text))
        if not stripped_text:
            return []
        sentences = _sentence_parts(stripped_text, stripped_start)
        atoms: list[TextAtom] = []
        for sentence, start, end in sentences:
            kind = "dialogue_tag" if _speaker_from_tag(sentence) else "narration"
            speaker = _speaker_from_tag(sentence) if kind == "dialogue_tag" else None
            atoms.append(
                self._atom(
                    kind,
                    sentence,
                    start,
                    end,
                    speaker,
                    0.84 if speaker else 0.0,
                    0.86 if kind == "dialogue_tag" else 0.82,
                    {"reason": "dialogue_tag" if kind == "dialogue_tag" else "narration_sentence"},
                )
            )
        return atoms

    def _sentence_atoms(self, text: str, base: int, kind: str) -> list[TextAtom]:
        return [
            self._atom(
                kind,
                sentence,
                start,
                end,
                _speaker_from_free_text(sentence),
                0.74 if _speaker_from_free_text(sentence) else 0.0,
                0.82,
                {"reason": "sentence_batch"},
            )
            for sentence, start, end in _sentence_parts(text, base)
        ]

    def _atoms_for_colon_speaker(
        self,
        text: str,
        start: int,
        end: int,
        speaker: str | None,
        body_start: int,
    ) -> list[TextAtom]:
        body_sentences = _sentence_parts(text[body_start:], start + body_start)
        if len(body_sentences) > 1 and _looks_like_narrative_tail(body_sentences[1][0]):
            first_end = body_sentences[0][2]
            atoms = [
                self._atom(
                    "quote",
                    text[: first_end - start],
                    start,
                    first_end,
                    speaker,
                    0.93,
                    0.9,
                    {
                        "reason": "colon_speaker_first_sentence",
                        "speakerRule": "colon_speaker",
                    },
                )
            ]
            for sentence, sentence_start, sentence_end in body_sentences[1:]:
                speaker_hint = _speaker_from_free_text(sentence)
                atoms.append(
                    self._atom(
                        "narration",
                        sentence,
                        sentence_start,
                        sentence_end,
                        speaker_hint,
                        0.74 if speaker_hint else 0.0,
                        0.78,
                        {"reason": "colon_speaker_narrative_tail"},
                    )
                )
            return atoms
        return [
            self._atom(
                "quote",
                text,
                start,
                end,
                speaker,
                0.93,
                0.93,
                {"reason": "colon_speaker", "speakerRule": "colon_speaker"},
            )
        ]

    def resolve_atom_speaker(
        self, atoms: list[TextAtom], atom_index: int
    ) -> tuple[str | None, float, dict[str, object]]:
        atom = atoms[atom_index]
        if atom.speaker_hint and not ignored_speaker(atom.speaker_hint):
            return atom.speaker_hint, atom.speaker_confidence, {
                "speakerRule": atom.evidence.get("speakerRule", atom.evidence.get("reason", "speaker_hint")),
                "speakerEvidence": atom.evidence,
            }
        previous = atoms[atom_index - 1] if atom_index > 0 else None
        next_atom = atoms[atom_index + 1] if atom_index + 1 < len(atoms) else None
        for candidate, rule in ((next_atom, "quote_followed_by_dialogue_tag"), (previous, "dialogue_tag_before_quote")):
            if candidate and candidate.kind == "dialogue_tag":
                speaker = candidate.speaker_hint or _speaker_from_tag(candidate.text)
                if speaker and not ignored_speaker(speaker):
                    return speaker, 0.88, {"speakerRule": rule, "speakerEvidence": candidate.text}
        if previous and previous.kind == "narration":
            speaker = _subject_name(previous.text)
            if speaker and not ignored_speaker(speaker):
                return speaker, 0.62, {
                    "speakerRule": "action_beat_before_quote",
                    "speakerEvidence": previous.text[:160],
                }
        return None, 0.0, {"speakerRule": "unresolved_quote"}

    def _draft(
        self,
        atoms: list[TextAtom],
        segment_type: str,
        production_type: str,
        speaker: str | None,
        speaker_confidence: float,
        confidence: float,
    ) -> SegmentDraft:
        start = atoms[0].start_offset
        end = atoms[-1].end_offset
        text = " ".join(atom.text for atom in atoms).strip()
        return SegmentDraft(
            atom_ids=[atom.id for atom in atoms],
            segment_type=segment_type,
            production_type=production_type,
            text=text,
            start_offset=start,
            end_offset=end,
            speaker_hint=speaker,
            speaker_confidence=speaker_confidence,
            confidence=confidence,
            status="ready",
            evidence={
                "sources": ["block_map", "quote_aware_atomization", "deterministic_segment_builder"],
                "confidence": confidence,
                "atomKinds": [atom.kind for atom in atoms],
                "atomSpeakerHints": [
                    {
                        "name": atom.speaker_hint,
                        "confidence": atom.speaker_confidence,
                        "kind": atom.kind,
                    }
                    for atom in atoms
                    if atom.speaker_hint
                ],
            },
        )

    def _split_narration_group(self, atoms: list[TextAtom], max_chars: int) -> list[SegmentDraft]:
        drafts: list[SegmentDraft] = []
        current: list[TextAtom] = []
        current_chars = 0
        for atom in atoms:
            if current and current_chars + len(atom.text) > max_chars:
                drafts.append(self._draft(current, "narration", "narration", None, 0.0, 0.88))
                current = []
                current_chars = 0
            if len(atom.text) > max_chars:
                for sentence, start, end in _sentence_parts(atom.text, atom.start_offset):
                    piece = self._atom("narration", sentence, start, end, None, 0.0, 0.78, {"reason": "long_atom_sentence_split"})
                    drafts.append(self._draft([piece], "narration", "narration", None, 0.0, 0.78))
                continue
            current.append(atom)
            current_chars += len(atom.text)
        if current:
            speaker = next((atom.speaker_hint for atom in current if atom.speaker_hint), None)
            confidence = next((atom.speaker_confidence for atom in current if atom.speaker_hint), 0.0)
            drafts.append(self._draft(current, "narration", "narration", speaker, confidence, 0.88))
        return drafts

    def _atom(
        self,
        kind: str,
        text: str,
        start: int,
        end: int,
        speaker_hint: str | None,
        speaker_confidence: float,
        confidence: float,
        evidence: dict[str, object],
    ) -> TextAtom:
        return TextAtom(
            id=stable_id("atom", self.source_id, start, end, text),
            kind=kind,
            text=text.strip(),
            start_offset=start,
            end_offset=end,
            speaker_hint=_clean_speaker(speaker_hint),
            speaker_confidence=speaker_confidence,
            confidence=confidence,
            evidence={**evidence, "parserVersion": self.parser_version},
        )


def cast_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _chapter_from_container_signal(chapter: object) -> bool:
    record = cast_dict(chapter).get("record")
    try:
        evidence = json.loads(str(cast_dict(record).get("parser_evidence_json") or "{}"))
    except json.JSONDecodeError:
        return False
    return isinstance(evidence, dict) and str(evidence.get("reason")) in CONTAINER_SIGNAL_KINDS


def _warning_code(warning: dict[str, object]) -> str:
    try:
        evidence = json.loads(str(warning.get("evidence_json") or "{}"))
    except json.JSONDecodeError:
        return ""
    return str(evidence.get("code") or "") if isinstance(evidence, dict) else ""


def _is_unresolved_dialogue_draft(draft: SegmentDraft) -> bool:
    return draft.segment_type == "dialogue" and (
        not draft.speaker_hint or draft.speaker_confidence < 0.8
    )


def _clean_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _speaker_hint_pairs(value: object) -> list[tuple[str, float]]:
    if not isinstance(value, list):
        return []
    pairs: list[tuple[str, float]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            confidence = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        pairs.append((name, confidence))
    return pairs


def _speaker_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _strip_markdown_heading(value: str) -> str:
    return re.sub(r"^#{1,6}\s+", "", value).strip()


def _chapter_title_from_heading(value: str) -> str:
    heading = value.strip()
    if any(separator in heading for separator in (":", "-", "—")):
        return heading
    match = re.match(
        r"^(?P<prefix>chapter\s+(?:\d+|[ivxlcdm]+|[a-z]+))\s+(?P<title>.+)$",
        heading,
        re.IGNORECASE,
    )
    if not match:
        return heading
    title = match.group("title").strip()
    if _is_title_line(title):
        return f"{match.group('prefix')} - {title}"
    return heading


def _next_nonblank(blocks: list[TextBlock], start: int) -> TextBlock | None:
    for block in blocks[start:]:
        if block.kind != "blank":
            return block
    return None


def _is_title_line(text: str) -> bool:
    if not text or len(text) > 80:
        return False
    if text.endswith((".", "?", "!", ",", ";", ":")):
        return False
    if '"' in text or "“" in text or "”" in text:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if not words or len(words) > 8:
        return False
    titleish = sum(1 for word in words if word[:1].isupper())
    return titleish >= max(1, len(words) - 1)


def _is_time_shift(text: str) -> bool:
    return bool(TIME_SHIFT_RE.match(text.strip()))


def _is_performance_beat(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) <= 140 and (
        (stripped.startswith("[") and stripped.endswith("]"))
        or (stripped.startswith("(") and stripped.endswith(")"))
    )


def _looks_like_narrative_tail(text: str) -> bool:
    return bool(re.match(r"^(?:the|a|an)\b", text.strip(), re.IGNORECASE))


def _paragraph_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for match in re.finditer(r"\n\s*\n", text):
        if match.start() > cursor:
            spans.append((cursor, match.start(), text[cursor : match.start()]))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text), text[cursor:]))
    return spans


def _trim_span(text: str, start: int, end: int) -> tuple[int, int, str]:
    left = len(text) - len(text.lstrip())
    right = len(text.rstrip())
    return start + left, start + right, text.strip()


def _quote_spans(text: str) -> list[tuple[int, int]]:
    return _scan_quotes(text).spans


def _scan_quotes(text: str) -> QuoteScan:
    spans: list[tuple[int, int]] = []
    pairs = {"“": "”", "‘": "’"}
    cursor = 0
    open_start: int | None = None
    close_char = ""
    open_char = ""
    while cursor < len(text):
        char = text[cursor]
        if open_start is None:
            if char in {'"', "“", "‘"} or (char == "'" and not _is_apostrophe(text, cursor)):
                open_start = cursor
                open_char = char
                close_char = pairs.get(char, char)
        elif char == close_char and not (char == "'" and _is_apostrophe(text, cursor)):
            spans.append((open_start, cursor + 1))
            open_start = None
            close_char = ""
            open_char = ""
        cursor += 1
    return QuoteScan(spans=spans, unclosed_start=open_start, unclosed_char=open_char or None)


def _is_apostrophe(text: str, index: int) -> bool:
    previous = text[index - 1] if index > 0 else ""
    next_char = text[index + 1] if index + 1 < len(text) else ""
    return previous.isalnum() and next_char.isalnum()


def _sentence_parts(text: str, base: int) -> list[tuple[str, int, int]]:
    parts: list[tuple[str, int, int]] = []
    cursor = 0
    for match in SENTENCE_RE.finditer(text):
        raw = match.group(0)
        if not raw.strip():
            continue
        start, end, stripped = _trim_span(raw, base + match.start(), base + match.end())
        if start < end:
            parts.append((stripped, start, end))
        cursor = match.end()
    if not parts and text.strip():
        start, end, stripped = _trim_span(text, base, base + len(text))
        parts.append((stripped, start, end))
    elif cursor < len(text) and text[cursor:].strip():
        start, end, stripped = _trim_span(text[cursor:], base + cursor, base + len(text))
        parts.append((stripped, start, end))
    return _merge_abbreviation_sentence_parts(parts)


def _merge_abbreviation_sentence_parts(
    parts: list[tuple[str, int, int]]
) -> list[tuple[str, int, int]]:
    merged: list[tuple[str, int, int]] = []
    index = 0
    while index < len(parts):
        text, start, end = parts[index]
        while index + 1 < len(parts) and ABBREVIATION_TAIL_RE.search(text):
            next_text, _next_start, next_end = parts[index + 1]
            text = f"{text} {next_text}"
            end = next_end
            index += 1
        merged.append((text, start, end))
        index += 1
    return merged


def _speaker_from_tag(text: str) -> str | None:
    before = TAG_BEFORE_RE.match(text.strip())
    if before:
        return _clean_speaker(before.group("speaker"))
    after = TAG_AFTER_RE.match(text.strip())
    if after:
        return _clean_speaker(after.group("speaker_before") or after.group("speaker_after"))
    return None


def _speaker_from_free_text(text: str) -> str | None:
    match = re.search(rf"\b(?P<speaker>{SPEAKER_PATTERN})\s+(?:{SPEECH_VERB_PATTERN})\b", text, re.IGNORECASE)
    return _clean_speaker(match.group("speaker")) if match else None


def _subject_name(text: str) -> str | None:
    match = re.match(rf"^\s*(?P<speaker>{SPEAKER_PATTERN})\b", text)
    return _clean_speaker(match.group("speaker")) if match else None


def _clean_speaker(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value.strip(" ,.:;!?\"'“”‘’"))
    return None if ignored_speaker(cleaned) else cleaned
