import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup
from docx import Document
from ebooklib import ITEM_DOCUMENT, epub  # type: ignore[import-untyped]
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from echodraft_db.models import (
    CanonicalSpanRecord,
    OcrPageResultRecord,
    OcrRunRecord,
    SourceDocumentRecord,
    SourcePageRecord,
)
from echodraft_domain import ParserWarning, RightsStatus, WarningSeverity

from .container import AppContainer

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PARSER_VERSION = "ingestion-0.1.0"
MIN_PDF_TEXT_CHARS = 20
MAX_PDF_OCR_PAGES = 150
PDF_RENDER_DPI = 200
SUPPORTED = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".epub": "application/epub+zip",
    ".pdf": "application/pdf",
}


@dataclass(frozen=True)
class PdfArtifactPaths:
    root: Path
    pages: Path
    embedded_text: Path
    selected_text: Path
    ocr: Path
    manifests: Path


@dataclass(frozen=True)
class PdfPageExtraction:
    page_number: int
    source_page_id: str
    embedded_text: str
    selected_text: str
    extraction_method: str
    confidence: float
    image_path: Path | None
    embedded_text_path: Path | None
    selected_text_path: Path | None
    warnings: list[ParserWarning]


@dataclass(frozen=True)
class PdfTextQuality:
    usable: bool
    score: float


class IngestionError(ValueError):
    pass


