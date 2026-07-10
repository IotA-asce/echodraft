## Summary

<!-- What does this PR do, and why? -->

## Linked issue / workstream

<!-- e.g. "Closes #123" or "Implements W3.1, see docs/plans/v2-implementation-roadmap.md" -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup (no behavior change)
- [ ] Documentation
- [ ] Migration / persistence change
- [ ] Other (describe above)

## Verification

Run as many of these as are relevant to this change; if a check can't run, say so explicitly.

- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy apps/api/src libs/domain-models/src libs/db/src`
- [ ] `npm run web:lint`
- [ ] `npm run web:typecheck`
- [ ] `npm run web:test:smoke` (requires `npx playwright install chromium`)
- [ ] Migration check against a disposable DB (only if persistence changed):
      `ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db uv run alembic -c libs/db/alembic.ini upgrade head`

<details>
<summary>Verification output</summary>

```text
paste relevant command output here
```

</details>

## Docs

- [ ] Docs updated to match any behavior change (or: no behavior change, no docs update needed)
- [ ] `docs/progress-tracker.md` updated if this changes roadmap/gap-analysis status

## Constraints respected

- [ ] Segment remains the atomic editable/renderable unit
- [ ] Manifests updated if pipeline inputs/outputs changed
- [ ] Segment/chapter render history stays append-only
- [ ] No audio blobs added to the relational DB (filesystem paths only)
- [ ] No mandatory-cloud assumptions introduced (local-first preserved)
- [ ] No files under `test-assets/` staged or committed
