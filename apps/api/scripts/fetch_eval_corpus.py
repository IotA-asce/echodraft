#!/usr/bin/env python3
"""Fetch the v2 golden evaluation corpus into git-ignored test-assets."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_METADATA_ROOT = REPO_ROOT / "tests" / "fixtures" / "golden-corpus"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "test-assets" / "golden-corpus"
SOURCE_SHA_FILENAME = ".source.sha256"
USER_AGENT = "Echodraft eval corpus fetcher"


@dataclass(frozen=True)
class CorpusBook:
    slug: str
    title: str
    author: str
    gutenberg_id: int
    source_url: str
    checksum_sha256: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and verify the public-domain v2 golden corpus."
    )
    parser.add_argument(
        "--metadata-root",
        type=Path,
        default=DEFAULT_METADATA_ROOT,
        help="Directory containing committed per-book meta.json files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Git-ignored directory where fetched raw text is written.",
    )
    parser.add_argument(
        "--book",
        action="append",
        dest="books",
        help="Fetch only the given slug. May be passed more than once.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when the local sidecar checksum already matches.",
    )
    args = parser.parse_args()

    metadata_root = args.metadata_root.resolve()
    output_root = args.output_root.resolve()
    requested = set(args.books or [])
    books = load_books(metadata_root)
    unknown = requested - {book.slug for book in books}
    if unknown:
        parser.error(f"unknown book slug(s): {', '.join(sorted(unknown))}")

    selected = [book for book in books if not requested or book.slug in requested]
    if not selected:
        parser.error(f"no corpus metadata found under {metadata_root}")

    for book in selected:
        fetch_book(book, output_root, force=args.force)
    return 0


def load_books(metadata_root: Path) -> list[CorpusBook]:
    books: list[CorpusBook] = []
    for path in sorted(metadata_root.glob("*/meta.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("source") != "project-gutenberg":
            continue
        books.append(
            CorpusBook(
                slug=str(payload["slug"]),
                title=str(payload["title"]),
                author=str(payload["author"]),
                gutenberg_id=int(payload["gutenbergId"]),
                source_url=str(payload["sourceUrl"]),
                checksum_sha256=str(payload["checksumSha256"]),
            )
        )
    return books


def fetch_book(book: CorpusBook, output_root: Path, *, force: bool) -> None:
    raw_dir = output_root / book.slug / "raw"
    output_path = raw_dir / f"{book.slug}.txt"
    sidecar_path = raw_dir / SOURCE_SHA_FILENAME
    if not force and output_path.exists() and sidecar_path.exists():
        existing_sha = sidecar_path.read_text(encoding="utf-8").strip()
        if existing_sha == book.checksum_sha256:
            print(f"{book.slug}: already present", flush=True)
            return

    print(f"{book.slug}: fetching {book.source_url}", flush=True)
    source_bytes = download(book.source_url)
    observed = sha256(source_bytes).hexdigest()
    if observed != book.checksum_sha256:
        raise SystemExit(
            f"{book.slug}: checksum mismatch for {book.source_url}\n"
            f"expected {book.checksum_sha256}\n"
            f"observed {observed}"
        )

    text = strip_gutenberg_boilerplate(decode_text(source_bytes))
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    sidecar_path.write_text(f"{observed}\n", encoding="utf-8")
    print(f"{book.slug}: wrote {output_path.relative_to(REPO_ROOT)}", flush=True)


def download(url: str) -> bytes:
    if curl := shutil.which("curl"):
        completed = subprocess.run(
            [
                curl,
                "-L",
                "--fail",
                "--max-time",
                "60",
                "-A",
                USER_AGENT,
                "-sS",
                url,
            ],
            check=True,
            capture_output=True,
        )
        return completed.stdout
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return response.read()


def decode_text(source_bytes: bytes) -> str:
    return source_bytes.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def strip_gutenberg_boilerplate(text: str) -> str:
    start = re.search(
        r"(?im)^\\*\\*\\* START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK .+? \\*\\*\\*\\s*$",
        text,
    )
    end = re.search(
        r"(?im)^\\*\\*\\* END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK .+? \\*\\*\\*\\s*$",
        text,
    )
    body = text[start.end() :] if start else text
    if end:
        end_index = end.start() - (start.end() if start else 0)
        body = body[:end_index]
    return body.strip() + "\n"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
