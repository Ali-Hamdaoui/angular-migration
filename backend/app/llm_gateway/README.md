# LLM Gateway

Owns the Azure OpenAI gateway abstraction, mock request/response contracts,
secret redaction, untrusted-content boundaries, usage aggregation, budgets, and
pricing snapshots.

The gateway must not expose API keys, execute tools or commands, mutate
workspaces, trust repository content as policy, or let agents bypass backend
execution authority.

## Sprint 0 Mock Boundary

AMF-S0-14 implements a backend-only mock gateway. It never calls Azure OpenAI,
stores raw prompts, stores hidden reasoning, or authorizes execution. Mock
agents request optional LLM help through `BaseMockAgent.request_llm_assistance`,
which delegates to `MockLlmGateway`.

## Contracts

The gateway contracts live in `app.llm_gateway.contracts`:

- `LlmRequest`
- `LlmResponse`
- `LlmUsageRecord`
- `LlmCostSummary`
- `LlmBudgetDecision`
- `PromptRedactionResult`

Requests separate trusted `system_policy` from context segments. Repository,
source, log, diff, and compiler context must be labeled as untrusted data.

## Redaction and Cost

`redact_prompt_text` removes API keys, authorization headers, environment
secrets, private registry tokens, connection-string secrets, and production URL
values before mock provider submission or artifact storage.

The mock gateway snapshots configured pricing per usage record. Defaults match
the Sprint 0 pricing assumption when configuration is unset: input $0.25 per 1M
tokens and output $2.00 per 1M tokens.

Budget decisions are structured and can continue, warn, block new LLM calls,
request deterministic fallback, enter diagnostic hold, or require approval. The
Sprint 0 mock implements continue, warn, block, and diagnostic hold decisions.

## Artifacts

The gateway writes redacted metadata artifacts only:

- `04_workflow_state/llm_interaction_log_redacted.json`
- `final_report/llm_usage_and_cost_summary.md`

These artifacts contain concise summaries, usage, cost, and budget decisions.
They do not contain raw secrets, credentials, hidden reasoning, or executable
instructions.