#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from echodraft_api.orchestrator import HardwareProbe
from echodraft_api.tts_bakeoff import preflight, select_candidate

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JSON = REPO_ROOT / "docs" / "pipeline" / "tts" / "bakeoff-results.json"
DEFAULT_MD = REPO_ROOT / "docs" / "pipeline" / "tts" / "bakeoff-results.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the consent-safe Tier-S TTS bake-off gate.")
    parser.add_argument("--results", type=Path, help="Optional completed candidate-results JSON.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    candidate_results = (
        json.loads(args.results.read_text(encoding="utf-8")) if args.results else []
    )
    if not isinstance(candidate_results, list):
        raise ValueError("Candidate results must be a JSON array.")
    report = {
        "schemaVersion": "1.0.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        **preflight(HardwareProbe().snapshot()),
        "candidateResults": candidate_results,
        "selectedCandidate": select_candidate(candidate_results),
    }
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.output_md.write_text(markdown_report(report), encoding="utf-8")
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    return 0


def markdown_report(report: dict[str, object]) -> str:
    hardware = report["hardware"]
    assert isinstance(hardware, dict)
    candidates = report["candidates"]
    assert isinstance(candidates, list)
    lines = [
        "# Tier-S TTS Bake-off Results",
        "",
        f"Generated: `{report['generatedAt']}`",
        "",
        "## Hardware",
        "",
        f"- Platform: `{hardware.get('platform')}`",
        f"- CPU count: `{hardware.get('cpu_count')}`",
        f"- RAM GiB: `{hardware.get('total_ram_gib')}`",
        f"- Device: `{hardware.get('ttsDevice')}`",
        "",
        "## Candidate preflight",
        "",
        "| Candidate | License gate | Runtime installed | Executable now |",
        "|---|---:|---:|---:|",
    ]
    for raw in candidates:
        assert isinstance(raw, dict)
        lines.append(
            f"| [{raw['display_name']}]({raw['model_card_url']}) | "
            f"{raw['license_gate']} | {raw['runtimeInstalled']} | "
            f"{raw['eligibleForExecution']} |"
        )
    selected = report.get("selectedCandidate")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Selected candidate: `{selected}`" if selected else (
                "No Tier-S engine selected. Candidate runtimes and model weights are not installed; "
                "explicit Model Center license/download consent is required before R10 can run."
            ),
            "",
            "The selector fails closed until every required script renders, R10 stability passes, "
            "R13 is `pass`, and blind emotion/naturalness ratings are supplied.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
