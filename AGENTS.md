## Repository purpose
echodraft is a local-first AI audiobook production system.
Core priorities:
1. segment-first architecture
2. manifest-driven pipeline
3. patchability over one-shot generation
4. local-first privacy
5. conservative, tasteful audio production

## Golden implementation workflow
For every feature implementation, Codex must follow this exact sequence:

1. Create a feature branch from the current target branch.
2. Implement the requested change only within the required scope.
3. Run relevant verification commands.
4. Commit the change with a clear commit message.
5. Merge the feature branch back into the target branch.
6. Push the updated target branch and the feature branch if needed.

Do not skip branch creation.
Do not code directly on main.
Do not merge unverified changes unless the user explicitly instructs you to do so.

## Verification rule
Before merge, run as many of these as relevant:
- backend tests
- frontend tests
- lint
- typecheck
- migration checks
- smoke test for the touched workflow

If any check cannot run, state it explicitly before merge.

## Repo layout
- apps/api -> FastAPI entrypoint
- apps/web -> Next.js frontend
- services/* -> domain services
- libs/domain-models -> shared schemas
- libs/db -> ORM + migrations
- docs/ -> architecture and operating docs

## Done means
A feature is done only if:
- code is implemented
- tests/lint/typecheck were run where applicable
- docs were updated if behavior changed
- changes were committed
- merge was completed
- push was completed

## Constraints
- Keep changes modular.
- Preserve append-only render history.
- Do not store audio blobs in the relational DB.
- Keep segment as the atomic editable/renderable unit.
- Avoid introducing cloud-only assumptions into MVP code.
