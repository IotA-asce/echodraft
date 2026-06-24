import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup
from docx import Document
from ebooklib import ITEM_DOCUMENT, epub  # type: ignore[import-untyped]
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from echodraft_db.models import SourceDocumentRecord
from echodraft_domain import ParserWarning, RightsStatus, WarningSeverity

from .container import AppContainer

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PARSER_VERSION = "ingestion-0.1.0"
MIN_PDF_TEXT_CHARS = 20
MAX_PDF_OCR_PAGES = 150
SUPPORTED = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".epub": "application/epub+zip",
    ".pdf": "application/pdf",
}


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
            text, warnings = self._extract(original_path, filename)
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

    def _extract(self, path: Path, filename: str) -> tuple[str, list[ParserWarning]]:
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
            return self._extract_pdf(path)
        raise IngestionError("Unsupported file type.")

    def _extract_pdf(self, path: Path) -> tuple[str, list[ParserWarning]]:
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
