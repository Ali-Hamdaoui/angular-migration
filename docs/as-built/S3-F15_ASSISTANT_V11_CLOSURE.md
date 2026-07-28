# S3-F15 Assistant V1.1 closure

The V1.1 slice keeps the Assistant run-scoped and read-only. Authenticated routes authorize the run owner, resolve one selected/latest conversation, rebuild the workflow projection, classify natural questions through the capability registry, bound context, invoke the governed Assistant role with a 20,000-token output ceiling, validate approved evidence citations, and persist the exchange plus lifecycle events.

Request IDs are generated per normal submit. Replays reuse the same request ID and payload; user Retry supplies a new request ID and optional `retry_of_message_id`. Assistant telemetry no longer advances the workflow semantic state version; lifecycle sequence remains operational metadata. Historical answers become stale only when the authoritative run state version changes.

Context packaging records counted sections, selected/omitted identifiers, limit, and truncation metadata. Evidence selection is same-run, approved, immutable, checksum-bound, lineage-bound, redacted, and bounded. The structured response remains read-only and unknown fields stay unavailable. Durable lifecycle events support sequence cursors and frontend gap-triggered history restoration.

The frontend retains the backend conversation ID, restores history on remount, provides optimistic user messages, retry identity, stale markers, validated evidence, reconnect state, and read-only navigation data. `20260727_19_assistant_v11_fields` is additive and preserves existing AMFA-221 rows.

Focused validation:

```text
backend: pytest tests/test_assistant_v11.py tests/test_assistant_amfa221.py tests/test_amfa221_vertical_demo.py -q  → 26 passed
backend: ruff check app tests → passed
backend: compileall -q app tests → passed
frontend: npm run typecheck → passed
frontend: npm run lint → passed with one unrelated existing warning
frontend: vitest focused AssistantPanel/assistantReplay files → 3 passed
```

Explicitly unavailable fields remain unavailable where this branch has no authoritative owner, including some gate, stage, next-action, and workflow projection details in sparse fixtures. Alembic graph validation remains blocked by the pre-existing missing `20260721_01` revision referenced elsewhere in the branch.
