import json
import time
from io import BytesIO
from pathlib import Path

from docx import Document
from ebooklib import epub
import pytest

import echodraft_api.ingestion as ingestion
from echodraft_api.ingestion import IngestionError, IngestionService


def project_id(client) -> str:
    response = client.post("/api/v1/projects", json={"title": "Import Test", "rightsStatus": "declared"})
    assert response.status_code == 201
    return response.json()["id"]


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(50):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("Import job did not finish")


def docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("A DOCX manuscript line.")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def epub_bytes(tmp_path: Path) -> bytes:
    book = epub.EpubBook()
    book.set_identifier("sample")
    book.set_title("Sample")
    book.set_language("en")
    chapter = epub.EpubHtml(title="One", file_name="one.xhtml", lang="en")
    chapter.content = "<h1>One</h1><p>An EPUB manuscript line.</p>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    target = tmp_path / "sample.epub"
    epub.write_epub(str(target), book)
    return target.read_bytes()


def pdf_bytes(text: str) -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + payload + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    result.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(result)


def import_bytes(client, project: str, name: str, data: bytes, mime: str = "application/octet-stream") -> dict:
    response = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": (name, data, mime)},
        data={"rightsAcknowledged": "true"},
    )
    assert response.status_code == 202, response.text
    return wait_for_job(client, response.json()["id"])


def test_txt_import_creates_deterministic_canonical_artifacts_and_manifest(client) -> None:
    project = project_id(client)
    job = import_bytes(client, project, "story.txt", b"A\r\n\r\nA\r\n\r\nAn   ending.\r\n")
    assert job["status"] == "succeeded"
    source = client.get(f"/api/v1/projects/{project}/source").json()
    assert source["preview"] == "A\n\nAn ending.\n"
    manifest = json.loads(Path(source["manifestPath"]).read_text())
    assert manifest["payload"]["canonicalChecksum"]
    assert any(item["message"].startswith("Duplicated") for item in source["warnings"])


def test_current_ingestion_documents_page_marker_pollution(client) -> None:
    project = project_id(client)
    text = (
        "Ooh! I felt a wiggle that time.\n\n"
        "<!-- Page 9 -->\n\n"
        "Open! My eyelids creep up."
    )
    job = import_bytes(client, project, "page-marker.md", text.encode())
    assert job["status"] == "succeeded"

    source = client.get(f"/api/v1/projects/{project}/source").json()
    assert source["preview"] == text + "\n"
    assert "<!-- Page 9 -->" in Path(source["canonicalPath"]).read_text(encoding="utf-8")
    assert not source["warnings"]


def test_markdown_docx_and_epub_import(client, tmp_path: Path) -> None:
    for name, data in [("story.md", b"# Heading\n\nText"), ("story.docx", docx_bytes()), ("story.epub", epub_bytes(tmp_path))]:
        project = project_id(client)
        job = import_bytes(client, project, name, data)
        assert job["status"] == "succeeded", job["errorMessage"]
        assert client.get(f"/api/v1/projects/{project}/source").json()["preview"]


def test_pdf_import_extracts_text_and_preserves_manifest(client) -> None:
    project = project_id(client)
    job = import_bytes(
        client,
        project,
        "story.pdf",
        pdf_bytes("A PDF manuscript line with enough readable characters."),
        "application/pdf",
    )
    assert job["status"] == "succeeded", job["errorMessage"]
    source = client.get(f"/api/v1/projects/{project}/source").json()
    assert source["mimeType"] == "application/pdf"
    assert "A PDF manuscript line with enough readable characters." in source["preview"]
    assert Path(source["originalPath"]).suffix == ".pdf"


