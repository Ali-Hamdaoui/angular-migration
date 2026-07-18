# S2-F02 Progress

## Completed issues

- `S2-F02-I01`: deterministic structural parity-baseline builders and application contract.
- `S2-F02-I02`: SQLite persistence, immutable artifacts, versioned API, and durable events.
- `S2-F02-I03`: authoritative frontend parity-evidence viewer.
- `S2-F02-I04`: regression coverage for typed API paths, UI authoritative inputs/stale handling, persisted artifact/event evidence, and the manual verification record.

## Manual verification

1. Start from a G03-approved run with checksum-registered baseline evidence.
2. Open the parity evidence panel and request inspection.
3. Confirm routes, backend/auth indicators, sensitive files, unknown/manual markers, and immutable artifact links are shown.
4. Repeat with a stale state version or mismatched prerequisite checksum; confirm the backend rejects it and the UI reloads authoritative state.

The evidence is structural only; browser/visual proof and runtime traffic capture remain manual/out of scope.
