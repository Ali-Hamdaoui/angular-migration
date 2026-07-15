# Sprint 0 Demo Notes

The Sprint 0 demo should call out these architecture boundaries before showing the Control Tower:

- Backend state is the source of truth.
- Commands are structured and backend-authorized.
- Original source remains immutable.
- Mutation happens only inside the internal run workspace.
- Artifacts are checksum-bound evidence.
- Manual and deferred validation gates are never shown as passed.

## Angular 18 Fixture

Use `external synthetic Angular fixture/` as the controlled source application for the Sprint 0 demo. The fixture includes route, lazy-route, API, interceptor, form-validation, style, environment, proxy, known-failure, and prompt-injection signals. Its expectation manifests live under `external synthetic Angular fixture/expectations/`.

Sprint 0 regression tests copy the fixture into a temporary internal workspace and verify source integrity. Do not run migration mutations directly against the fixture directory.

Reference the ADR index at [docs/adr/README.md](adr/README.md) during review.