def test_pdf_ocr_candidates_and_failures(app, monkeypatch, tmp_path: Path) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        is_encrypted = False

        def __init__(self, pages: list[FakePage]) -> None:
            self.pages = pages

    service = IngestionService(app.state.container)
    monkeypatch.setattr(
        ingestion,
        "PdfReader",
        lambda _: FakeReader([FakePage("A readable page with sufficient extracted text."), FakePage("")]),
    )
    monkeypatch.setattr(IngestionService, "_require_ocr_tools", staticmethod(lambda: None))
    monkeypatch.setattr(
        IngestionService, "_ocr_page", staticmethod(lambda _pdf, _root, page: f"OCR page {page} text.")
    )
    text, warnings = service._extract_pdf(tmp_path / "mixed.pdf")
    assert "A readable page with sufficient extracted text." in text and "OCR page 2 text." in text
    assert text.split("\n\n") == [
        "A readable page with sufficient extracted text.",
        "OCR page 2 text.",
    ]
    assert warnings[0].source_range == "page 2"

    monkeypatch.undo()
    monkeypatch.setattr(ingestion, "PdfReader", lambda _: FakeReader([FakePage("")]))
    monkeypatch.setattr(ingestion.shutil, "which", lambda _: None)
    with pytest.raises(IngestionError, match="pdftoppm"):
        service._extract_pdf(tmp_path / "needs-ocr.pdf")

    monkeypatch.undo()
    monkeypatch.setattr(ingestion, "PdfReader", lambda _: FakeReader([FakePage("")]))
    monkeypatch.setattr(
        ingestion.shutil, "which", lambda command: "/usr/bin/pdftoppm" if command == "pdftoppm" else None
    )
    with pytest.raises(IngestionError, match="Tesseract"):
        service._extract_pdf(tmp_path / "needs-tesseract.pdf")

    monkeypatch.undo()
    monkeypatch.setattr(
        ingestion, "PdfReader", lambda _: FakeReader([FakePage("") for _ in range(151)])
    )
    with pytest.raises(IngestionError, match="150 pages"):
        service._extract_pdf(tmp_path / "too-many.pdf")


def test_scanned_pdf_path_uses_mocked_ocr_for_every_page(app, monkeypatch, tmp_path: Path) -> None:
    class FakePage:
        def extract_text(self) -> str:
            return ""

    class FakeReader:
        is_encrypted = False
        pages = [FakePage(), FakePage(), FakePage()]

    service = IngestionService(app.state.container)
    monkeypatch.setattr(ingestion, "PdfReader", lambda _: FakeReader())
    monkeypatch.setattr(IngestionService, "_require_ocr_tools", staticmethod(lambda: None))
    monkeypatch.setattr(
        IngestionService,
        "_ocr_page",
        staticmethod(lambda _pdf, _root, page: f"Recognized scanned page {page}."),
    )

    text, warnings = service._extract_pdf(tmp_path / "scanned.pdf")

    assert text == (
        "Recognized scanned page 1.\n\n"
        "Recognized scanned page 2.\n\n"
        "Recognized scanned page 3."
    )
    assert [warning.source_range for warning in warnings] == ["page 1", "page 2", "page 3"]


def test_ocr_warning_and_failed_parse_preserve_original(client) -> None:
    project = project_id(client)
    assert import_bytes(client, project, "ocr.txt", "Bad � text".encode())["status"] == "succeeded"
    source = client.get(f"/api/v1/projects/{project}/source").json()
    assert source["warnings"][0]["severity"] == "warning"
    project = project_id(client)
    failed = import_bytes(client, project, "broken.docx", b"not a docx")
    assert failed["status"] == "failed"
    source = client.get(f"/api/v1/projects/{project}/source").json()
    assert source["status"] == "failed"
    assert Path(source["originalPath"]).exists()
    project = project_id(client)
    failed = import_bytes(client, project, "broken.pdf", b"not a pdf", "application/pdf")
    assert failed["status"] == "failed"


def test_reparse_preserves_prior_manifest(client) -> None:
    project = project_id(client)
    assert import_bytes(client, project, "story.txt", b"One paragraph.")["status"] == "succeeded"
    first = client.get(f"/api/v1/projects/{project}/source").json()
    response = client.post(f"/api/v1/projects/{project}/source/reparse", json={"parserVersion": "ingestion-0.1.1"})
    assert response.status_code == 202
    assert wait_for_job(client, response.json()["id"])["status"] == "succeeded"
    second = client.get(f"/api/v1/projects/{project}/source").json()
    assert Path(first["manifestPath"]).exists()
    assert first["manifestPath"] != second["manifestPath"]
