import re
from dataclasses import dataclass

from echodraft_domain import ParserWarning, WarningSeverity


@dataclass(frozen=True)
class CleaningChange:
    change_type: str
    start: int
    end: int
    original: str
    replacement: str
    confidence: float


@dataclass(frozen=True)
class CleaningIssueDraft:
    issue_type: str
    start: int
    end: int
    severity: str
    suggested_fix: str | None
    confidence: float
    status: str = "open"


@dataclass(frozen=True)
class CleaningResult:
    text: str
    changes: list[CleaningChange]
    issues: list[CleaningIssueDraft]
    warnings: list[ParserWarning]


class CleaningPipeline:
    html_page_marker = re.compile(r"<!--\s*(?:page\s*)?\d+\s*-->", re.IGNORECASE)
    line_page_marker = re.compile(
        r"(?im)^\s*(?:page\s+\d+|\[\s*(?:page\s*)?\d+\s*\])\s*$"
    )
    suspicious_digit_word = re.compile(r"\b[A-Za-z]+[0-9][A-Za-z0-9]*\b")
    suspicious_repeated_glyph = re.compile(r"\b([A-Za-z])\1{3,}\w*\b")

    def clean(self, text: str) -> CleaningResult:
        changes: list[CleaningChange] = []
        issues: list[CleaningIssueDraft] = []
        warnings: list[ParserWarning] = []

        text = self._remove_matches(text, self.html_page_marker, "html_page_marker", changes)
        text = self._remove_matches(text, self.line_page_marker, "line_page_marker", changes)
        text = self._remove_repeated_headers_or_footers(text, changes)
        text = self._repair_hyphenation(text, changes)
        text = self._merge_broken_line_wraps(text, changes)

        for match in self.suspicious_digit_word.finditer(text):
            issues.append(
                CleaningIssueDraft(
                    issue_type="suspicious_ocr_token",
                    start=match.start(),
                    end=match.end(),
                    severity="warning",
                    suggested_fix=None,
                    confidence=0.7,
                )
            )
        for match in self.suspicious_repeated_glyph.finditer(text):
            issues.append(
                CleaningIssueDraft(
                    issue_type="suspicious_repeated_glyph",
                    start=match.start(),
                    end=match.end(),
                    severity="warning",
                    suggested_fix=None,
                    confidence=0.65,
                )
            )
        if changes:
            warnings.append(
                ParserWarning(
                    severity=WarningSeverity.INFO,
                    sourceRange="document",
                    message=f"Canonical cleaning applied {len(changes)} deterministic changes.",
                    suggestedAction="Review the clean text decisions before structure extraction.",
                )
            )
        return CleaningResult(text=text, changes=changes, issues=issues, warnings=warnings)

    def _remove_matches(
        self, text: str, pattern: re.Pattern[str], change_type: str, changes: list[CleaningChange]
    ) -> str:
        result: list[str] = []
        cursor = 0
        for match in pattern.finditer(text):
            result.append(text[cursor:match.start()])
            changes.append(
                CleaningChange(
                    change_type=change_type,
                    start=match.start(),
                    end=match.end(),
                    original=match.group(0),
                    replacement="",
                    confidence=0.96,
                )
            )
            cursor = match.end()
        result.append(text[cursor:])
        return "".join(result)

    def _remove_repeated_headers_or_footers(
        self, text: str, changes: list[CleaningChange]
    ) -> str:
        pages = text.split("\f")
        if len(pages) < 3:
            return text
        candidates: dict[str, int] = {}
        for page in pages:
            lines = [line.strip() for line in page.splitlines() if line.strip()]
            for line in (lines[:1] + lines[-1:]):
                normalized = re.sub(r"\s+", " ", line).casefold()
                if len(normalized) > 3:
                    candidates[normalized] = candidates.get(normalized, 0) + 1
        repeated = {
            line for line, count in candidates.items() if count / max(1, len(pages)) >= 0.4
        }
        if not repeated:
            return text
        output_pages: list[str] = []
        offset = 0
        for page in pages:
            kept: list[str] = []
            for line in page.splitlines():
                normalized = re.sub(r"\s+", " ", line.strip()).casefold()
                if normalized in repeated:
                    start = text.find(line, offset)
                    changes.append(
                        CleaningChange(
                            change_type="running_header_footer",
                            start=max(0, start),
                            end=max(0, start) + len(line),
                            original=line,
                            replacement="",
                            confidence=0.78,
                        )
                    )
                    continue
                kept.append(line)
            output_pages.append("\n".join(kept))
            offset += len(page) + 1
        return "\f".join(output_pages)

    def _repair_hyphenation(self, text: str, changes: list[CleaningChange]) -> str:
        pattern = re.compile(r"(?P<left>[A-Za-z]{2,})-\n(?P<right>[a-z]{2,})")
        result: list[str] = []
        cursor = 0
        for match in pattern.finditer(text):
            replacement = f"{match.group('left')}{match.group('right')}"
            result.append(text[cursor:match.start()])
            result.append(replacement)
            changes.append(
                CleaningChange(
                    change_type="hyphenation_repair",
                    start=match.start(),
                    end=match.end(),
                    original=match.group(0),
                    replacement=replacement,
                    confidence=0.82,
                )
            )
            cursor = match.end()
        result.append(text[cursor:])
        return "".join(result)

    def _merge_broken_line_wraps(self, text: str, changes: list[CleaningChange]) -> str:
        pattern = re.compile(r"(?<!\n)\n(?!\n)")
        matches = list(pattern.finditer(text))
        if not matches:
            return text
        for match in matches:
            changes.append(
                CleaningChange(
                    change_type="line_wrap_merge",
                    start=match.start(),
                    end=match.end(),
                    original="\n",
                    replacement=" ",
                    confidence=0.72,
                )
            )
        return pattern.sub(" ", text)
