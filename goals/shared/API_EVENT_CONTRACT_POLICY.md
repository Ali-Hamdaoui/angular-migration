# API, Event, and Artifact Contract Policy

- Versioned FastAPI routes and stable machine-readable errors.
- Mutations include expected state version, actor/correlation metadata, and idempotency key.
- Durable events use a common envelope: event ID, run/stage IDs, sequence, state versions, type, timestamp, safe payload, artifact refs.
- State and required artifacts commit atomically or in a documented finalize-then-transition protocol.
- Frontend generated types/events come from backend authoritative schemas.
- Aggregate OpenAPI/client/event files are regenerated once during integration unless the goal owns the generator source.
- Cross-goal handoffs conform to `shared/contracts/*.schema.json` and `CONTRACT_REGISTRY.yaml`.
