# Angular 18 Basic Fixture

This fixture is the Sprint 0 controlled Angular 18 reference application for the AI Frontend Migration Factory. It is intentionally small, but it includes enough signals for discovery, baseline, parity, backend-contract, risk, and prompt-injection regression tests.

## Runtime

- Angular CLI: 18.2.12
- Angular packages: 18.2.13
- npm lockfile: committed `package-lock.json`
- Expected Node.js profile: Node 20.19.x or Node 22.12.x according to the platform runtime policy for Angular 18 fixtures
- Expected npm profile: npm 10.x

## Commands

```bash
npm ci
npm run build
npm run test
```

`npm run lint` is present as metadata for discovery, but no lint builder is configured in this fixture. Sprint 0 regression tests validate manifests and source integrity without running Angular package installation.

## Signals Included

- Standalone Angular application bootstrap.
- Primary routes for home, orders, about, and wildcard redirect.
- Lazy route for `/orders` using `loadComponent`.
- HTTP API service for `POST /orders`.
- Functional HTTP interceptor adding `X-Fixture-App` and API base URL behavior.
- Reactive form validation for customer name and quantity.
- Component and global CSS theme signals.
- Environment files and proxy configuration.
- Unit-test metadata.
- Known-failure fingerprint fixture.
- Prompt-injection text explicitly marked as test data.

## Expectations

The `expectations/` directory contains version-controlled manifests for discovery, baseline, routes, backend contracts, changed-file risk, parity, source runtime, and source integrity. Tests must copy this fixture into an internal workspace before mutation and must verify the fixture source hash remains unchanged.
