# Task 9 report: make migration evidence discoverable

## Scope

Task 9 adds a backend-authoritative Evidence investigation workspace. The list accepts the existing registered artifact references or their deterministic presentation adapters. It supports case-insensitive search across the human title and raw path/checksum/type metadata, category filters, stage filters, deterministic grouping/order, local selection, preview loading, explicit failure state, and provenance disclosure. Desktop uses a list/detail split view; mobile switches to list-to-detail with a Back to evidence control. Selection never writes to backend state.

`ArtifactPreviewPanel` now leads with the human title and existing viewer, while ID, raw path, type, stage, attempt, creator, timestamp, and checksum remain available under Provenance → Technical details. Existing diff, Markdown, and log viewers and `getArtifactById` loading are preserved.

## Strict RED evidence

Before implementation, the new EvidenceWorkspace suite failed at module resolution because the workspace did not exist:

```text
Error: Failed to resolve import "@/components/control-tower/EvidenceWorkspace"
```

## Focused GREEN evidence

```text
npm test -- --run src/presentation/__tests__/artifacts.test.ts src/components/control-tower/__tests__/EvidenceWorkspace.test.tsx src/components/__tests__/ArtifactViewers.test.tsx
Test Files: 3 passed
Tests: 28 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
```

The full frontend suite was intentionally not run for this task. No backend files or API contracts changed.

## Review fix round 1

Independent review identified three lifecycle/accessibility gaps. Preview state is now bound to the artifact run, ID, and checksum plus a request generation. Selecting another artifact remounts and clears the preview; late responses and mismatched response envelopes are ignored or shown as unavailable. Detail selection moves focus to the artifact heading, and Back restores focus to the originating result button. Missing creator metadata is rendered as **Unavailable** rather than an invented backend producer.

### Strict RED evidence

Before the fix, the new tests failed because the panel retained `Loading`/previous content across artifact changes, creator `null` rendered `backend`, and selection left focus on the document body:

```text
Test Files: 2 failed
Tests: 3 failed, 8 passed
```

### Focused GREEN evidence

```text
npm test -- --run src/presentation/__tests__/artifacts.test.ts src/components/control-tower/__tests__/EvidenceWorkspace.test.tsx src/components/__tests__/ArtifactViewers.test.tsx
Test Files: 3 passed
Tests: 31 passed

npm run typecheck
Exit code: 0

npm run lint
Exit code: 0

git diff --check
Exit code: 0
```

The full frontend suite remains intentionally unrun.
