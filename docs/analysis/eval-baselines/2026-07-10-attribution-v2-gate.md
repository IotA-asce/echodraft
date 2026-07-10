# Attribution v2 comparison gate

W3.5 was evaluated against the committed `modern-format-synthetic` corpus with:

```bash
uv run python apps/api/scripts/run_eval.py \
  --cast-v2 \
  --attribution-v2 \
  --output-json /tmp/echodraft-attribution-v2-eval.json \
  --output-md /tmp/echodraft-attribution-v2-eval.md
```

| Metric | 2026-07-07 baseline | Attribution v2 | Gate |
|---|---:|---:|---|
| Attribution accuracy | 1.00 | 1.00 | pass |
| Auto-accept precision | 1.00 | 1.00 | pass |
| Attributable-dialogue recall | 1.00 | 1.00 | pass |
| Human-agreement rate | 1.00 | 1.00 | pass |
| Evaluated rows with explicit speakers | 5/5 | 5/5 | pass |

The local structured-extraction model was not installed during the harness run, so the live corpus
run exercised the deterministic pre-pass fallback and proved the flag does not regress attribution.
Deterministic integration tests exercise the actual LLM-primary path with scene-window TARGET/
CONTEXT isolation, Character Bible identity resolution, conversation state, three independent vote
samples, majority application, user-lock preservation, book-level alternation repair, and additive
manifest output.
