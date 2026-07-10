#!/usr/bin/env python3
"""Run the current extraction pipeline against v2 golden corpus fixtures."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from echodraft_api.config import AppSettings
from echodraft_api.eval.metrics import (
    AttributionGold,
    AttributionPrediction,
    CastGoldCharacter,
    CastPredictedCluster,
    attribution_metrics,
    cast_metrics,
    flag_metrics,
)
from echodraft_api.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "golden-corpus"
FETCHED_ROOT = REPO_ROOT / "test-assets" / "golden-corpus"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "docs" / "analysis" / "eval-baselines" / "2026-07-07-baseline.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "analysis" / "eval-baselines" / "2026-07-07-baseline.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an Echodraft v2 baseline eval report.")
    parser.add_argument("--book", action="append", dest="books", help="Book slug to evaluate.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--max-segment-chars", type=int, default=120)
    parser.add_argument(
        "--cast-v2",
        action="store_true",
        help="Enable the feature-flagged cast-v2 clustering path for comparison.",
    )
    parser.add_argument(
        "--attribution-v2",
        action="store_true",
        help="Enable the feature-flagged attribution-v2 path for comparison.",
    )
    args = parser.parse_args()

    books = args.books or ["modern-format-synthetic"]
    report = {
        "schemaVersion": "1.0.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "pipeline": _pipeline_name(
            cast_v2=args.cast_v2,
            attribution_v2=args.attribution_v2,
        ),
        "books": [
            evaluate_book(
                book,
                max_segment_chars=args.max_segment_chars,
                cast_v2_enabled=args.cast_v2,
                attribution_v2_enabled=args.attribution_v2,
            )
            for book in books
        ],
    }
    report["summary"] = summarize(report["books"])
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_md.write_text(markdown_summary(report), encoding="utf-8")
    print(f"wrote {_display_path(args.output_json)}")
    print(f"wrote {_display_path(args.output_md)}")
    return 0


def _display_path(path: Path) -> Path:
    return path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path


def _pipeline_name(*, cast_v2: bool, attribution_v2: bool) -> str:
    enabled = [
        name
        for active, name in (
            (cast_v2, "cast-v2-clustering"),
            (attribution_v2, "attribution-v2"),
        )
        if active
    ]
    return "+".join(enabled) if enabled else "current-structure-service"


def evaluate_book(
    book_slug: str,
    *,
    max_segment_chars: int,
    cast_v2_enabled: bool = False,
    attribution_v2_enabled: bool = False,
) -> dict[str, Any]:
    text = load_book_text(book_slug)
    labels = load_labels(book_slug)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"echodraft-eval-{book_slug}-") as tmp:
        tmp_path = Path(tmp)
        app = create_app(
            AppSettings(
                database_url=f"sqlite:///{tmp_path / 'eval.db'}",
                artifact_root=tmp_path / "artifacts",
                tts_settings_path=tmp_path / "tts-settings.json",
                kokoro_runtime_root=tmp_path / "kokoro" / "managed-onnx-v1",
                cast_v2_enabled=cast_v2_enabled,
                attribution_v2_enabled=attribution_v2_enabled,
            )
        )
        with TestClient(app) as client:
            project_id = create_project(client, book_slug, text)
            extract_structure(client, project_id, max_segment_chars=max_segment_chars)
            snapshot = collect_snapshot(client, project_id)
    elapsed = time.perf_counter() - started
    metrics = compute_metrics(book_slug, labels, snapshot)
    return {
        "bookSlug": book_slug,
        "wallClockSeconds": round(elapsed, 3),
        "counts": {
            "chapters": len(snapshot["chapters"]),
            "scenes": len(snapshot["scenes"]),
            "segments": len(snapshot["segments"]),
            "characters": len(snapshot["characters"]),
            "speakerAttributions": len(snapshot["attributions"]),
        },
        "metrics": metrics,
    }


def create_project(client: TestClient, book_slug: str, text: str) -> str:
    created = client.post(
        "/api/v1/projects",
        json={"title": f"Eval Baseline: {book_slug}", "rightsStatus": "declared"},
    ).json()
    project_id = str(created["id"])
    imported = client.post(
        f"/api/v1/projects/{project_id}/source/import",
        files={"file": (f"{book_slug}.txt", text.encode(), "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    wait_for_job(client, str(imported["id"]))
    return project_id


def extract_structure(client: TestClient, project_id: str, *, max_segment_chars: int) -> None:
    job = client.post(
        f"/api/v1/projects/{project_id}/structure/extract",
        json={"maxSegmentChars": max_segment_chars},
    ).json()
    wait_for_job(client, str(job["id"]))


def wait_for_job(client: TestClient, job_id: str) -> None:
    for _ in range(600):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] == "succeeded":
            return
        if job["status"] == "failed":
            raise RuntimeError(f"job {job_id} failed: {job.get('errorMessage')}")
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not finish")


def collect_snapshot(client: TestClient, project_id: str) -> dict[str, list[dict[str, Any]]]:
    chapters = client.get(f"/api/v1/projects/{project_id}/chapters").json()
    scenes = [
        scene
        for chapter in chapters
        for scene in client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()
    ]
    segments = [
        segment
        for scene in scenes
        for segment in client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    ]
    return {
        "chapters": chapters,
        "scenes": scenes,
        "segments": segments,
        "characters": client.get(f"/api/v1/projects/{project_id}/characters").json(),
        "attributions": client.get(f"/api/v1/projects/{project_id}/speaker-attributions").json(),
        "issues": client.get(f"/api/v1/projects/{project_id}/issues").json(),
        "warnings": client.get(f"/api/v1/projects/{project_id}/structure-warnings").json(),
    }


def compute_metrics(
    book_slug: str,
    labels: dict[str, Any],
    snapshot: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    attribution = attribution_metrics(
        attribution_gold(labels.get("attribution_sample", {})),
        attribution_predictions(labels.get("attribution_sample", {}), snapshot),
    )
    cast = cast_metrics(cast_gold(labels.get("roster", {})), cast_predictions(snapshot))
    flags = flag_metrics(book_slug, [*snapshot["issues"], *snapshot["warnings"]])
    return {
        "attribution": attribution.__dict__,
        "cast": cast.__dict__,
        "flags": flags.__dict__,
    }


def attribution_gold(payload: dict[str, Any]) -> list[AttributionGold]:
    return [
        AttributionGold(
            id=str(item.get("id") or item.get("quotedText") or index),
            gold_speaker=none_if_blank(item.get("goldSpeaker")),
            ambiguous=bool(item.get("ambiguous")),
            agreement=none_if_blank(item.get("agreement")),
        )
        for index, item in enumerate(payload.get("items", []))
        if isinstance(item, dict)
    ]


def attribution_predictions(
    payload: dict[str, Any],
    snapshot: dict[str, list[dict[str, Any]]],
) -> list[AttributionPrediction]:
    segments_by_id = {segment["id"]: segment for segment in snapshot["segments"]}
    predictions: list[AttributionPrediction] = []
    for index, item in enumerate(payload.get("items", [])):
        if not isinstance(item, dict):
            continue
        quoted = str(item.get("quotedText") or "").strip()
        attribution = find_attribution_for_quote(quoted, snapshot["attributions"], segments_by_id)
        predictions.append(
            AttributionPrediction(
                id=str(item.get("id") or quoted or index),
                predicted_speaker=none_if_blank(attribution.get("speakerName") if attribution else None),
                confidence=float(attribution.get("confidence") or 0.0) if attribution else 0.0,
            )
        )
    return predictions


def find_attribution_for_quote(
    quote: str,
    attributions: list[dict[str, Any]],
    segments_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    normalized_quote = normalize_text(quote)
    for attribution in attributions:
        segment = segments_by_id.get(str(attribution.get("segmentId") or ""))
        if segment and normalized_quote in normalize_text(str(segment.get("textContent") or "")):
            return attribution
    return None


def cast_gold(payload: dict[str, Any]) -> list[CastGoldCharacter]:
    return [
        CastGoldCharacter(
            canonical_name=str(item.get("canonicalName") or ""),
            aliases=tuple(str(alias) for alias in item.get("aliases", []) if str(alias).strip()),
        )
        for item in payload.get("items", [])
        if isinstance(item, dict)
    ]


def cast_predictions(snapshot: dict[str, list[dict[str, Any]]]) -> list[CastPredictedCluster]:
    clusters = []
    for character in snapshot["characters"]:
        if character.get("mergedIntoCharacterId"):
            continue
        surfaces = [str(character.get("displayName") or "")]
        surfaces.extend(str(alias) for alias in character.get("aliases", []) if str(alias).strip())
        clusters.append(CastPredictedCluster(tuple(surfaces)))
    return clusters


def load_book_text(book_slug: str) -> str:
    committed = FIXTURE_ROOT / book_slug / "raw" / f"{book_slug}.txt"
    fetched = FETCHED_ROOT / book_slug / "raw" / f"{book_slug}.txt"
    if committed.exists():
        return committed.read_text(encoding="utf-8")
    if fetched.exists():
        return fetched.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"No text found for {book_slug}. Run apps/api/scripts/fetch_eval_corpus.py first."
    )


def load_labels(book_slug: str) -> dict[str, Any]:
    labels_root = FIXTURE_ROOT / book_slug / "labels"
    return {
        path.stem.replace("-", "_"): json.loads(path.read_text(encoding="utf-8"))
        for path in labels_root.glob("*.json")
    }


def summarize(books: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "bookCount": len(books),
        "totalWallClockSeconds": round(sum(float(book["wallClockSeconds"]) for book in books), 3),
        "totalFlags": sum(int(book["metrics"]["flags"]["flag_count"]) for book in books),
    }


def markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# v2 Baseline Eval Report",
        "",
        f"Generated at: `{report['generatedAt']}`",
        "",
        "| Book | Wall clock seconds | Attribution accuracy | Cast F1 | Flags |",
        "|---|---:|---:|---:|---:|",
    ]
    for book in report["books"]:
        metrics = book["metrics"]
        lines.append(
            "| {book} | {wall:.3f} | {accuracy:.3f} | {cast_f1:.3f} | {flags} |".format(
                book=book["bookSlug"],
                wall=float(book["wallClockSeconds"]),
                accuracy=float(metrics["attribution"]["accuracy"]),
                cast_f1=float(metrics["cast"]["roster_f1"]),
                flags=int(metrics["flags"]["flag_count"]),
            )
        )
    return "\n".join(lines) + "\n"


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def none_if_blank(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())
