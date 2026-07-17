# S1-F14 Progress

## Completed

- I01: deterministic baseline qualification now runs through `BaselineG03ApplicationService` and the Transition Service.
- I02: assessment/G03 models, Alembic migration, typed APIs, durable events, and checksum-registered baseline artifacts are implemented.
- I03: the Control Tower renders qualification evidence and submits G03 actions through authoritative APIs.
- I04: optimistic version/idempotency checks, artifact metadata, SSE event vocabulary, restart rehydration, and frontend/backend verification are covered.

## Generated artifacts

`frontend/next-env.d.ts` intentionally tracks Next.js 16's generated `./.next/types/routes.d.ts` location and is validated by `npm run build`. Disposable test output directories are intentionally ignored/retained when Windows holds open handles; they are not source artifacts.
