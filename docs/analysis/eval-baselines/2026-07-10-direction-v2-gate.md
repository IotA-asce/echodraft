# Direction v2 progressive-delivery gate

W3.7 was evaluated with every extraction-v2 flag enabled:

```bash
uv run python apps/api/scripts/run_eval.py \
  --cast-v2 --attribution-v2 --confidence-v2 \
  --direction-v2 --progressive-delivery \
  --output-json /tmp/echodraft-direction-v2-eval.json \
  --output-md /tmp/echodraft-direction-v2-eval.md
```

| Metric | Result | Gate |
|---|---:|---|
| First provisional chapter direction-ready | 0.029 s | pass (<600 s) |
| Total extraction wall-clock | 0.228 s | informational |
| Optional grouped review tasks | 1 | pass (<20) |
| Required tasks | 0 | pass |

The committed fixture validates event/checkpoint timing and pipeline ordering, not the separate
500-page mid-tier hardware milestone. Automated tests additionally cover stable chapter-priority
ordering, provisional and final readiness events, parallel scene-window refinement, Character Bible
profile inputs, TARGET-only writes, controlled direction values, locked-row preservation, and
versioned manifest output.
