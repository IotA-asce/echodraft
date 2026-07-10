# Tier-S Bake-off Harness Plan

**Goal:** Make Tier-S selection reproducible and fail closed when candidate runtimes, license
acceptance, ASR, or human ratings are missing.

**Architecture:** Define the fixed eight-script corpus and official candidate/license ledger in a
pure module. The harness records hardware and runtime preflight, measures WAV stability/RTF/audio
health, accepts external ASR and blind-listening scores, and selects only candidates that pass R10
and R13. A CLI writes JSON and Markdown evidence. It never downloads model weights; Model Center
consent remains a separate prerequisite.

**Tech Stack:** stdlib WAV/import inspection, existing audio analysis and ASR word scoring,
hardware probe, argparse, pytest.

---

1. Encode the candidate license ledger from official model cards/repositories.
2. Encode the fixed evaluation corpus, including a 1,500+ word stability case.
3. Implement preflight, per-WAV measurement, hard-gate selection, and report rendering.
4. Run the harness on this Mac and record the unresolved installation/consent blockers honestly.
5. Verify the scorer and fail-closed selector with synthetic WAV/results fixtures.
