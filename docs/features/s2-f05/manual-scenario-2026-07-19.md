# S2-F05 authenticated scenario record — 2026-07-19

## Scope and identity

The scenario uses the authenticated local operator identity `operator` and
the run-scoped API/UI boundary. The browser automation dependency is not
installed in this workspace, so the UI behavior was exercised through the
existing React/Vitest harness and the authenticated FastAPI TestClient
boundary; no unauthenticated or local-only state was treated as evidence.

## Executed scenario

1. Loaded the empty Feasibility view and confirmed that resolution cannot be
   submitted until the backend supplies the exact source, runtime candidates,
   catalogue, and registry snapshot.
2. Submitted the authenticated feasibility request with source `18.2.4`, the
   versioned catalogue and registry checksum, and a paired Node/npm/npx
   candidate. The response displayed the `18.x → 19.x → 20.x → 21.x` ladder,
   exact Stage 1 profile, six immutable artifacts, and pending G05.
3. Submitted `approve_with_comment` with a non-empty review comment. The API
   returned an accepted G05 decision and the UI reloaded the authoritative
   snapshot.
4. Negative case: changed the package checksum before submitting the G05
   decision. The authenticated request was rejected with
   `G05_PACKAGE_INTEGRITY_FAILED`; the pending gate and evidence were not
   trusted. Binding/expiry rejection emits and persists `G05_STALE`.

## Evidence commands

```powershell
python -m pytest backend/tests/test_compatibility_application_service_s2_f05_i01.py backend/tests/test_compatibility_verification_s2_f05_i04.py -q
cd frontend
npm test -- src/components/__tests__/FeasibilityPanel.test.tsx
npm run typecheck
npm run lint
```

The repository’s browser-driver limitation is recorded above; the automated
authenticated boundary and negative-case evidence remain reproducible.