class IngestionService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def stage(self, project_id: str, filename: str, content_type: str | None, data: bytes, parser_version: str) -> str:
        if not self.container.projects.get(project_id):
            raise KeyError(project_id)
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED:
            raise IngestionError("Unsupported file type. Use TXT, Markdown, DOCX, EPUB, or PDF.")
        if not data:
            raise IngestionError("The selected manuscript is empty.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise IngestionError("The selected manuscript exceeds the 10 MB local import limit.")
        source_id = f"src_{uuid4().hex[:16]}"
        project = self.container.projects.get(project_id)
        assert project
        original_path = Path(project.artifact_path) / "source" / "original" / f"{source_id}-{Path(filename).name}"
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(data)
        now = datetime.now(UTC)
        self.container.sources.create(SourceDocumentRecord(
            id=source_id, project_id=project_id, original_filename=Path(filename).name,
            mime_type=SUPPORTED[suffix] if content_type in {None, "application/octet-stream"} else content_type,
            checksum=hashlib.sha256(data).hexdigest(), imported_at=now,
            rights_status=RightsStatus.DECLARED.value, parser_version=parser_version,
            original_path=str(original_path), warnings_json="[]", status="queued",
        ))
        return source_id

    def process(self, source_id: str, project_id: str, filename: str, mime_type: str, parser_version: str, original_path: Path) -> None:
        try:
            text, warnings = self._extract(original_path, filename, source_id, project_id)
            canonical, normalized_warnings = self._normalize(text)
            warnings.extend(normalized_warnings)
            if not canonical.strip():
                raise IngestionError("No readable text was found in the manuscript.")
            project = self.container.projects.get(project_id)
            assert project
            root = Path(project.artifact_path)
            canonical_version = root / "source" / "canonical" / f"{source_id}.md"
            canonical_version.parent.mkdir(parents=True, exist_ok=True)
            canonical_version.write_text(canonical, encoding="utf-8")
            current_canonical = root / "source" / "canonical.md"
            shutil.copyfile(canonical_version, current_canonical)
            manifest = {
                "manifestType": "source_manifest", "schemaVersion": "0.1.0", "projectId": project_id,
                "generatedAt": datetime.now(UTC).isoformat(), "status": "completed", "diagnostics": [w.model_dump(by_alias=True) for w in warnings],
                "payload": {"sourceDocumentId": source_id, "originalFilename": filename, "mimeType": mime_type,
                            "originalPath": str(original_path), "normalizedTextPath": str(current_canonical),
                            "checksum": hashlib.sha256(original_path.read_bytes()).hexdigest(), "canonicalChecksum": hashlib.sha256(canonical.encode()).hexdigest(),
                            "parserVersion": parser_version, "warnings": [w.model_dump(by_alias=True) for w in warnings]},
            }
            manifest_version = root / "manifests" / f"source_manifest.{source_id}.json"
            manifest_version.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            shutil.copyfile(manifest_version, root / "manifests" / "source_manifest.json")
            self.container.sources.update(source_id, canonical_path=str(current_canonical), manifest_path=str(manifest_version), warnings_json=json.dumps([w.model_dump(by_alias=True) for w in warnings]), status="succeeded")
        except Exception as error:
            self.container.sources.update(source_id, status="failed", error_message=str(error))
            raise

    def _extract(
        self, path: Path, filename: str, source_id: str | None = None, project_id: str | None = None
    ) -> tuple[str, list[ParserWarning]]:
        suffix = Path(filename).suffix.lower()
        warnings: list[ParserWarning] = []
        if suffix in {".txt", ".md", ".markdown"}:
            return path.read_bytes().decode("utf-8-sig", errors="replace"), warnings
        if suffix == ".docx":
            try:
                return "\n\n".join(p.text for p in Document(str(path)).paragraphs), warnings
            except Exception as error:
                raise IngestionError(f"Unreadable DOCX: {error}") from error
        if suffix == ".epub":
            try:
                book = epub.read_epub(str(path))
                sections = []
                for item in book.get_items_of_type(ITEM_DOCUMENT):
                    text = BeautifulSoup(item.get_content(), "html.parser").get_text("\n", strip=True)
                    if text:
                        sections.append(text)
                if not sections:
                    raise IngestionError("Unreadable EPUB: no readable document sections.")
                return "\n\n".join(sections), warnings
            except IngestionError:
                raise
            except Exception as error:
                raise IngestionError(f"Unreadable EPUB: {error}") from error
        if suffix == ".pdf":
            return self._extract_pdf(path, source_id, project_id)
        raise IngestionError("Unsupported file type.")

    def _extract_pdf(
        self, path: Path, source_id: str | None = None, project_id: str | None = None
    ) -> tuple[str, list[ParserWarning]]:
        if not source_id or not project_id:
            return self._extract_pdf_legacy(path)
        return self._extract_pdf_v2(path, source_id, project_id)

    def _extract_pdf_legacy(self, path: Path) -> tuple[str, list[ParserWarning]]:
        try:
            reader = PdfReader(str(path))
        except PdfReadError as error:
            raise IngestionError(f"Unreadable PDF: {error}") from error
        except Exception as error:
            raise IngestionError(f"Unreadable PDF: {error}") from error
        if reader.is_encrypted:
            raise IngestionError("Unreadable PDF: password-protected PDFs are not supported.")

        warnings: list[ParserWarning] = []
        pages: list[str] = []
        ocr_pages: list[int] = []
        try:
            for page_number, page in enumerate(reader.pages, start=1):
                extracted = page.extract_text() or ""
                pages.append(extracted.strip())
                if len(re.sub(r"\s+", "", extracted)) < MIN_PDF_TEXT_CHARS:
                    ocr_pages.append(page_number)
        except Exception as error:
            raise IngestionError(f"Unreadable PDF text content: {error}") from error

        if len(ocr_pages) > MAX_PDF_OCR_PAGES:
            raise IngestionError(
                f"PDF requires OCR for {len(ocr_pages)} pages; the local OCR limit is "
                f"{MAX_PDF_OCR_PAGES} pages. Split or OCR the document before importing."
            )
        if ocr_pages:
            self._require_ocr_tools()
            with tempfile.TemporaryDirectory(prefix="echodraft-pdf-ocr-") as temporary:
                temporary_root = Path(temporary)
                for page_number in ocr_pages:
                    pages[page_number - 1] = self._ocr_page(path, temporary_root, page_number)
                    if pages[page_number - 1].strip():
                        warnings.append(
                            ParserWarning(
                                severity=WarningSeverity.INFO,
                                sourceRange=f"page {page_number}",
                                message="Text was extracted with local OCR.",
                                suggestedAction="Review this page for OCR errors before generation.",
                            )
                        )
                    else:
                        warnings.append(
                            ParserWarning(
                                severity=WarningSeverity.WARNING,
                                sourceRange=f"page {page_number}",
                                message="No readable text was found after local OCR.",
                                suggestedAction="Check the scan quality or OCR this page before import.",
                            )
                        )
        text = "\n\n".join(page for page in pages if page.strip())
        if not text.strip():
            raise IngestionError("Unreadable PDF: no readable text was found after extraction and OCR.")
        return text, warnings

    def _extract_pdf_v2(
        self, path: Path, source_id: str, project_id: str
    ) -> tuple[str, list[ParserWarning]]:
        try:
            reader = PdfReader(str(path))
        except PdfReadError as error:
            raise IngestionError(f"Unreadable PDF: {error}") from error
        except Exception as error:
            raise IngestionError(f"Unreadable PDF: {error}") from error
        if reader.is_encrypted:
            raise IngestionError("Unreadable PDF: password-protected PDFs are not supported.")

        project = self.container.projects.get(project_id)
        if not project:
            raise KeyError(project_id)
        paths = self._pdf_artifact_paths(Path(project.artifact_path), source_id)
        for folder in (paths.pages, paths.embedded_text, paths.selected_text, paths.ocr, paths.manifests):
            folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, paths.root / "original.pdf")
        self.container.source_artifacts.clear_source(source_id)

        page_count = len(reader.pages)
        pages_requiring_ocr: list[int] = []
        page_extractions: list[PdfPageExtraction] = []
        warnings: list[ParserWarning] = []
        ocr_run = None

        for page_number, page in enumerate(reader.pages, start=1):
            embedded = (page.extract_text() or "").strip()
            embedded_path = paths.embedded_text / f"page_{page_number:04d}.txt"
            embedded_path.write_text(embedded, encoding="utf-8")
            quality = self._embedded_pdf_quality(embedded)
            image_path, render_warning = self._try_render_pdf_page(path, paths.pages, page_number)
            page_warnings: list[ParserWarning] = []
            if render_warning:
                page_warnings.append(render_warning)

            selected_text = embedded
            extraction_method = "embedded_text"
            confidence = quality.score
            ocr_result: tuple[str, Path, Path, float] | None = None

            if not quality.usable:
                pages_requiring_ocr.append(page_number)
                if len(pages_requiring_ocr) > MAX_PDF_OCR_PAGES:
                    raise IngestionError(
                        f"PDF requires OCR for more than {MAX_PDF_OCR_PAGES} pages. "
                        "Split or OCR the document before importing."
                    )
                if ocr_run is None:
                    ocr_run = self.container.source_artifacts.create_ocr_run(
                        OcrRunRecord(
                            id=f"ocr_{uuid4().hex[:16]}",
                            source_document_id=source_id,
                            provider="tesseract",
                            status="running",
                            settings_json=json.dumps({"language": "eng", "dpi": PDF_RENDER_DPI}),
                            started_at=datetime.now(UTC),
                        )
                    )
                try:
                    if not image_path:
                        self._require_ocr_tools()
                        image_path = self._render_pdf_page(path, paths.pages, page_number)
                    ocr_result = self._ocr_page_image(
                        image_path, paths.ocr / f"run_{ocr_run.id}", page_number
                    )
                except Exception as error:
                    self.container.source_artifacts.update_ocr_run(
                        ocr_run.id,
                        status="failed",
                        completed_at=datetime.now(UTC),
                        error_message=str(error),
                    )
                    raise
                ocr_text, _ocr_text_path, _ocr_json_path, ocr_confidence = ocr_result
                if ocr_text.strip():
                    selected_text = ocr_text.strip()
                    extraction_method = "ocr"
                    confidence = ocr_confidence
                    page_warnings.append(
                        ParserWarning(
                            severity=WarningSeverity.INFO,
                            sourceRange=f"page {page_number}",
                            message="Text was extracted with local OCR.",
                            suggestedAction="Review this page for OCR errors before generation.",
                        )
                    )
                elif not embedded:
                    page_warnings.append(
                        ParserWarning(
                            severity=WarningSeverity.WARNING,
                            sourceRange=f"page {page_number}",
                            message="No readable text was found after local OCR.",
                            suggestedAction="Check the scan quality or OCR this page before import.",
                        )
                    )

            selected_path = paths.selected_text / f"page_{page_number:04d}.txt"
            selected_path.write_text(selected_text, encoding="utf-8")
            source_page_id = f"srcpage_{uuid4().hex[:16]}"
            page_record = self.container.source_artifacts.create_page(
                SourcePageRecord(
                    id=source_page_id,
                    source_document_id=source_id,
                    page_number=page_number,
                    image_path=str(image_path) if image_path else None,
                    embedded_text_path=str(embedded_path),
                    selected_text_path=str(selected_path),
                    extraction_method=extraction_method,
                    confidence=confidence,
                    warnings_json=self._warnings_json(page_warnings),
                )
            )
            if ocr_result and ocr_run:
                _ocr_text, ocr_text_path, ocr_json_path, ocr_confidence = ocr_result
                self.container.source_artifacts.create_ocr_page_result(
                    OcrPageResultRecord(
                        id=f"ocrpage_{uuid4().hex[:16]}",
                        ocr_run_id=ocr_run.id,
                        source_page_id=page_record.id,
                        page_number=page_number,
                        text_path=str(ocr_text_path),
                        json_path=str(ocr_json_path),
                        confidence=ocr_confidence,
                        warnings_json=self._warnings_json(page_warnings),
                    )
                )
            page_extractions.append(
                PdfPageExtraction(
                    page_number=page_number,
                    source_page_id=source_page_id,
                    embedded_text=embedded,
                    selected_text=selected_text,
                    extraction_method=extraction_method,
                    confidence=confidence,
                    image_path=image_path,
                    embedded_text_path=embedded_path,
                    selected_text_path=selected_path,
                    warnings=page_warnings,
                )
            )
            warnings.extend(page_warnings)

        if ocr_run:
            self.container.source_artifacts.update_ocr_run(
                ocr_run.id, status="succeeded", completed_at=datetime.now(UTC)
            )

        text = "\n\n".join(page.selected_text for page in page_extractions if page.selected_text.strip())
        if not text.strip():
            raise IngestionError("Unreadable PDF: no readable text was found after extraction and OCR.")
        self._write_canonical_spans(source_id, text, page_extractions)
        self._write_pdf_ingestion_manifest(
            paths, source_id, project_id, page_count, page_extractions, warnings
        )
        return text, warnings

    def _write_canonical_spans(
        self, source_id: str, text: str, pages: list[PdfPageExtraction]
    ) -> None:
        cursor = 0
        for page in pages:
            if not page.selected_text.strip():
                continue
            start = text.find(page.selected_text, cursor)
            if start < 0:
                start = cursor
            end = start + len(page.selected_text)
            cursor = end
            self.container.source_artifacts.create_span(
                CanonicalSpanRecord(
                    id=f"span_{uuid4().hex[:16]}",
                    source_document_id=source_id,
                    page_number=page.page_number,
                    canonical_start_offset=start,
                    canonical_end_offset=end,
                    source_text_hash=hashlib.sha256(page.selected_text.encode()).hexdigest(),
                    bbox_json=None,
                    extraction_method=page.extraction_method,
                    confidence=page.confidence,
                )
            )

    def _write_pdf_ingestion_manifest(
        self,
        paths: PdfArtifactPaths,
        source_id: str,
        project_id: str,
        page_count: int,
        pages: list[PdfPageExtraction],
        warnings: list[ParserWarning],
    ) -> None:
        manifest = {
            "manifestType": "pdf_ingestion_manifest",
            "schemaVersion": "0.2.0",
            "projectId": project_id,
            "sourceDocumentId": source_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "pageCount": page_count,
            "diagnostics": [warning.model_dump(by_alias=True) for warning in warnings],
            "pages": [
                {
                    "pageNumber": page.page_number,
                    "sourcePageId": page.source_page_id,
                    "imagePath": str(page.image_path) if page.image_path else None,
                    "embeddedTextPath": str(page.embedded_text_path)
                    if page.embedded_text_path
                    else None,
                    "selectedTextPath": str(page.selected_text_path)
                    if page.selected_text_path
                    else None,
                    "extractionMethod": page.extraction_method,
                    "confidence": page.confidence,
                    "warnings": [warning.model_dump(by_alias=True) for warning in page.warnings],
                }
                for page in pages
            ],
        }
        (paths.manifests / "ingestion_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _pdf_artifact_paths(project_root: Path, source_id: str) -> PdfArtifactPaths:
        root = project_root / "sources" / source_id / "pdf"
        return PdfArtifactPaths(
            root=root,
            pages=root / "pages",
            embedded_text=root / "embedded_text",
            selected_text=root / "selected_text",
            ocr=root / "ocr",
            manifests=root / "manifests",
        )

    @staticmethod
    def _embedded_pdf_quality(text: str) -> PdfTextQuality:
        compact = re.sub(r"\s+", "", text)
        words = re.findall(r"\w+", text)
        suspicious_spacing = bool(re.search(r"(?:\w\s){8,}\w", text))
        repeated_glyphs = bool(re.search(r"([^\w\s])\1{6,}", text))
        too_few_words = len(compact) < MIN_PDF_TEXT_CHARS or len(words) < 4
        score = 0.9
        if too_few_words:
            score -= 0.55
        if suspicious_spacing:
            score -= 0.2
        if repeated_glyphs:
            score -= 0.2
        score = max(0.0, min(1.0, score))
        return PdfTextQuality(
            usable=not too_few_words and not suspicious_spacing and not repeated_glyphs,
            score=score,
        )

    def _try_render_pdf_page(
        self, pdf_path: Path, output_root: Path, page_number: int
    ) -> tuple[Path | None, ParserWarning | None]:
        if not shutil.which("pdftoppm"):
            return None, ParserWarning(
                severity=WarningSeverity.INFO,
                sourceRange=f"page {page_number}",
                message="PDF page image was not rendered because Poppler is not installed.",
                suggestedAction="Install Poppler from Model Center to enable page previews.",
            )
        try:
            return self._render_pdf_page(pdf_path, output_root, page_number), None
        except IngestionError as error:
            return None, ParserWarning(
                severity=WarningSeverity.WARNING,
                sourceRange=f"page {page_number}",
                message=str(error),
                suggestedAction="Install or repair Poppler from Model Center.",
            )

    @staticmethod
    def _render_pdf_page(pdf_path: Path, output_root: Path, page_number: int) -> Path:
        image_stem = output_root / f"page_{page_number:04d}"
        output_root.mkdir(parents=True, exist_ok=True)
        rendered = subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                "-r",
                str(PDF_RENDER_DPI),
                "-png",
                "-singlefile",
                str(pdf_path),
                str(image_stem),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        image_path = image_stem.with_suffix(".png")
        if rendered.returncode or not image_path.is_file():
            detail = rendered.stderr.strip() or "Poppler did not create a page image."
            raise IngestionError(f"PDF page render failed on page {page_number}: {detail}")
        return image_path

    @staticmethod
    def _ocr_page_image(
        image_path: Path, output_root: Path, page_number: int
    ) -> tuple[str, Path, Path, float]:
        if not shutil.which("tesseract"):
            raise IngestionError(
                "PDF OCR requires Tesseract with English language data. Install Tesseract from Model Center."
            )
        output_root.mkdir(parents=True, exist_ok=True)
        recognized = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", "eng"],
            capture_output=True,
            text=True,
            check=False,
        )
        if recognized.returncode:
            detail = recognized.stderr.strip() or "Tesseract did not return text."
            raise IngestionError(f"PDF OCR failed on page {page_number}: {detail}")
        text = recognized.stdout.strip()
        text_path = output_root / f"page_{page_number:04d}.txt"
        json_path = output_root / f"page_{page_number:04d}.json"
        confidence = 0.75 if text else 0.0
        text_path.write_text(text, encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                    "page_number": page_number,
                    "text": text,
                    "confidence": confidence,
                    "blocks": [
                        {
                            "type": "text",
                            "text": text,
                            "bbox": None,
                            "confidence": confidence,
                            "reading_order": 1,
                        }
                    ]
                    if text
                    else [],
                    "warnings": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return text, text_path, json_path, confidence

    @staticmethod
    def _warnings_json(warnings: list[ParserWarning]) -> str:
        return json.dumps([warning.model_dump(by_alias=True) for warning in warnings])

    @staticmethod
    def _require_ocr_tools() -> None:
        if not shutil.which("pdftoppm"):
            raise IngestionError(
                "PDF OCR requires Poppler's pdftoppm command. Install Poppler and add it to PATH."
            )
        if not shutil.which("tesseract"):
            raise IngestionError(
                "PDF OCR requires Tesseract with English language data. Install tesseract-ocr and add it to PATH."
            )

    @staticmethod
    def _ocr_page(pdf_path: Path, temporary_root: Path, page_number: int) -> str:
        image_stem = temporary_root / f"page-{page_number}"
        rendered = subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                "-r",
                "200",
                "-png",
                "-singlefile",
                str(pdf_path),
                str(image_stem),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        image_path = image_stem.with_suffix(".png")
        if rendered.returncode or not image_path.is_file():
            detail = rendered.stderr.strip() or "Poppler did not create a page image."
            raise IngestionError(f"PDF OCR failed while rendering page {page_number}: {detail}")
        recognized = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", "eng"],
            capture_output=True,
            text=True,
            check=False,
        )
        if recognized.returncode:
            detail = recognized.stderr.strip() or "Tesseract did not return text."
            raise IngestionError(f"PDF OCR failed on page {page_number}: {detail}")
        return recognized.stdout.strip()

    def _normalize(self, text: str) -> tuple[str, list[ParserWarning]]:
        warnings: list[ParserWarning] = []
        if "�" in text:
            warnings.append(ParserWarning(severity=WarningSeverity.WARNING, sourceRange="document", message="Replacement characters suggest OCR or encoding corruption.", suggestedAction="Review affected text before generation."))
        text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
        text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        text = text.replace("—", "--").replace("–", "-")
        paragraphs = [re.sub(r"[ \t]+", " ", item).strip() for item in re.split(r"\n\s*\n", text)]
        cleaned: list[str] = []
        for index, paragraph in enumerate(paragraphs, start=1):
            if paragraph and cleaned and paragraph == cleaned[-1]:
                warnings.append(ParserWarning(severity=WarningSeverity.WARNING, sourceRange=f"paragraph {index}", message="Duplicated adjacent header or paragraph removed.", suggestedAction="Confirm the original page break did not contain content."))
                continue
            if len(paragraph) > 1800:
                warnings.append(ParserWarning(severity=WarningSeverity.INFO, sourceRange=f"paragraph {index}", message="Unusually long paragraph detected.", suggestedAction="Review segmentation after import."))
            if paragraph:
                cleaned.append(paragraph)
        return "\n\n".join(cleaned).strip() + "\n", warnings
