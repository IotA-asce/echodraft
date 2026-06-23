import json
import time
from io import BytesIO
from pathlib import Path

from docx import Document
from ebooklib import epub


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


def test_markdown_docx_and_epub_import(client, tmp_path: Path) -> None:
    for name, data in [("story.md", b"# Heading\n\nText"), ("story.docx", docx_bytes()), ("story.epub", epub_bytes(tmp_path))]:
        project = project_id(client)
        job = import_bytes(client, project, name, data)
        assert job["status"] == "succeeded", job["errorMessage"]
        assert client.get(f"/api/v1/projects/{project}/source").json()["preview"]


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
