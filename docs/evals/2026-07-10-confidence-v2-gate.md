# Extraction confidence v2 comparison gate

W3.6 was evaluated against the committed `modern-format-synthetic` corpus with:

```bash
uv run python apps/api/scripts/run_eval.py \
  --cast-v2 \
  --attribution-v2 \
  --confidence-v2 \
  --output-json /tmp/echodraft-confidence-v2-eval.json \
  --output-md /tmp/echodraft-confidence-v2-eval.md
```

| Metric | Legacy baseline | Confidence v2 | Gate |
|---|---:|---:|---|
| User-facing review items | 3 | 2 grouped tasks | pass |
| Optional tasks | n/a | 2 | pass (<20) |
| Required tasks | n/a | 0 | pass |
| Attribution accuracy | 1.00 | 1.00 | pass |
| Auto-accept precision | 1.00 | 1.00 | pass |
| Attributable-dialogue recall | 1.00 | 1.00 | pass |

The v2 count is sourced from open `review_tasks`, not the retained low-level parser diagnostics.
Migration, legacy SQLite repair, partial-open-task uniqueness, member folding, row-to-task linkage,
typed API status updates, rerun deduplication, and lock-safe tier clearing are covered by automated
tests.
